"""Fixture-backed food comparison and staging through TinyFish Agent API.

TinyFish documentation checked 2026-10-25:
POST https://agent.tinyfish.ai/v1/automation/run-async accepts ``url``, ``goal``,
``output_schema`` and ``agent_config`` with ``X-API-Key`` authentication; it
returns ``run_id`` and ``error``. Results are polled at
GET https://agent.tinyfish.ai/v1/runs/{run_id} until status is COMPLETED, FAILED,
or CANCELLED. ``COMPLETED`` is validated as data, not treated as success itself.
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from pydantic import ValidationError

from guard.food_models import FoodContract, FoodOption, StagedFoodCart
from guard.food_rank import effective_price as guarded_effective_price
from guard.food_rank import rank as guard_rank
from guard.food_rank import taste_score as guarded_taste_score

from .tinyfish_client import TinyFishError, cancel_agent_run, get_agent_run, start_agent_async


class FoodCompareError(RuntimeError):
    """Food comparison or staging could not produce verified structured data."""


_ROOT = Path(__file__).resolve().parents[1]
_RECORDINGS = _ROOT / "recordings" / "food"
_POLL_SECONDS = 0.25
_DEFAULT_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class RejectedOption:
    option: FoodOption
    reasons: list[str]


@dataclass(frozen=True)
class ComparisonResult:
    options: list[FoodOption]
    failures: dict[str, str]


@dataclass(frozen=True)
class RankingResult:
    ranked: list[FoodOption]
    rejected: list[RejectedOption]


def _platform_name(url: str) -> str:
    parsed = urlparse(url)
    part = parsed.path.strip("/").split("/", 1)[0].lower()
    if part not in {"foodhub", "quickbite", "dinedash"}:
        raise FoodCompareError("Food platform URL must use the FoodHub, QuickBite, or DineDash path.")
    return part


def _fixture_path(platform: str) -> Path:
    return _RECORDINGS / f"{platform}.json"


def _load_fixture(platform: str) -> dict:
    try:
        value = json.loads(_fixture_path(platform).read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise FoodCompareError(f"Replay is enabled but food fixture {_fixture_path(platform)} is missing.") from error
    except json.JSONDecodeError as error:
        raise FoodCompareError(f"Food fixture {_fixture_path(platform)} is invalid JSON.") from error
    if not isinstance(value, dict) or value.get("fixture") is not True:
        raise FoodCompareError(f"Food replay file {_fixture_path(platform)} must be a clearly labelled fixture object.")
    return value


def _save_live(platform: str, raw: object, step: str) -> None:
    directory = _RECORDINGS / "live"
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = directory / f"{platform}__{step}__{timestamp}__{uuid4().hex}.json"
    path.write_text(json.dumps(raw, indent=2, sort_keys=True), encoding="utf-8")


def _option_schema() -> dict:
    money = {"type": "integer", "minimum": 0}
    coupon = {
        "type": "object", "properties": {
            "code": {"type": "string"}, "type": {"type": "string", "enum": ["flat", "percent"]},
            "value": money, "max_discount": {"type": "integer", "minimum": 0, "nullable": True}, "min_order": money,
        }, "required": ["code", "type", "value", "max_discount", "min_order"],
    }
    option = {
        "type": "object", "properties": {
            "platform": {"type": "string"}, "restaurant": {"type": "string"}, "dish": {"type": "string"},
            "veg": {"type": "boolean"}, "item_price": money, "rating": {"type": "number", "minimum": 0, "maximum": 5},
            "rating_count": {"type": "integer", "minimum": 0}, "eta_minutes": {"type": "integer", "minimum": 0},
            "fees": {"type": "object", "properties": {"delivery": money, "platform": money, "packaging": money}, "required": ["delivery", "platform", "packaging"]},
            "coupons": {"type": "array", "items": coupon}, "review_snippets": {"type": "array", "items": {"type": "string"}}, "url": {"type": "string"},
        }, "required": ["platform", "restaurant", "dish", "veg", "item_price", "rating", "rating_count", "eta_minutes", "fees", "coupons", "review_snippets", "url"],
    }
    return {"type": "object", "properties": {"options": {"type": "array", "items": option}}, "required": ["options"]}


def _staged_cart_schema() -> dict:
    money = {"type": "integer", "minimum": 0}
    item = {"type": "object", "properties": {"id": {"type": "string"}, "type": {"type": "string", "enum": ["dish", "tip", "donation", "membership", "fee"]}, "price": money}, "required": ["id", "type", "price"]}
    cart = {"type": "object", "properties": {"cart_id": {"type": "string"}, "items": {"type": "array", "items": item}, "coupon_applied": {"type": "string", "nullable": True}, "quantity": {"type": "integer", "minimum": 1, "nullable": True}, "total": {"type": "integer", "minimum": 0, "nullable": True}, "eta_minutes": {"type": "integer", "minimum": 0}, "veg": {"type": "boolean"}, "hidden_text": {"type": "array", "items": {"type": "string"}}}, "required": ["cart_id", "items", "coupon_applied", "quantity", "total", "eta_minutes", "veg", "hidden_text"]}
    return {"type": "object", "properties": {"cart": cart}, "required": ["cart"]}


def _comparison_goal(*, retry: bool) -> str:
    reminder = " Return only the JSON object, with no Markdown or explanation." if retry else ""
    return (
        "Compare every listed dish on this food platform. Open each dish detail page and extract ONLY visible page data. "
        "For every dish return platform, restaurant, dish, veg, item_price, rating, rating_count, eta_minutes, "
        "fees (delivery, platform, packaging), coupons (code, type flat or percent, value, max_discount or null, min_order), "
        "review_snippets, and the detail-page URL. All money must be integer rupees. "
        "Do not add anything to a cart. Do not start checkout. Do not place an order. "
        "If a field is not visible, do not invent it; omit that dish instead. Return only JSON matching the requested schema."
        + reminder
    )


def _staging_goal(option: FoodOption, contract: FoodContract, *, retry: bool) -> str:
    reminder = " Return only the JSON object, with no Markdown or explanation." if retry else ""
    return (
        f"Open the visible detail page for {option.restaurant}: {option.dish}. Add exactly quantity {contract.quantity} to the cart. "
        "Choose and apply only the single best eligible coupon: eligible means item_price is at least the coupon minimum order; "
        "for percent coupons cap the discount at max_discount. Go to checkout and inspect the cart. "
        "Do NOT click Place order, Pay, Confirm, Submit, or any equivalent final-action button. "
        "Return only JSON with cart_id, items (id, type dish|tip|donation|membership|fee, integer price), coupon_applied, "
        "quantity, integer total, eta_minutes, veg, and hidden_text. Include preselected tip, donation, or membership as items; "
        "do not remove them. Do not invent missing values."
        + reminder
    )


def _fix_goal(option: FoodOption, remove_item_ids: list[str], *, retry: bool) -> str:
    reminder = " Return only the JSON object, with no Markdown or explanation." if retry else ""
    return (
        f"Open the cart for {option.restaurant}: {option.dish}. Untick or remove only these item IDs: {remove_item_ids}. "
        "Keep the dish, required fees, quantity, and any eligible coupon unchanged. Go to checkout and return the current cart JSON. "
        "Do NOT click Place order, Pay, Confirm, Submit, or any equivalent final-action button. "
        "Return only JSON with cart_id, items (id, type dish|tip|donation|membership|fee, integer price), coupon_applied, "
        "quantity, integer total, eta_minutes, veg, and hidden_text."
        + reminder
    )


def _commit_goal(option: FoodOption, cart: StagedFoodCart) -> str:
    return (
        f"Open the checkout for {option.restaurant}: {option.dish}. Verify the visible cart total is Rs {cart.total}. "
        "This is a simulated demo only. Do not enter payment, card, address, phone, email, or personal data. "
        "Click Place order only when the page explicitly identifies the order as simulated and no real payment is taken. "
        "Return only JSON with order_id and integer total."
    )


def _result_object(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise FoodCompareError("TinyFish result is not a JSON object.")
    result = raw.get("result", raw)
    if isinstance(result, str):
        result = json.loads(result)
    if not isinstance(result, dict):
        raise FoodCompareError("TinyFish result payload is not a JSON object.")
    return result


def _parse_options(raw: object) -> list[FoodOption]:
    value = _result_object(raw).get("options")
    if not isinstance(value, list) or not value:
        raise FoodCompareError("TinyFish returned no food options.")
    return [FoodOption.model_validate(item) for item in value]


def _parse_staged_cart(raw: object) -> StagedFoodCart:
    return StagedFoodCart.model_validate(_result_object(raw).get("cart"))


def _with_coupon_evidence(staged: StagedFoodCart, option: FoodOption) -> StagedFoodCart:
    """Bind a staged coupon code to the selected option's visible coupon data."""

    if staged.coupon_applied is None:
        return staged
    coupon = next((value for value in option.coupons if value.code == staged.coupon_applied), None)
    return staged.model_copy(update={"coupon_details": coupon})


def _wait_for_result(run_id: str, *, timeout_seconds: int) -> dict:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        run = get_agent_run(run_id)
        status = run.get("status")
        if status == "COMPLETED":
            if run.get("result") is None:
                raise FoodCompareError("TinyFish completed without a result.")
            return run
        if status in {"FAILED", "CANCELLED"}:
            raise FoodCompareError(f"TinyFish {str(status).lower()} the food run.")
        time.sleep(_POLL_SECONDS)
    cancel_agent_run(run_id)
    raise FoodCompareError(f"TinyFish food run exceeded {timeout_seconds} seconds.")


def _live_options(platform_url: str, *, retry: bool, timeout_seconds: int) -> list[FoodOption]:
    platform = _platform_name(platform_url)
    queued = start_agent_async(platform_url, _comparison_goal(retry=retry), output_schema=_option_schema(), timeout_seconds=timeout_seconds)
    run_id = queued.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise FoodCompareError("TinyFish did not return a run_id for food comparison.")
    raw = _wait_for_result(run_id, timeout_seconds=timeout_seconds)
    _save_live(platform, raw, "compare")
    return _parse_options(raw)


def compare_platform(platform_url: str, *, timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS) -> list[FoodOption]:
    """Extract visible dish options from one platform, with one parse retry."""

    platform = _platform_name(platform_url)
    if os.getenv("REPLAY") == "1":
        return [FoodOption.model_validate(option) for option in _load_fixture(platform).get("options", [])]
    first_error: Exception | None = None
    for retry in (False, True):
        try:
            return _live_options(platform_url, retry=retry, timeout_seconds=timeout_seconds)
        except (FoodCompareError, TinyFishError, ValidationError, json.JSONDecodeError) as error:
            if retry:
                raise FoodCompareError(f"Food comparison failed after one JSON retry: {first_error} | {error}") from error
            first_error = error
    raise AssertionError("unreachable")


def compare_all(platform_urls: list[str], *, timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS) -> ComparisonResult:
    """Start all supplied platform comparisons concurrently and retain partial results."""

    options: list[FoodOption] = []
    failures: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(platform_urls) or 1) as executor:
        futures = {executor.submit(compare_platform, url, timeout_seconds=timeout_seconds): _platform_name(url) for url in platform_urls}
        for future in as_completed(futures):
            platform = futures[future]
            try:
                options.extend(future.result())
            except Exception as error:
                failures[platform] = str(error)
    return ComparisonResult(options=options, failures=failures)


def coupon_discount(option: FoodOption) -> int:
    """Return the largest discount from a coupon eligible on item price alone."""

    discounts: list[int] = []
    for coupon in option.coupons:
        if option.item_price < coupon.min_order:
            continue
        discount = coupon.value if coupon.type == "flat" else option.item_price * coupon.value // 100
        if coupon.type == "percent" and coupon.max_discount is not None:
            discount = min(discount, coupon.max_discount)
        discounts.append(discount)
    return max(discounts, default=0)


def effective_price(option: FoodOption) -> int:
    return guarded_effective_price(option)


def taste_score(option: FoodOption) -> float:
    return guarded_taste_score(option)


def rank_options(options: list[FoodOption], contract: FoodContract) -> RankingResult:
    result = guard_rank(contract, options)
    return RankingResult(
        ranked=[entry["option"] for entry in result["ranked"]],
        rejected=[RejectedOption(entry["option"], entry["reasons"]) for entry in result["dropped"]],
    )


def stage_winner(option: FoodOption, contract: FoodContract, *, timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS) -> StagedFoodCart:
    """Stage the selected food cart, retaining extras as evidence and never ordering."""

    platform = _platform_name(option.url)
    scenario = parse_qs(urlparse(option.url).query).get("scenario", ["clean"])[0]
    if os.getenv("REPLAY") == "1":
        fixture = _load_fixture(platform)
        try:
            staged = StagedFoodCart.model_validate(fixture["staged_carts"][scenario])
            return _with_coupon_evidence(staged, option)
        except (KeyError, ValidationError) as error:
            raise FoodCompareError(f"Food fixture has no valid staged {scenario!r} cart for {platform}.") from error

    first_error: Exception | None = None
    for retry in (False, True):
        try:
            queued = start_agent_async(option.url, _staging_goal(option, contract, retry=retry), output_schema=_staged_cart_schema(), timeout_seconds=timeout_seconds)
            run_id = queued.get("run_id")
            if not isinstance(run_id, str) or not run_id:
                raise FoodCompareError("TinyFish did not return a run_id for food staging.")
            raw = _wait_for_result(run_id, timeout_seconds=timeout_seconds)
            _save_live(platform, raw, "stage")
            return _with_coupon_evidence(_parse_staged_cart(raw), option)
        except (FoodCompareError, TinyFishError, ValidationError, json.JSONDecodeError) as error:
            if retry:
                raise FoodCompareError(f"Food staging failed after one JSON retry: {first_error} | {error}") from error
            first_error = error
    raise AssertionError("unreachable")


def fix_staged_cart(option: FoodOption, cart: StagedFoodCart, remove_item_ids: list[str], *, timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS) -> StagedFoodCart:
    """Remove only checker-identified food extras and return freshly staged evidence."""

    platform = _platform_name(option.url)
    if os.getenv("REPLAY") == "1":
        unknown = set(remove_item_ids) - {item.id for item in cart.items}
        if unknown:
            raise FoodCompareError("Food fix referenced an item that is not in the staged cart.")
        items = [item for item in cart.items if item.id not in set(remove_item_ids)]
        return cart.model_copy(update={"items": items, "total": sum(item.price for item in items)})
    first_error: Exception | None = None
    for retry in (False, True):
        try:
            queued = start_agent_async(option.url, _fix_goal(option, remove_item_ids, retry=retry), output_schema=_staged_cart_schema(), timeout_seconds=timeout_seconds)
            run_id = queued.get("run_id")
            if not isinstance(run_id, str) or not run_id:
                raise FoodCompareError("TinyFish did not return a run_id for food fix.")
            raw = _wait_for_result(run_id, timeout_seconds=timeout_seconds)
            _save_live(platform, raw, "fix")
            return _parse_staged_cart(raw)
        except (FoodCompareError, TinyFishError, ValidationError, json.JSONDecodeError) as error:
            if retry:
                raise FoodCompareError(f"Food fix failed after one JSON retry: {first_error} | {error}") from error
            first_error = error
    raise AssertionError("unreachable")


def commit_staged_order(option: FoodOption, cart: StagedFoodCart, *, timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS) -> dict:
    """Commit only the already-allowed simulated food order."""

    platform = _platform_name(option.url)
    if os.getenv("REPLAY") == "1":
        return {"order_id": f"food_replay_{platform}_{cart.cart_id}", "total": cart.total}
    queued = start_agent_async(option.url, _commit_goal(option, cart), output_schema={
        "type": "object", "properties": {"order_id": {"type": "string"}, "total": {"type": "integer", "minimum": 0}},
        "required": ["order_id", "total"],
    }, timeout_seconds=timeout_seconds)
    run_id = queued.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise FoodCompareError("TinyFish did not return a run_id for food commit.")
    raw = _wait_for_result(run_id, timeout_seconds=timeout_seconds)
    _save_live(platform, raw, "commit")
    result = _result_object(raw)
    if not isinstance(result.get("order_id"), str) or not result["order_id"] or type(result.get("total")) is not int:
        raise FoodCompareError("TinyFish returned an invalid simulated food order result.")
    return {"order_id": result["order_id"], "total": result["total"]}
