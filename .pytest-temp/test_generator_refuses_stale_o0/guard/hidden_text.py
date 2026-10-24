"""Small, deterministic detector for suspicious hidden instruction text."""

from __future__ import annotations

import re


_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("instruction to ignore a constraint", re.compile(r"\bignore\b", re.I)),
    ("system-note instruction", re.compile(r"\bsystem\s+note\b", re.I)),
    ("AI-agent instruction", re.compile(r"\bai\s+agents?\b", re.I)),
    ("instruction to hide information from the user", re.compile(r"\bdo\s+not\s+tell\s+(?:the\s+)?user\b", re.I)),
    ("instruction to add insurance", re.compile(r"\badd\s+(?:travel\s+)?insurance\b", re.I)),
    ("instruction to bypass a safeguard", re.compile(r"\b(?:bypass|override|disregard)\b", re.I)),
)


def scan_hidden_text(blocks: list[str]) -> list[str]:
    """Return one plain-language flag per suspicious pattern found.

    The function only examines supplied text. It performs no I/O.
    """

    text = "\n".join(blocks)
    return [flag for flag, pattern in _PATTERNS if pattern.search(text)]
