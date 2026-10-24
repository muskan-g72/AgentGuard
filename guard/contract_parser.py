"""Draft contracts only; user confirmation is required before execution."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.request import Request, urlopen

from .models import Contract, Question, Requirements

DEMO_CONTRACT = Contract(
    route={"from": "Ludhiana", "to": "Delhi"}, date="2026-10-26",
    quantity=1, max_total=1000, allow_extras=False, source="fallback",
)


def _draft_schema() -> dict[str, Any]:
    schema = Contract.model_json_schema()
    # Structured Outputs requires every property, even nullable ones.
    for obj in [schema, *schema.get("$defs", {}).values()]:
        if obj.get("type") == "object":
            obj["required"] = list(obj.get("properties", {}))
            for prop in obj.get("properties", {}).values():
                prop.pop("default", None)
    return schema


def _openai_json(text: str, api_key: str) -> dict[str, Any]:
    payload = {
        "model": os.getenv("GUARD_LLM_MODEL", "gpt-4.1-mini"),
        "temperature": 0,
        "input": [
            {"role": "system", "content": (
                "Draft a booking contract from the user's text. Money is integer rupees. "
                "Use null for unspecified requirements; do not infer preferences. "
                "Use source parsed. Never authorize a purchase or operate a browser."
            )},
            {"role": "user", "content": text},
        ],
        "text": {"format": {"type": "json_schema", "name": "booking_contract", "strict": True, "schema": _draft_schema()}},
    }
    request = Request(
        "https://api.openai.com/v1/responses", data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST",
    )
    with urlopen(request, timeout=20) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not isinstance(body, dict) or body.get("status") != "completed":
        raise ValueError("Draft response did not complete")
    chunks = [
        content["text"]
        for output in body.get("output", []) if output.get("type") == "message"
        for content in output.get("content", []) if content.get("type") == "output_text"
    ]
    result = json.loads("".join(chunks))
    if not isinstance(result, dict):
        raise ValueError("Draft must be an object")
    return result


def parse_contract(text: str) -> Contract:
    key = os.getenv("OPENAI_API_KEY")
    if key:
        try:
            draft = _openai_json(text, key)
            draft["source"] = "parsed"  # Provenance is assigned locally.
            return Contract.model_validate(draft)
        except Exception:
            # Failure produces an explicitly labelled draft, never authorization.
            pass
    return DEMO_CONTRACT.model_copy(deep=True)


def questions_for(contract: Contract) -> list[Question]:
    wording = {
        "refundable": "Do you need a refundable ticket?",
        "seat_confirmed": "Do you need a confirmed seat?",
        "baggage": "Do you need baggage included?",
    }
    return [Question(key=key, text=wording[key]) for key in Requirements.model_fields
            if getattr(contract.requirements, key) is None]
