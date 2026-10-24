"""Deterministic questions about preferences omitted from a train request."""

from __future__ import annotations

import re

from .models import Contract


_CHECKLIST = (
    ("refundable", "Must the ticket be refundable?", r"\b(?:non[-\s]?)?refundable\b|\brefunds?\b"),
    ("seat_confirmed", "Must the ticket have a confirmed seat?",
     r"\b(?:confirmed|reserved)\s+seats?\b|\bseat\s+(?:confirmation|reservation|confirmed)\b|\bwait[-\s]?list(?:ed)?\b"),
    ("baggage", "Must baggage be included?", r"\b(?:baggage|luggage)\b"),
)
_UNCERTAIN = re.compile(r"\b(?:unsure|uncertain|maybe|whether|not sure|don['’]t know|do not know)\b", re.I)
_OPTIONS = ["yes", "no", "don't care"]


def _contract(draft: Contract | dict) -> Contract:
    # Revalidate and copy so answers cannot mutate a shared draft or fallback.
    return Contract.model_validate(draft.model_dump() if isinstance(draft, Contract) else draft)


def _implied(sentence: str, pattern: str) -> bool:
    for clause in re.split(r"[.!;\n]", sentence):
        if re.search(pattern, clause, re.I) and "?" not in clause and not _UNCERTAIN.search(clause):
            return True
    return False


def find_gaps(draft_contract: Contract | dict, sentence: str) -> list[dict]:
    """Return at most three questions in a stable order.

    Explicit refundable/seat/baggage wording counts as an implication. Price
    words such as 'cheapest' never imply one of these preferences. Uncertain
    wording and questions do not establish a preference. This function only
    chooses questions; the contract parser owns extracting explicit intent.
    """

    if not isinstance(sentence, str):
        raise TypeError("sentence must be a string")
    draft = _contract(draft_contract)
    return [
        {"key": key, "text": text, "options": _OPTIONS.copy()}
        for key, text, pattern in _CHECKLIST
        if getattr(draft.requirements, key) is None and not _implied(sentence, pattern)
    ]


def apply_answers(draft: Contract | dict, answers: dict[str, str]) -> Contract:
    """Apply only recognized checklist answers and preserve all other fields.

    'No' means a negative requirement; 'don't care' means no constraint. Invalid
    keys or answers raise ValueError instead of silently weakening a contract.
    """

    result = _contract(draft)
    if not isinstance(answers, dict):
        raise ValueError("answers must be a dictionary")
    allowed_keys = {key for key, _, _ in _CHECKLIST}
    values = {"yes": True, "no": False, "don't care": None}
    for key, answer in answers.items():
        if key not in allowed_keys:
            raise ValueError(f"Unexpected answer key: {key}")
        if not isinstance(answer, str) or answer not in values:
            raise ValueError(f"Invalid answer for {key}; choose yes, no, or don't care")
        setattr(result.requirements, key, values[answer])
    return result
