"""Local HTML heuristics for hidden content and agent-directed instructions.

Inspects inline declarations and simple embedded stylesheet selectors. This is
not a browser layout engine: external CSS, scripts, media queries and viewport
geometry are not evaluated. Findings are evidence to review, never permission
to execute instructions from the page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
import re


_INSTRUCTION = re.compile(r"\bignore\s+(?:all\s+)?previous\b|\bthe\s+agent\s+must\b", re.I)
_ZERO = re.compile(r"^[+-]?(?:0+(?:\.0*)?|\.0+)(?:px|pt|em|rem|%|vh|vw)?$", re.I)
_VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
_NON_TEXT = frozenset({"style", "script", "template"})


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str | None] = field(default_factory=dict)
    children: list = field(default_factory=list)
    parent: _Node | None = None
    start: str = ""

    def text(self) -> str:
        if self.tag in _NON_TEXT:
            return ""
        return "".join(child.text() if isinstance(child, _Node) else child for child in self.children)


class _Document(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("document")
        self.stack = [self.root]
        self.nodes: list[_Node] = []
        self.comments: list[str] = []

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, dict(attrs), parent=self.stack[-1], start=self.get_starttag_text())
        self.stack[-1].children.append(node)
        self.nodes.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)

    def handle_comment(self, data):
        self.comments.append(data)


def _declarations(css: str) -> list[tuple[str, str, bool]]:
    result = []
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for declaration in css.split(";"):
        name, separator, value = declaration.partition(":")
        if not separator:
            continue
        important = bool(re.search(r"!\s*important\s*$", value, re.I))
        value = re.sub(r"!\s*important\s*$", "", value, flags=re.I).strip().lower()
        result.append((name.strip().lower(), value, important))
    return result


def _selector_matches(node: _Node, selector: str) -> bool:
    """Match tag, #id, .class and compound forms, plus descendant selectors."""
    parts = selector.strip().split()
    if not parts:
        return False

    def simple(target: _Node, part: str) -> bool:
        tokens = re.findall(r"(?:[#.][\w-]+|[\w-]+|\*)", part)
        if "".join(tokens) != part:
            return False  # Unsupported selectors must not match normal content.
        for token in tokens:
            if token.startswith("#"):
                if target.attrs.get("id") != token[1:]:
                    return False
            elif token.startswith("."):
                if token[1:] not in (target.attrs.get("class") or "").split():
                    return False
            elif token != "*" and target.tag != token.lower():
                return False
        return bool(tokens)

    if not simple(node, parts[-1]):
        return False
    ancestor = node.parent
    for part in reversed(parts[:-1]):
        while ancestor is not None and not simple(ancestor, part):
            ancestor = ancestor.parent
        if ancestor is None:
            return False
        ancestor = ancestor.parent
    return True


def _style(node: _Node, rules: list[tuple[str, list, int]]) -> dict[str, str]:
    properties = {}

    def apply(declarations, inline, specificity, order):
        for index, (name, value, important) in enumerate(declarations):
            priority = (important, inline, *specificity, order, index)
            if name not in properties or priority >= properties[name][0]:
                properties[name] = (priority, value)

    for selector, declarations, order in rules:
        if _selector_matches(node, selector):
            specificity = (
                selector.count("#"), selector.count("."),
                len(re.findall(r"(?:^|\s)[a-zA-Z][\w-]*", selector)),
            )
            apply(declarations, False, specificity, order)
    apply(_declarations(node.attrs.get("style") or ""), True, (0, 0, 0), len(rules))
    return {name: value for name, (_, value) in properties.items()}


def _off_screen(style: dict[str, str]) -> bool:
    # Large pixel offsets are strong evidence without guessing a viewport size.
    for name in ("left", "right", "top", "bottom", "margin-left", "margin-top", "text-indent"):
        value = style.get(name, "")
        match = re.fullmatch(r"(-?\d+(?:\.\d+)?)px", value)
        if match and float(match[1]) <= -1000:
            if name in {"text-indent", "margin-left", "margin-top"} or style.get("position") in {"absolute", "fixed"}:
                return True
    transform = style.get("transform", "")
    for match in re.finditer(r"translate(?:x|y)?\(\s*(-?\d+(?:\.\d+)?)(px|%)", transform):
        if float(match[1]) <= (-1000 if match[2] == "px" else -100):
            return True
    return False


def scan_html(html: str) -> dict:
    """Return {flagged, findings:[{kind,snippet}]} with snippets <= 120 chars."""
    if not isinstance(html, str):
        raise TypeError("html must be a string")
    document = _Document()
    document.feed(html)
    document.close()
    rules = []
    for node in document.nodes:
        if node.tag == "style":
            css = "".join(child for child in node.children if isinstance(child, str))
            css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
            # Do not apply conditional rules without a browser/media context.
            css = re.sub(r"@[^{}]+\{(?:[^{}]|\{[^{}]*\})*\}", "", css, flags=re.S)
            for selectors, declarations in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
                for selector in selectors.split(","):
                    rules.append((selector.strip(), _declarations(declarations), len(rules)))

    findings = []
    seen = set()

    def add(kind: str, text: str) -> None:
        snippet = re.sub(r"\s+", " ", text).strip()[:120]
        key = (kind, snippet)
        if key not in seen:
            seen.add(key)
            findings.append({"kind": kind, "snippet": snippet})

    for node in document.nodes:
        if node.tag in _NON_TEXT:
            continue
        style = _style(node, rules)
        text = node.text() or node.start
        if style.get("display") == "none":
            add("display:none", text)
        if style.get("visibility") == "hidden":
            add("visibility:hidden", text)
        if (node.attrs.get("aria-hidden") or "").strip().lower() == "true":
            add("aria-hidden", text)
        if _off_screen(style):
            add("off-screen", text)
        if _ZERO.fullmatch(style.get("font-size", "")):
            add("font-size:0", text)
        if _ZERO.fullmatch(style.get("opacity", "")):
            add("opacity:0", text)
        if "hidden" in node.attrs:
            add("hidden", text)

    # Find minimal containing elements so wrappers don't duplicate instructions.
    for node in [document.root, *document.nodes]:
        text = node.text()
        if _INSTRUCTION.search(text) and not any(
            isinstance(child, _Node) and _INSTRUCTION.search(child.text()) for child in node.children
        ):
            add("instruction-like", text)
    for comment in document.comments:
        if _INSTRUCTION.search(comment):
            add("instruction-like", comment)
    return {"flagged": bool(findings), "findings": findings}
