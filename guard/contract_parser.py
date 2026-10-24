"""LLM-backed contract parsing with a deterministic demo fallback."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from .models import Contract


DEMO_CONTRACT = Contract(
    route={"from": "Ludhiana", "to": "Delhi"},
    date="2026-10-25",
    quantity=1,
    max_total=1000,
    allow_extras=False,
    source="fallback",
)

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "route": {"type": "object", "properties": {"from": {"type": "string"}, "to": {"type": "string"}}, "required": ["from", "to"], "additionalProperties": False},
        "date": {"type": "string"},
        "quantity": {"type": "integer", "minimum": 1},
        "max_total": {"type": "number", "minimum": 0},
        "allow_extras": {"type": "boolean"},
        "requirements": {"type": "object"},
        "source": {"type": "string", "enum": ["parsed", "fallback"]},
    },
    "required": ["route", "date", "quantity", "max_total", "allow_extras", "requirements", "source"],
}


def _openai_json(text: str, api_key: str) -> dict[str, Any]:
    """Request a strict JSON object from OpenAI's Responses API."""

    payload = {
        "model": os.getenv("GUARD_LLM_MODEL", "gpt-4.1-mini"),
        "temperature": 0,
        "input": [
            {
                "role": "system",
                "content": "Extract a booking contract. Return only the requested JSON object.",
            },
            {"role": "user", "content": text},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "booking_contract",
                "strict": True,
                "schema": _SCHEMA,
            }
        },
    }
    request = Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:  # nosec B310: fixed HTTPS API endpoint
        body = json.loads(response.read().decode("utf-8"))
    output_text = body.get("output_text")
    if not isinstance(output_text, str):
        raise ValueError("LLM response did not contain output_text")
    parsed = json.loads(output_text)
    if not isinstance(parsed, dict):
        raise ValueError("LLM response was not a JSON object")
    return parsed


def parse_contract(text: str) -> Contract:
    """Parse a natural-language request or return the known demo contract.

    Network access is isolated here, never in :func:`guard.checker.check`. The
    function uses ``OPENAI_API_KEY`` when available. Any missing key, API failure,
    malformed response, or model-validation failure returns ``DEMO_CONTRACT``.
    """

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return DEMO_CONTRACT
    try:
        return Contract.model_validate(_openai_json(text, api_key))
    except (OSError, URLError, ValueError, ValidationError, json.JSONDecodeError):
        return DEMO_CONTRACT
