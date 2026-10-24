"""Pure, deterministic ranking for already-extracted food options."""

from __future__ import annotations

from decimal import Decimal

from .food_models import Coupon, FoodContract, FoodOption


def _coupon_discount(option: FoodOption, coupon: Coupon) -> int | None:
    """Return a coupon saving only when it is eligible on item price."""

    if option.item_price < coupon.min_order:
        return None
    if coupon.type == "flat":
        return coupon.value
    discount = option.item_price * coupon.value // 100
    return min(discount, coupon.max_discount) if coupon.max_discount is not None else discount


def eligible_coupon(option: FoodOption) -> Coupon | None:
    """Return the best eligible coupon, deterministically breaking ties by code."""

    choices = [
        (coupon, discount)
        for coupon in option.coupons
        if (discount := _coupon_discount(option, coupon)) is not None
    ]
    if not choices:
        return None
    return min(choices, key=lambda choice: (-choice[1], choice[0].code))[0]


def effective_price(option: FoodOption) -> int:
    """Item price plus listed fees less the best eligible coupon.

    Tips, donations, and memberships have no representation in ``FoodOption``;
    therefore none can affect a read-only comparison price.
    """

    coupon = eligible_coupon(option)
    discount = _coupon_discount(option, coupon) if coupon is not None else 0
    return option.item_price + option.fees.delivery + option.fees.platform + option.fees.packaging - (discount or 0)


def taste_score(option: FoodOption) -> float:
    """A rating-count-weighted proxy, never presented as ground truth."""

    rating = Decimal(str(option.rating))
    count = Decimal(option.rating_count)
    return float((rating * count + Decimal("3.8") * 50) / (count + 50))


def _dropped_reasons(contract: FoodContract, option: FoodOption, price: int) -> list[str]:
    reasons: list[str] = []
    if contract.diet == "veg" and not option.veg:
        reasons.append("not vegetarian")
    if option.rating < contract.min_rating:
        reasons.append(f"rating {option.rating:g} is below {contract.min_rating:g}")
    if option.eta_minutes > contract.max_eta_minutes:
        reasons.append(f"ETA {option.eta_minutes} exceeds {contract.max_eta_minutes} minutes")
    if price > contract.max_total:
        reasons.append(f"effective price Rs {price} exceeds Rs {contract.max_total}")
    return reasons


def _why(option: FoodOption, price: int) -> list[str]:
    coupon = eligible_coupon(option)
    coupon_reason = f"Applied eligible coupon {coupon.code}." if coupon else "No eligible coupon applies."
    return [
        "Vegetarian dish.",
        f"Rating {option.rating:g} meets the minimum.",
        f"ETA {option.eta_minutes} minutes is within the maximum.",
        f"Effective price is Rs {price}.",
        coupon_reason,
    ]


def _identity(option: FoodOption) -> tuple[str, str, str, str]:
    return option.platform, option.restaurant, option.dish, option.url


def rank(contract: FoodContract, options: list[FoodOption]) -> dict:
    """Drop disallowed options and rank survivors without I/O or an LLM.

    ``ranked`` records the actual derived values and selection explanation;
    ``dropped`` preserves every disqualifying reason for auditability.
    """

    ranked: list[dict] = []
    dropped: list[dict] = []
    for option in options:
        price = effective_price(option)
        reasons = _dropped_reasons(contract, option, price)
        if reasons:
            dropped.append({"option": option, "reasons": reasons})
            continue
        ranked.append({
            "option": option,
            "effective_price": price,
            "taste_score": taste_score(option),
            "why": _why(option, price),
        })

    if contract.priority == "price":
        ranked.sort(key=lambda entry: (
            entry["effective_price"], -entry["taste_score"], _identity(entry["option"]),
        ))
    else:
        ranked.sort(key=lambda entry: (
            -entry["taste_score"], entry["effective_price"], _identity(entry["option"]),
        ))
    return {"ranked": ranked, "dropped": dropped}
