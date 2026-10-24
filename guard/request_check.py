"""Compare the outgoing order payload to the authorized cart, without I/O."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import ValidationError

from .checker import check
from .models import Cart, Contract, Decision, OrderRequest


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def cart_hash(cart: Cart | dict) -> str:
    cart = Cart.model_validate(cart)
    return hashlib.sha256(canonical_json(cart.model_dump(mode="json")).encode("utf-8")).hexdigest()


def request_check(
    contract: Contract | dict, cart: Cart | dict, order_request: OrderRequest | dict,
    allowed_cart_hash: str | None,
) -> Decision:
    try:
        contract = Contract.model_validate(contract)
        cart = Cart.model_validate(cart)
        request = OrderRequest.model_validate(order_request)
        current_hash = cart_hash(cart)
        canonical_json(request.model_dump(mode="json"))
    except (ValidationError, ValueError, TypeError):
        return Decision(result="block", reasons=["Invalid outgoing order request or cart."], flags=["invalid_input"])
    if not allowed_cart_hash or current_hash != allowed_cart_hash:
        return Decision(result="block", reasons=["The cart has changed since authorization."], differing_fields=["cart_hash"])
    decision = check(contract, cart)
    if decision.result != "allow":
        return decision
    differing = []
    if request.cart_id != cart.cart_id:
        differing.append("cart_id")
    expected = {item.id: item.price for item in cart.items}
    actual = {item.id: item.price for item in request.items}
    if len(actual) != len(request.items) or actual != expected:
        differing.append("items")
    if request.total != cart.total or request.total != sum(item.price for item in request.items):
        differing.append("total")
    # Extra form fields have no authorization in this demo contract.
    if request.fields:
        differing.extend(f"fields.{key}" for key in sorted(request.fields))
    if differing:
        return Decision(
            result="block", reasons=[f"Outgoing order differs at {field}." for field in differing],
            differing_fields=differing,
        )
    return Decision(result="allow", reasons=["The outgoing request matches the authorized cart."])
