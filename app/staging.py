"""Cart staging with TinyFish, plus replayable raw recordings."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pydantic import ValidationError

from guard.models import Cart, Contract

from .tinyfish_client import TinyFishError, run_agent


class StagingError(RuntimeError):
    """A staged Agent result could not be parsed as the shared cart shape."""


_ROOT = Path(__file__).resolve().parents[1]
_RECORDINGS = _ROOT / "recordings"


def _scenario_from_url(cart_url: str) -> str:
    scenario = parse_qs(urlparse(cart_url).query).get("scenario", ["manual"])[0]
    return scenario if scenario.replace("-", "").replace("_", "").isalnum() else "manual"


def _goal(contract: Contract, *, retry: bool = False) -> str:
    reminder = " Return only the JSON object. Do not include Markdown, explanations, or extra keys." if retry else ""
    return (
        "Stage a train cart for this authorized contract: "
        f"route {contract.route}; date {contract.date}; quantity {contract.quantity}; "
        f"maximum total Rs {contract.max_total}; extras allowed: {contract.allow_extras}. "
        "Select the matching ticket and go to checkout. Do NOT click Confirm, Pay, "
        "Place order, Submit, or any equivalent final-action button. "
        "Inspect the checkout page and return only a JSON object with exactly these top-level keys: "
        '"cart" and "hidden_text". "cart" must contain "cart_id", "items", "total", and "passengers". '
        'Every item must contain "id", "type", and "price"; ticket items must also contain "route" and "date". '
        'For every included cart item, inspect its checkout row in the HTML/DOM and copy the row\'s '
        '"data-item-id" attribute verbatim into "id". Do not derive an ID from the item type, '
        'visible label, or checkbox element\'s "id" attribute. Before returning, verify each item ID '
        'against its row\'s actual "data-item-id". Do not invent an ID if that attribute cannot be read. '
        'Item "type" is one of "ticket", "insurance", "meal", or "fee". '
        '"hidden_text" must be a list of hidden or invisible text strings noticed on the page.'
        + reminder
    )


def _recording_path(scenario: str) -> Path:
    return _RECORDINGS / f"{scenario}.json"


def _save_recording(scenario: str, raw: dict) -> None:
    _RECORDINGS.mkdir(exist_ok=True)
    _recording_path(scenario).write_text(json.dumps(raw, indent=2), encoding="utf-8")


def _load_recording(scenario: str) -> dict:
    path = _recording_path(scenario)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise StagingError(f"Replay is enabled but no recording exists at {path}.") from error
    except json.JSONDecodeError as error:
        raise StagingError(f"Replay recording {path} is not valid JSON.") from error
    if not isinstance(value, dict):
        raise StagingError(f"Replay recording {path} must contain a JSON object.")
    return value


def _result_object(raw: dict) -> dict:
    value = raw.get("result", raw)
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise StagingError("The agent result must be a JSON object.")
    return value


def _parse(raw: dict) -> tuple[Cart, list[str]]:
    result = _result_object(raw)
    cart = Cart.model_validate(result.get("cart"))
    hidden_text = result.get("hidden_text", [])
    if not isinstance(hidden_text, list) or not all(isinstance(text, str) for text in hidden_text):
        raise StagingError("The agent result field hidden_text must be a list of strings.")
    return cart, hidden_text


def stage_cart_details(
    cart_url: str, contract: Contract, *, scenario: str | None = None
) -> tuple[Cart, list[str]]:
    """Stage a cart and return it with any hidden text found by the Agent."""

    scenario = scenario or _scenario_from_url(cart_url)
    if os.getenv("REPLAY") == "1":
        return _parse(_load_recording(scenario))

    try:
        raw = run_agent(cart_url, _goal(contract))
        _save_recording(scenario, raw)
    except TinyFishError as error:
        raise StagingError(f"Agent staging request failed: {error}") from error
    try:
        return _parse(raw)
    except (StagingError, ValidationError, json.JSONDecodeError) as first_error:
        # Retry exactly once only when the Agent's completed response was not parseable.
        try:
            retry_raw = run_agent(cart_url, _goal(contract, retry=True))
            _save_recording(scenario, retry_raw)
            return _parse(retry_raw)
        except TinyFishError as retry_error:
            raise StagingError(f"Agent staging retry failed: {retry_error}") from retry_error
        except (StagingError, ValidationError, json.JSONDecodeError) as retry_error:
            raise StagingError(
                f"Agent staging failed after one JSON-only retry: {first_error} | {retry_error}"
            ) from retry_error


def stage_cart(cart_url: str, contract: Contract) -> Cart:
    """Stage one cart. This public interface returns only the shared Cart model."""

    cart, _hidden_text = stage_cart_details(cart_url, contract)
    return cart
