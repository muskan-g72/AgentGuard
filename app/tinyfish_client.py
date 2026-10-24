"""TinyFish synchronous Agent API client."""

# TinyFish Agent API Reference (read 2026-10-24): POST
# https://agent.tinyfish.ai/v1/automation/run with JSON fields "url" and
# "goal", authenticated by the "X-API-Key" header. The same request shape is
# used by /run-async and /run-sse, but this client intentionally uses /run.
# Sources: https://docs.tinyfish.ai/agent-api/reference.md and
# https://docs.tinyfish.ai/api-reference/automation/run-browser-automation-synchronously.md

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv


_API_URL = "https://agent.tinyfish.ai/v1/automation/run"
_TIMEOUT_SECONDS = 360


class TinyFishError(RuntimeError):
    """A request, authentication, or Agent-run error."""


def _load_key() -> str:
    """Load a local .env file without putting its contents in source control."""

    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env")
    key = os.getenv("TINYFISH_API_KEY")
    if not key:
        raise TinyFishError("TINYFISH_API_KEY is missing. Add it to the project's .env file.")
    return key


def run_agent(url: str, goal: str) -> dict:
    """Run one synchronous TinyFish automation and return its raw JSON response."""

    request = Request(
        _API_URL,
        data=json.dumps({"url": url, "goal": goal}).encode("utf-8"),
        headers={"X-API-Key": _load_key(), "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # nosec B310: fixed HTTPS API endpoint
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise TinyFishError(f"TinyFish returned HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise TinyFishError(f"Could not reach TinyFish: {error.reason}") from error
    except TimeoutError as error:
        raise TinyFishError(f"TinyFish did not respond within {_TIMEOUT_SECONDS} seconds.") from error
    except json.JSONDecodeError as error:
        raise TinyFishError("TinyFish returned invalid JSON.") from error

    if not isinstance(body, dict):
        raise TinyFishError("TinyFish returned a JSON value other than an object.")
    if body.get("status") != "COMPLETED":
        error = body.get("error") or {}
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise TinyFishError(f"TinyFish run did not complete: {message or body.get('status', 'unknown status')}")
    if body.get("result") is None:
        raise TinyFishError("TinyFish completed without a result.")
    return body
