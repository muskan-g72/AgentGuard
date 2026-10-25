"""Cart staging with TinyFish, plus replayable raw recordings."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from pydantic import ValidationError

from guard.models import Cart, Contract

from .tinyfish_client import TinyFishError, run_agent, validate_replay_url


class StagingError(RuntimeError):
    """A staged Agent result could not be parsed or its item IDs verified."""


_ROOT = Path(__file__).resolve().parents[1]
_RECORDINGS = _ROOT / "recordings"


def _safe_scenario(scenario: str) -> str:
    return scenario if scenario.replace("-", "").replace("_", "").isalnum() else "manual"


def _scenario_from_url(cart_url: str) -> str:
    scenario = parse_qs(urlparse(cart_url).query).get("scenario", ["manual"])[0]
    return _safe_scenario(scenario)


def _goal(contract: Contract, *, retry: bool = False) -> str:
    reminder = (
        " Reinspect the literal checkout row attributes and correct the extraction problem. "
        "Return only the JSON object. Do not include Markdown, explanations outside extraction_error, or extra keys."
        if retry else ""
    )
    return (
        "Stage a train cart for this authorized contract: "
        f"{contract.model_dump_json()}. "
        f"maximum total Rs {contract.max_total}; extras allowed: {contract.allow_extras}. "
        "Select the matching ticket and go to checkout. Do NOT click Confirm, Pay, "
        "Place order, Submit, or any equivalent final-action button. "
        "Inspect the checkout page and return only a JSON object with exactly these top-level keys: "
        '"cart", "hidden_text", "checkout_html", "extraction_error", and "staged_url". '
        'Copy the exact final checkout URL, including the complete selected state, into staged_url. '
        '"cart" must contain "cart_id", "items", "total", "passengers", "attributes", and "hidden_text". '
        'All prices and totals must be integer rupees. Inspect checkbox state and omit unchecked extras. '
        'If the total or passenger count is absent or unknown, return null; never infer it from the URL or fare catalogue. '
        'attributes must contain refundable, seat_confirmed, baggage, each boolean or null for unknown. '
        'Every item must contain "id", "type", and "price"; ticket items must also contain "route" and "date". '
        'For every included cart item, inspect its checkout row in the HTML/DOM and copy the row\'s '
        '"data-item-id" attribute verbatim into "id". Do not derive an ID from the item type, '
        'visible label, or checkbox element\'s "id" attribute. Before returning, verify each item ID '
        'against its row\'s actual "data-item-id" and "data-item-type". '
        'Return the literal outerHTML of the checkout #cart element as "checkout_html", including '
        'all data-item-id and data-item-type attributes, without rewriting them. '
        'On success set "extraction_error" to null. If the row attributes cannot be read, do not '
        'invent an ID: return "cart": null, "checkout_html": null, and describe the extraction '
        'problem in "extraction_error". Do not claim that an item with an unknown ID can be removed safely. '
        'Item "type" is one of "ticket", "insurance", "meal", or "fee". '
        '"hidden_text" must be a list of hidden or invisible text strings noticed on the page.'
        + reminder
    )


def _recording_path(scenario: str) -> Path:
    if _safe_scenario(scenario) != scenario:
        raise StagingError("Invalid replay scenario name.")
    return _RECORDINGS / f"{scenario}.json"


def _save_recording(scenario: str, raw: dict) -> Path:
    live_directory = _RECORDINGS / "live"
    live_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = live_directory / f"{_safe_scenario(scenario)}_{timestamp}_{uuid4().hex}.json"
    with path.open("x", encoding="utf-8") as recording:
        recording.write(json.dumps(raw, indent=2))
    return path


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


class _CheckoutRows(HTMLParser):
    """Read literal row IDs and types from the Agent's checkout HTML evidence."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: dict[str, str | None] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if "data-item-id" not in attributes:
            return
        item_id = attributes["data-item-id"]
        if not item_id or not item_id.strip():
            raise StagingError("Checkout row has an empty data-item-id; safe removal targets cannot be established.")
        if item_id in self.rows:
            raise StagingError(f"Checkout HTML has duplicate data-item-id {item_id!r}; removal targets are ambiguous.")
        self.rows[item_id] = attributes.get("data-item-type")


def _validate_item_ids(cart: Cart, checkout_html: object) -> None:
    if not isinstance(checkout_html, str) or not checkout_html.strip():
        raise StagingError("Checkout HTML is missing; item IDs cannot be verified for safe removal.")
    parser = _CheckoutRows()
    parser.feed(checkout_html)
    parser.close()
    if not parser.rows:
        raise StagingError("Checkout HTML has no data-item-id rows; safe removal targets cannot be established.")
    seen: set[str] = set()
    for item in cart.items:
        if item.id in seen:
            raise StagingError(f"Cart has duplicate item ID {item.id!r}; removal targets are ambiguous.")
        seen.add(item.id)
        if item.id not in parser.rows:
            raise StagingError(f"Item ID {item.id!r} is not a checkout row's data-item-id; it cannot be safely targeted.")
        if parser.rows[item.id] != item.type:
            raise StagingError(f"Item ID {item.id!r} has a different or missing checkout row type; it cannot be safely targeted.")


def _parse(raw: dict, *, verify_item_ids: bool = False) -> tuple[Cart, list[str]]:
    result = _result_object(raw)
    extraction_error = result.get("extraction_error")
    if extraction_error is not None:
        if not isinstance(extraction_error, str) or not extraction_error.strip():
            raise StagingError("The agent result extraction_error must be a nonempty explanation or null.")
        raise StagingError(f"Cart item-ID extraction failed: {extraction_error}")
    cart = Cart.model_validate(result.get("cart"))
    if verify_item_ids or "checkout_html" in result:
        _validate_item_ids(cart, result.get("checkout_html"))
    hidden_text = result.get("hidden_text", [])
    if not isinstance(hidden_text, list) or not all(isinstance(text, str) for text in hidden_text):
        raise StagingError("The agent result field hidden_text must be a list of strings.")
    hidden_text = list(dict.fromkeys(cart.hidden_text + hidden_text))
    cart = cart.model_copy(update={"hidden_text": hidden_text})
    return cart, hidden_text


@dataclass
class StageEvidence:
    cart: Cart
    hidden_text: list[str]
    staged_url: str | None
    mode: str


def stage_cart_details(
    cart_url: str, contract: Contract, *, scenario: str | None = None
) -> tuple[Cart, list[str]]:
    """Stage a cart and return it with any hidden text found by the Agent."""

    evidence = stage_cart_evidence(cart_url, contract, scenario=scenario)
    return evidence.cart, evidence.hidden_text


def stage_cart_evidence(cart_url: str, contract: Contract, *, scenario: str | None = None,
                        max_attempts: int = 2, replay: bool | None = None) -> StageEvidence:
    scenario = scenario or _scenario_from_url(cart_url)
    use_replay = replay if replay is not None else os.getenv("REPLAY") == "1"
    if use_replay:
        validate_replay_url(cart_url)
        cart, hidden = _parse(_load_recording(scenario))
        return StageEvidence(cart, hidden, None, "fixture_replay")

    def parsed(raw):
        cart, hidden = _parse(raw, verify_item_ids=True)
        staged_url = _result_object(raw).get("staged_url")
        if staged_url is not None and not isinstance(staged_url, str):
            raise StagingError("The staged URL must be a string.")
        return StageEvidence(cart, hidden, staged_url, "live_agent")

    try:
        raw = run_agent(cart_url, _goal(contract))
        _save_recording(scenario, raw)
    except TinyFishError as error:
        raise StagingError(f"Agent staging request failed: {error}") from error
    try:
        return parsed(raw)
    except (StagingError, ValidationError, json.JSONDecodeError) as first_error:
        if max_attempts <= 1:
            raise StagingError("Live extraction failed; the single-run limit prevents a retry.") from first_error
        # Retry exactly once for invalid cart data or unverifiable row IDs.
        try:
            retry_raw = run_agent(cart_url, _goal(contract, retry=True))
            _save_recording(scenario, retry_raw)
            return parsed(retry_raw)
        except TinyFishError as retry_error:
            raise StagingError(f"Agent staging retry failed: {retry_error}") from retry_error
        except (StagingError, ValidationError, json.JSONDecodeError) as retry_error:
            raise StagingError(
                f"Agent staging failed after one extraction retry: {first_error} | {retry_error}"
            ) from retry_error


def stage_cart(cart_url: str, contract: Contract) -> Cart:
    """Stage one cart. This public interface returns only the shared Cart model."""

    cart, _hidden_text = stage_cart_details(cart_url, contract)
    return cart
