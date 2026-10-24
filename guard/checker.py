"""Deterministic, network-free cart authorization checks."""

from __future__ import annotations

from .hidden_text import scan_hidden_text
from .models import Cart, Contract, Decision, Item, Route
from .food_models import FoodContract, StagedFoodCart


def _money(amount: int) -> str:
    """Format whole rupees without changing their representation."""

    return f"Rs {amount:,}"


def _item_name(item: Item) -> str:
    return {
        "insurance": "Travel insurance",
        "meal": "Priority meal",
        "fee": "Convenience fee",
        "ticket": "Ticket",
    }[item.type]


def _block(reasons: list[str], remove_item_ids: list[str] | None = None) -> Decision:
    return Decision(result="block", reasons=reasons, remove_item_ids=remove_item_ids or [])


def check(contract: Contract, cart: Cart, hidden_text: list[str] | None = None) -> Decision:
    """Compare a staged cart with a contract in a fixed, explainable order.

    This function is pure logic. It reads no environment variables and makes no
    network calls. A hidden-text finding is considered only after the cart passes
    every cart rule, so it cannot weaken a block.
    """

    # 1. Missing information.
    missing: list[str] = []
    ticket_items = [item for item in cart.items if item.type == "ticket"]
    if cart.total is None:
        missing.append("The cart total is missing.")
    if not ticket_items:
        missing.append("The ticket item is missing.")
    if cart.passengers is None:
        missing.append("The passenger count is missing.")
    if any(item.route is None for item in ticket_items):
        missing.append("The ticket route is missing.")
    if any(item.date is None for item in ticket_items):
        missing.append("The ticket date is missing.")
    if missing:
        return Decision(result="ask", reasons=missing)

    # 2. Ticket route and date.
    route_label = f"{contract.route.from_}-{contract.route.to}"

    def matches_route(route: Route | str | None) -> bool:
        return route == contract.route or route == route_label

    if len(ticket_items) != 1 or any(
        not matches_route(item.route) or item.date != contract.date for item in ticket_items
    ):
        return _block([
            f"The cart must contain exactly one ticket for {route_label} on {contract.date}."
        ])

    # 3. Quantity.
    if cart.passengers != contract.quantity:
        return _block([
            f"The cart has {cart.passengers} passenger(s), but {contract.quantity} were authorized."
        ])

    # 4. Extras.
    extras = [item for item in cart.items if item.type != "ticket"]
    if not contract.allow_extras and extras:
        return _block(
            [f"{_item_name(item)} costs {_money(item.price)} and was not authorized." for item in extras],
            [item.id for item in extras],
        )

    # 5. Budget.
    assert cart.total is not None  # Guaranteed by the missing-information rule.
    if cart.total > contract.max_total:
        return _block([
            f"The cart total of {_money(cart.total)} exceeds the authorized maximum of {_money(contract.max_total)}."
        ])

    # 6. Total consistency.
    item_sum = sum(item.price for item in cart.items)
    if cart.total != item_sum:
        return _block([
            f"The cart total of {_money(cart.total)} does not match the item total of {_money(item_sum)}."
        ])

    # 7. Known requirement violations outweigh unknown attributes.
    requirement_blocks: list[str] = []
    requirement_questions: list[str] = []
    blocked_fields: list[str] = []
    unknown_fields: list[str] = []
    descriptions = {
        "refundable": ("refundable", "not refundable"),
        "seat_confirmed": ("a confirmed seat", "no confirmed seat"),
        "baggage": ("baggage included", "no baggage included"),
    }
    for field, (positive, negative) in descriptions.items():
        required = getattr(contract.requirements, field)
        if required is None:
            continue
        actual = getattr(cart.attributes, field)
        if actual is None:
            detail = "is refundable" if field == "refundable" else f"has {positive}"
            requirement_questions.append(f"It is unknown whether the ticket {detail}.")
            unknown_fields.append(f"attributes.{field}")
        elif actual != required:
            verb = "is" if field == "refundable" else "has"
            observed = positive if actual else negative
            wanted = positive if required else negative
            reason = f"Ticket {verb} {observed} but you asked for {wanted}."
            requirement_blocks.append(reason)
            blocked_fields.append(f"attributes.{field}")
    if requirement_blocks:
        return Decision(result="block", reasons=requirement_blocks, differing_fields=blocked_fields)
    if requirement_questions:
        return Decision(result="ask", reasons=requirement_questions, differing_fields=unknown_fields)

    # 8. Suspicious hidden instructions can tighten an otherwise allow decision.
    flags = scan_hidden_text(cart.hidden_text + (hidden_text or []))
    if flags:
        return Decision(
            result="ask",
            reasons=["The page contains hidden instruction-like text that needs review."],
            flags=flags,
        )
    return Decision(result="allow", reasons=["The cart matches the authorized booking."])


def _food_extra_name(item_type: str) -> str:
    return {"tip": "Tip", "donation": "Donation", "membership": "Membership"}[item_type]


def _food_coupon_is_eligible(staged: StagedFoodCart) -> bool:
    """Verify an applied coupon from explicit checkout evidence only."""

    if staged.coupon_applied is None:
        return True
    coupon = staged.coupon_details
    if coupon is None or coupon.code != staged.coupon_applied:
        return False
    dish_price = sum(item.price for item in staged.items if item.type == "dish")
    return dish_price >= coupon.min_order


def check_food_cart(
    contract: FoodContract,
    staged: StagedFoodCart,
    expected_effective_price: int,
    hidden_text: list[str] | None = None,
) -> Decision:
    """Authorize staged food checkout evidence without network access or an LLM."""

    missing: list[str] = []
    if staged.total is None:
        missing.append("The cart total is missing.")
    if staged.quantity is None:
        missing.append("The quantity is missing.")
    if missing:
        return Decision(result="ask", reasons=missing)

    dish_items = [item for item in staged.items if item.type == "dish"]
    non_veg = [item for item in dish_items if item.veg is False]
    if contract.diet == "veg" and (staged.veg is False or non_veg):
        names = [item.id for item in non_veg]
        detail = f"Dish {names[0]} is not vegetarian." if names else "The staged dish is not vegetarian."
        return _block([detail])

    if staged.quantity != contract.quantity:
        return _block([
            f"The cart has quantity {staged.quantity}, but {contract.quantity} was authorized."
        ])

    extras = [item for item in staged.items if item.type in {"tip", "donation", "membership"}]
    if not contract.allow_extras and extras:
        return _block(
            [f"{_food_extra_name(item.type)} costs {_money(item.price)} and was not authorized." for item in extras],
            [item.id for item in extras],
        )

    assert staged.total is not None
    if staged.total > contract.max_total:
        return _block([
            f"The cart total of {_money(staged.total)} exceeds the authorized maximum of {_money(contract.max_total)}."
        ])

    expected = expected_effective_price + sum(item.price for item in extras)
    if staged.total != expected:
        return _block([
            f"The cart total of {_money(staged.total)} is an unexplained difference from expected {_money(expected)}."
        ])

    if not _food_coupon_is_eligible(staged):
        coupon = staged.coupon_applied or "unknown"
        return _block([f"Applied coupon {coupon} is not eligible for this cart."])

    flags = scan_hidden_text(staged.hidden_text + (hidden_text or []))
    if flags:
        return Decision(
            result="ask",
            reasons=["The page contains hidden instruction-like text that needs review."],
            flags=flags,
        )
    return Decision(result="allow", reasons=["The food cart matches the authorized order."])
