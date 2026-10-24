"""Deterministic, network-free cart authorization checks."""

from __future__ import annotations

from decimal import Decimal

from .hidden_text import scan_hidden_text
from .models import Cart, Contract, Decision, Item


def _money(amount: Decimal) -> str:
    """Format an exact decimal amount for a user-facing reason."""

    return f"Rs {amount:,.2f}" if amount % 1 else f"Rs {amount:,.0f}"


def _item_name(item: Item) -> str:
    return {
        "insurance": "Travel insurance",
        "meal": "Priority meal",
        "fee": "Convenience fee",
        "ticket": "Ticket",
    }[item.type]


def _block(reasons: list[str], remove_item_ids: list[str] | None = None) -> Decision:
    return Decision(result="block", reasons=reasons, remove_item_ids=remove_item_ids or [])


def check(contract: Contract, cart: Cart, hidden_text: list[str] = []) -> Decision:
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
    if missing:
        return Decision(result="ask", reasons=missing)

    # 2. Ticket route and date.
    matching_tickets = [
        item for item in ticket_items if item.route == contract.route and item.date == contract.date
    ]
    if len(matching_tickets) != 1:
        return _block([
            f"The cart must contain exactly one ticket for {contract.route} on {contract.date}."
        ])

    # 3. Quantity.
    if len(ticket_items) != contract.quantity:
        return _block([
            f"The cart has {len(ticket_items)} ticket item(s), but {contract.quantity} were authorized."
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
    item_sum = sum((item.price for item in cart.items), start=Decimal("0"))
    if cart.total != item_sum:
        return _block([
            f"The cart total of {_money(cart.total)} does not match the item total of {_money(item_sum)}."
        ])

    # 7. Suspicious hidden instructions can tighten an otherwise allow decision.
    flags = scan_hidden_text(hidden_text)
    if flags:
        return Decision(
            result="ask",
            reasons=["The page contains hidden instruction-like text that needs review."],
            flags=flags,
        )
    return Decision(result="allow", reasons=["The cart matches the authorized booking."])
