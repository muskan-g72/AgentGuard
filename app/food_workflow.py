"""Food adapter around the existing task event chain and allow-before-commit rule."""

from __future__ import annotations

from typing import Protocol

from guard.food_checker import check_food_cart
from guard.food_models import FoodContract, FoodOption, StagedFoodCart
from guard.models import Decision

from .food_compare import commit_staged_order, effective_price, fix_staged_cart, stage_winner
from .store import Store, digest


class FoodBrowser(Protocol):
    def stage_winner(self, option: FoodOption, contract: FoodContract) -> StagedFoodCart: ...
    def fix_cart(self, option: FoodOption, cart: StagedFoodCart, remove_item_ids: list[str]) -> StagedFoodCart: ...
    def commit_order(self, option: FoodOption, cart: StagedFoodCart) -> dict: ...


class TinyFishFoodBrowser:
    """Production adapter. Each action is a separate TinyFish run."""

    def stage_winner(self, option: FoodOption, contract: FoodContract) -> StagedFoodCart:
        return stage_winner(option, contract)

    def fix_cart(self, option: FoodOption, cart: StagedFoodCart, remove_item_ids: list[str]) -> StagedFoodCart:
        return fix_staged_cart(option, cart, remove_item_ids)

    def commit_order(self, option: FoodOption, cart: StagedFoodCart) -> dict:
        return commit_staged_order(option, cart)


def _event(store: Store, task_id: str, status: str, detail: str, event_type: str, **payload):
    return store.event(task_id, status, detail, event_type=event_type, **payload)


def _decision(contract: FoodContract, cart: StagedFoodCart, expected_price: int, guard_off: bool) -> Decision:
    if guard_off:
        return Decision(result="allow", reasons=["Guard disabled for the before/after demo."], flags=["guard_off"])
    return check_food_cart(contract, cart, expected_price)


def commit_food_task(store: Store, task_id: str, browser: FoodBrowser, option: FoodOption,
                     cart: StagedFoodCart, decision: Decision, *, guard_off: bool) -> bool:
    """Food commit gate. The browser is never called without an allow decision.

    Guard-off mode is a deliberately labelled demo bypass requested by the caller.
    """

    task = store.food_task(task_id)
    if not guard_off:
        if task["status"] != "allowed":
            _event(store, task_id, task["status"], "Food commit refused: task is not allowed.", "food_commit_refused", reason="status is not allowed")
            return False
        stored = task.get("food_cart")
        if not isinstance(stored, dict) or task.get("food_cart_hash") != digest(stored):
            _event(store, task_id, task["status"], "Food commit refused: staged cart changed after check.", "food_commit_refused", reason="cart hash mismatch")
            return False
        stored_decision = task.get("food_decision") or {}
        if stored_decision.get("result") != "allow" or decision.result != "allow":
            _event(store, task_id, task["status"], "Food commit refused: latest decision is not allow.", "food_commit_refused", reason="decision is not allow")
            return False
        if cart.total is None:
            _event(store, task_id, task["status"], "Food commit refused: cart total is unknown.", "food_commit_refused", reason="cart total is unknown")
            return False
    else:
        _event(store, task_id, "committing", "Guard-off demo bypassed food check and commit gate.", "food_guard_off_bypass", cart=cart.model_dump(mode="json"))

    _event(store, task_id, "committing", "Starting the simulated food commit run.", "food_commit_started", cart=cart.model_dump(mode="json"))
    try:
        result = browser.commit_order(option, cart)
    except Exception as error:
        _event(store, task_id, "failed", "Food commit run failed; no confirmed order was recorded.", "food_commit_failed", error=type(error).__name__)
        return False
    if cart.total is None or type(result.get("total")) is not int or result.get("total") != cart.total:
        _event(store, task_id, "failed", "Food commit total differs from the allowed cart total.", "food_total_mismatch", approved_total=cart.total, confirmed_total=result.get("total"))
        return False
    if not isinstance(result.get("order_id"), str) or not result["order_id"]:
        _event(store, task_id, "failed", "Food commit returned no order ID.", "food_commit_failed")
        return False
    stored = store.record_food_order(task_id, cart, FoodContract.model_validate(task["contract"]), decision, result)
    _event(store, task_id, "done", "Simulated food order committed after the required checks.", "food_commit_result", order_id=stored["order_id"], total=cart.total)
    return True


def run_food_task(store: Store, task_id: str, browser: FoodBrowser, *, scenario: str | None = None) -> dict:
    """Stage, check, make one bounded fix, re-check, and conditionally commit."""

    task = store.food_task(task_id)
    if not task.get("reviewed"):
        raise RuntimeError("Food contract must be explicitly confirmed before running.")
    contract = FoodContract.model_validate(task["contract"])
    option = FoodOption.model_validate(task.get("recommended"))
    scenario = scenario or task.get("scenario")
    if scenario and scenario != "food":
        sep = "&" if "?" in option.url else "?"
        option = option.model_copy(update={"url": f"{option.url}{sep}scenario={scenario}"})
    guard_off = bool(task.get("guard_off"))
    expected_price = effective_price(option)
    try:
        _event(store, task_id, "staging", "Staging the recommended food cart without ordering.", "food_stage_started", option=option.model_dump(mode="json"))
        cart = browser.stage_winner(option, contract)
        _event(store, task_id, "checking", "Food cart staged and ready for deterministic checking.", "food_staged", cart=cart.model_dump(mode="json"))
        decision = _decision(contract, cart, expected_price, guard_off)
        _event(store, task_id, {"allow": "allowed", "block": "blocked", "ask": "blocked"}[decision.result], "Food cart decision recorded.", "food_decision", food_cart=cart.model_dump(mode="json"), food_cart_hash=digest(cart), food_decision=decision.model_dump(mode="json"), expected_effective_price=expected_price)
        if decision.result == "ask":
            return store.food_task(task_id)
        if decision.result == "block" and not guard_off:
            if not decision.remove_item_ids:
                return store.food_task(task_id)
            _event(store, task_id, "fixing", "Removing only checker-listed food extras.", "food_fix_started", remove_item_ids=decision.remove_item_ids)
            cart = browser.fix_cart(option, cart, decision.remove_item_ids)
            _event(store, task_id, "checking", "Food extras removed; re-checking fresh cart evidence.", "food_recheck", cart=cart.model_dump(mode="json"))
            decision = _decision(contract, cart, expected_price, False)
            _event(store, task_id, {"allow": "allowed", "block": "blocked", "ask": "blocked"}[decision.result], "Food re-check decision recorded.", "food_decision", food_cart=cart.model_dump(mode="json"), food_cart_hash=digest(cart), food_decision=decision.model_dump(mode="json"), expected_effective_price=expected_price)
            if decision.result != "allow":
                return store.food_task(task_id)
        if decision.result == "allow":
            commit_food_task(store, task_id, browser, option, cart, decision, guard_off=guard_off)
        return store.food_task(task_id)
    except Exception as error:
        _event(store, task_id, "failed", "Food workflow failed before a simulated order could be committed.", "food_run_failed", error=type(error).__name__)
        return store.food_task(task_id)
