"""Deterministic checks for a staged food cart. No network or LLM access."""

from __future__ import annotations

from .food_models import FoodContract, StagedFoodCart
from .models import Decision


def check_food_cart(contract: FoodContract, cart: StagedFoodCart, expected_effective_price: int) -> Decision:
    """Check the selected dish, known extras, and the expected clean cart price."""

    reasons: list[str] = []
    differing: list[str] = []
    extras = [item for item in cart.items if item.type in {"tip", "donation", "membership"}]
    dish_items = [item for item in cart.items if item.type == "dish"]
    if len(dish_items) != 1:
        reasons.append("The cart must contain exactly one dish item.")
        differing.append("items")
    if cart.quantity != contract.quantity:
        reasons.append(f"The cart quantity {cart.quantity} differs from the authorized quantity {contract.quantity}.")
        differing.append("quantity")
    if contract.diet == "veg" and not cart.veg:
        reasons.append("The staged dish is not vegetarian.")
        differing.append("veg")
    if cart.eta_minutes > contract.max_eta_minutes:
        reasons.append(f"The ETA {cart.eta_minutes} exceeds the authorized {contract.max_eta_minutes} minutes.")
        differing.append("eta_minutes")
    if not contract.allow_extras and extras:
        labels = {"tip": "Tip", "donation": "Donation", "membership": "Membership"}
        reasons.extend(f"{labels[item.type]} costs Rs {item.price} and was not authorized." for item in extras)
        differing.append("items")
    if cart.total != sum(item.price for item in cart.items):
        reasons.append("The cart total does not match the item total.")
        differing.append("total")
    clean_total = cart.total - sum(item.price for item in extras)
    if clean_total != expected_effective_price:
        reasons.append(f"The clean cart total Rs {clean_total} differs from the expected Rs {expected_effective_price}.")
        differing.append("total")
    if cart.total > contract.max_total and not extras:
        reasons.append(f"Total Rs {cart.total} is over your Rs {contract.max_total} budget.")
        differing.append("total")
    if reasons:
        return Decision(
            result="block", reasons=reasons, remove_item_ids=[item.id for item in extras],
            differing_fields=list(dict.fromkeys(differing)),
        )
    if cart.hidden_text:
        return Decision(result="ask", reasons=["The page contains hidden text that needs review."], flags=["hidden_text"])
    return Decision(result="allow", reasons=["The food cart matches the authorized option."])
