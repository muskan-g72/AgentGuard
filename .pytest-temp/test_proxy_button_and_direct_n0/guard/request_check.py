"""Inspect outgoing order bodies without a network or LLM call.

The v2 wire format supplies IDs, not item types. This demo's fixed inventory is
therefore the allowlist; unknown IDs fail closed. Callers must separately bind
this request to the cart hash that received an allow decision before commit.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from .models import Contract, Decision, OrderRequest


ALLOWED_HOSTS = frozenset({"demo-booking-tau.vercel.app", "127.0.0.1", "localhost"})
ITEM_TYPES = {
    "t1": "ticket", "t2": "ticket", "t3": "ticket",
    "x1": "insurance", "m1": "meal", "f1": "fee",
}


def _path(location: tuple) -> str:
    result = ""
    for part in location:
        result += f"[{part}]" if isinstance(part, int) else ("." if result else "") + str(part)
    return result


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON number: {value}")


def check_request(
    contract: Contract, order_request: OrderRequest | dict | str | bytes | None, request_host: str,
    *, allowed_hosts: frozenset[str] = ALLOWED_HOSTS,
) -> Decision:
    """Check host, fields, inventory, integer totals and budget in stable order.

    differing_fields uses exact JSON paths (for example items[0].id); the host
    argument is named request_host. No body, malformed JSON or an incomplete
    body asks for evidence. A known violation always takes priority over an ask.
    The only supported fields payload is {}, since no extra fields are authorized.
    """

    if not isinstance(request_host, str) or request_host not in allowed_hosts:
        return Decision(
            result="block", reasons=["The order host is not on the allowlist."],
            differing_fields=["request_host"],
        )

    if isinstance(order_request, OrderRequest):
        body = order_request.model_dump()
    elif isinstance(order_request, (str, bytes)):
        try:
            body = json.loads(order_request, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        except (ValueError, UnicodeError, RecursionError):
            return Decision(result="ask", reasons=["The order request body could not be parsed."], differing_fields=["body"])
    else:
        body = order_request
    if not isinstance(body, dict):
        return Decision(result="ask", reasons=["The order request body is missing or is not an object."], differing_fields=["body"])

    reasons: list[str] = []
    differing: list[str] = []
    missing: list[str] = []

    def block(field: str, reason: str) -> None:
        reasons.append(reason)
        if field not in differing:
            differing.append(field)

    try:
        request = OrderRequest.model_validate(body)
    except ValidationError as error:
        request = None
        for issue in error.errors():
            field = _path(issue["loc"])
            if issue["type"] == "extra_forbidden":
                block(field, f"Unexpected order field: {field}.")
            else:
                missing.append(field)

    fields = body.get("fields")
    if isinstance(fields, dict):
        for key in fields:
            block(f"fields.{key}", f"Unexpected order field: fields.{key}.")

    # Inspect known violations even in a partially malformed body.
    total = body.get("total")
    if type(total) is int and total > contract.max_total:
        block("total", f"Total Rs {total} is over your Rs {contract.max_total} budget.")
    items = body.get("items")
    seen: set[str] = set()
    ticket_count = 0
    if isinstance(items, list):
        if not items:
            block("items", "The order has no ticket items.")
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            if not isinstance(item_id, str):
                continue
            field = f"items[{index}].id"
            item_type = ITEM_TYPES.get(item_id)
            if item_id in seen:
                block(field, f"Duplicate order item: {item_id}.")
            seen.add(item_id)
            if item_type == "ticket":
                ticket_count += 1
            if item_type is None or (not contract.allow_extras and item_type != "ticket"):
                block(field, f"Order item {item_id} is not in the allowed set.")

    if request is not None:
        if ticket_count != 1:
            block("items", "The order must contain exactly one group ticket item.")
        if request.total != sum(item.price for item in request.items):
            block("total", "The order total does not match its item prices.")
    if reasons:
        return Decision(
            result="block", reasons=reasons,
            differing_fields=list(dict.fromkeys(differing + missing)),
        )
    if missing:
        return Decision(
            result="ask", reasons=["The order request has missing or invalid fields."],
            differing_fields=list(dict.fromkeys(missing)),
        )
    return Decision(result="allow", reasons=["The order request matches the authorized budget and allowed items."])
