"""Deterministic checks for a staged food cart. No network or LLM access."""

from __future__ import annotations

from .food_models import FoodContract, StagedFoodCart
from .hidden_text import scan_hidden_text
from .models import Decision


def _money(amount: int) -> str:
    return f"Rs {amount:,}"


def _block(reasons: list[str], *, remove_item_ids: list[str] | None = None,
           differing_fields: list[str] | None = None) -> Decision:
    return Decision(
        result="block",
        reasons=reasons,
        remove_item_ids=remove_item_ids or [],
        differing_fields=differing_fields or [],
    )


def _coupon_is_eligible(cart: StagedFoodCart) -> bool:
    """Accept only explicit coupon metadata that matches the staged code."""

    if cart.coupon_applied is None:
        return True
    coupon = cart.coupon_details
    if coupon is None or coupon.code != cart.coupon_applied:
        return False
    item_price = sum(item.price for item in cart.items if item.type == "dish")
    return item_price >= coupon.min_order


def check_food_cart(
    contract: FoodContract,
    staged: StagedFoodCart,
    expected_effective_price: int,
    hidden_text: list[str] | None = None,
) -> Decision:
    """Check food cart evidence in the documented fail-closed order."""

    missing: list[str] = []
    if staged.total is None:
        missing.append("The cart total is missing.")
    if staged.quantity is None:
        missing.append("The quantity is missing.")
    if missing:
        return Decision(result="ask", reasons=missing)

    dish_items = [item for item in staged.items if item.type == "dish"]
    non_veg_items = [item for item in dish_items if item.veg is False]
    if contract.diet == "veg" and (staged.veg is False or non_veg_items):
        if non_veg_items:
            return _block(
                [f"Dish {item.id} is not vegetarian." for item in non_veg_items],
                differing_fields=["items"],
            )
        return _block(["The staged dish is not vegetarian."], differing_fields=["veg"])

    if staged.quantity != contract.quantity:
        return _block(
            [f"The cart has quantity {staged.quantity}, but {contract.quantity} was authorized."],
            differing_fields=["quantity"],
        )

    extras = [item for item in staged.items if item.type in {"tip", "donation", "membership"}]
    if not contract.allow_extras and extras:
        labels = {"tip": "Tip", "donation": "Donation", "membership": "Membership"}
        return _block(
            [f"{labels[item.type]} costs {_money(item.price)} and was not authorized." for item in extras],
            remove_item_ids=[item.id for item in extras],
            differing_fields=["items"],
        )

    assert staged.total is not None
    if staged.total > contract.max_total:
        return _block(
            [f"The cart total of {_money(staged.total)} exceeds the authorized maximum of {_money(contract.max_total)}."],
            differing_fields=["total"],
        )

    expected_total = expected_effective_price + sum(item.price for item in extras)
    if staged.total != expected_total:
        return _block(
            [f"The cart total of {_money(staged.total)} is an unexplained difference from expected {_money(expected_total)}."],
            differing_fields=["total"],
        )

    if not _coupon_is_eligible(staged):
        coupon = staged.coupon_applied or "unknown"
        return _block([f"Applied coupon {coupon} is not eligible for this cart."], differing_fields=["coupon_applied"])

    flags = scan_hidden_text(staged.hidden_text + (hidden_text or []))
    if flags:
        return Decision(
            result="ask",
            reasons=["The page contains hidden instruction-like text that needs review."],
            flags=flags,
        )
    return Decision(result="allow", reasons=["The food cart matches the authorized order."])
