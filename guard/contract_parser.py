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

_SCHEMA: dict[str, Any] = Contract.model_json_schema()
# Strict structured output requires every property, including nullable ones.
for _definition in [_SCHEMA, *_SCHEMA.get("$defs", {}).values()]:
    if "properties" in _definition:
        _definition["required"] = list(_definition["properties"])
        for _property in _definition["properties"].values():
            _property.pop("default", None)


def _openai_json(text: str, api_key: str) -> dict[str, Any]:
    """Request a strict JSON object from OpenAI's Responses API."""

    payload = {
        "model": os.getenv("GUARD_LLM_MODEL", "gpt-4.1-mini"),
        "temperature": 0,
        "max_output_tokens": 1000,
        "input": [
            {
                "role": "system",
                "content": "Draft a booking contract only; never approve a booking. Return the requested JSON object. Use source parsed. Unspecified requirements are null.",
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
    if not isinstance(body, dict) or body.get("status") != "completed":
        raise ValueError("LLM response was incomplete or unsuccessful")
    # Raw REST responses carry text in output[].content[]. The SDK convenience
    # property output_text is not a guaranteed top-level wire field.
    pieces = []
    output = body.get("output", [])
    if not isinstance(output, list):
        raise ValueError("LLM response output was not an array")
    for message in output:
        if not isinstance(message, dict) or message.get("type") != "message":
            continue
        content = message.get("content", [])
        if not isinstance(content, list):
            raise ValueError("LLM message content was not an array")
        for part in content:
            if not isinstance(part, dict):
                raise ValueError("LLM message content was invalid")
            if part.get("type") == "refusal":
                raise ValueError("LLM declined to draft the contract")
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                pieces.append(part["text"])
    output_text = "".join(pieces)
    if not output_text:
        raise ValueError("LLM response did not contain output text")
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
        return DEMO_CONTRACT.model_copy(deep=True)
    try:
        parsed = Contract.model_validate(_openai_json(text, api_key))
        return parsed.model_copy(update={"source": "parsed"})
    except (OSError, URLError, ValueError, ValidationError, json.JSONDecodeError):
        return DEMO_CONTRACT.model_copy(deep=True)
