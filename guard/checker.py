"""Deterministic, network-free cart authorization. Unknown is never allow."""

from __future__ import annotations

from pydantic import ValidationError

from .hidden_text import scan_hidden_text
from .models import Cart, Contract, Decision


def check(contract: Contract | dict, cart: Cart | dict, hidden_text: list[str] | None = None) -> Decision:
    """Check known violations before missing information; scan both text sources."""
    try:
        contract = Contract.model_validate(contract)
        cart = Cart.model_validate(cart)
        if hidden_text is not None and (
            not isinstance(hidden_text, list) or any(not isinstance(s, str) for s in hidden_text)
        ):
            raise ValueError("Invalid hidden text")
    except (ValidationError, ValueError, TypeError):
        return Decision(result="block", reasons=["Invalid contract or cart data."], flags=["invalid_input"])

    violations: list[str] = []
    missing: list[str] = []
    differing: list[str] = []
    tickets = [item for item in cart.items if item.type == "ticket"]
    ids = [item.id for item in cart.items]
    if len(ids) != len(set(ids)):
        violations.append("Cart item IDs must be unique.")
        differing.append("items")
    if not tickets:
        missing.append("The ticket item is missing.")
    elif len(tickets) != contract.quantity:
        violations.append(f"The cart has {len(tickets)} ticket item(s), but {contract.quantity} were authorized.")
        differing.append("quantity")
    for item in tickets:
        if item.route is None:
            missing.append(f"The route for ticket {item.id} is unknown.")
        elif item.route != contract.route:
            violations.append(f"Ticket {item.id} has a different route from the authorized booking.")
            differing.append("route")
        if item.date is None:
            missing.append(f"The date for ticket {item.id} is unknown.")
        elif item.date != contract.date:
            violations.append(f"Ticket {item.id} is not for the authorized date {contract.date}.")
            differing.append("date")
    if cart.passengers is None:
        missing.append("The passenger count is missing.")
    elif cart.passengers != contract.quantity:
        violations.append(f"The passenger count {cart.passengers} differs from the authorized quantity {contract.quantity}.")
        differing.append("passengers")

    extras = [item for item in cart.items if item.type != "ticket"] if not contract.allow_extras else []
    names = {"insurance": "Travel insurance", "meal": "Priority meal", "fee": "Convenience fee"}
    for item in extras:
        violations.append(f"{names[item.type]} costs Rs {item.price:,} and was not authorized.")
    if extras:
        differing.append("items")
    if cart.total is None:
        missing.append("The cart total is missing.")
    else:
        if cart.total > contract.max_total:
            violations.append(f"Total Rs {cart.total} is over your Rs {contract.max_total} budget.")
            differing.append("total")
        if cart.total != sum(item.price for item in cart.items):
            violations.append("The cart total does not match the item total.")
            differing.append("total")

    for name in type(contract.requirements).model_fields:
        required = getattr(contract.requirements, name)
        actual = getattr(cart.attributes, name)
        if required is None:
            continue
        if actual is None:
            missing.append(f"The ticket's {name} attribute is unknown.")
        elif actual != required:
            violations.append(f"The ticket's {name} attribute must be {str(required).lower()}.")
            differing.append(f"attributes.{name}")

    hidden_flags = scan_hidden_text(cart.hidden_text + (hidden_text or []))
    flags = ["hidden_text"] if hidden_flags else []
    if hidden_flags:
        missing.append("The page contains hidden instruction-like text that needs review.")
    if violations:
        return Decision(
            result="block", reasons=violations + missing,
            remove_item_ids=[item.id for item in extras], flags=flags,
            differing_fields=list(dict.fromkeys(differing)),
        )
    if missing:
        return Decision(result="ask", reasons=missing, flags=flags)
    return Decision(result="allow", reasons=["The cart matches the authorized booking."])
