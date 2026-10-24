"""Pure coupon math and rating shrinkage. Money arithmetic stays integer-only."""

from __future__ import annotations

from fractions import Fraction

from .models import FoodOption, PriceBreakdown


def effective_price(option: FoodOption) -> PriceBreakdown:
    """Apply one best eligible coupon; percentage discounts round down.

    Eligibility uses item_price alone, excluding delivery/platform/packaging.
    Tips, donations and memberships have no place in the comparison price.
    """
    option = FoodOption.model_validate(option)
    unknown = [name for name, value in (
        ("item_price", option.item_price), ("fees.delivery", option.fees.delivery),
        ("fees.platform", option.fees.platform), ("fees.packaging", option.fees.packaging),
    ) if value is None]
    if unknown:
        raise ValueError("Price is unknown at " + ", ".join(unknown) + ".")
    subtotal = option.item_price + option.fees.delivery + option.fees.platform + option.fees.packaging
    discount, code = 0, None
    for coupon in sorted(option.coupons, key=lambda coupon: coupon.code):
        if option.item_price < coupon.min_order:
            continue
        value = coupon.value if coupon.type == "flat" else min(
            option.item_price * coupon.value // 100, coupon.max_discount,
        )
        if value > discount:
            discount, code = value, coupon.code
    if discount > subtotal:
        raise ValueError("The best eligible coupon exceeds the payable subtotal.")
    return PriceBreakdown(subtotal=subtotal, discount=discount,
                          effective_price=subtotal - discount, coupon_code=code)


def taste_fraction(option: FoodOption) -> Fraction | None:
    """Use exact rational values for stable ranking, without rounding first."""
    option = FoodOption.model_validate(option)
    if option.rating is None or option.rating_count is None:
        return None
    return (Fraction(str(option.rating)) * option.rating_count + Fraction("3.8") * 50) / (option.rating_count + 50)


def taste_score(option: FoodOption) -> float | None:
    """A review-count-adjusted proxy, never a claim about actual food quality."""
    score = taste_fraction(option)
    return float(score) if score is not None else None
