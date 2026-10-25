"""Food-specific models kept separate from the shared train-cart schema."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .models import Count, Message, Money


class FoodContract(Message):
    """The authorization used to compare and stage a food order."""

    diet: Literal["veg"]
    quantity: Count
    max_total: Money
    min_rating: float = Field(ge=0, le=5)
    max_eta_minutes: int = Field(strict=True, ge=0)
    allow_extras: bool
    priority: Literal["price", "taste", "fastest", "value"]


class Coupon(Message):
    code: str = Field(min_length=1)
    type: Literal["flat", "percent"]
    value: Money
    max_discount: Money | None = None
    min_order: Money


class WalletEntry(Message):
    """A user-held credit that can apply only on its named platform."""

    platform: str = Field(min_length=1)
    kind: Literal["gift_voucher", "wallet_credit"]
    amount: Money
    min_order: Money
    code: str = Field(min_length=1)


class Fees(Message):
    delivery: Money
    platform: Money
    packaging: Money


class FoodOption(Message):
    platform: str = Field(min_length=1)
    restaurant: str = Field(min_length=1)
    dish: str = Field(min_length=1)
    veg: bool
    item_price: Money
    rating: float = Field(ge=0, le=5)
    rating_count: int = Field(strict=True, ge=0)
    eta_minutes: int = Field(strict=True, ge=0)
    fees: Fees
    coupons: list[Coupon] = Field(default_factory=list)
    review_snippets: list[str] = Field(default_factory=list)
    url: str = Field(min_length=1)


class FoodItem(Message):
    id: str = Field(min_length=1)
    type: Literal["dish", "tip", "donation", "membership", "fee"]
    price: Money
    # A platform may expose vegetarian evidence per dish or only as a cart-wide
    # flag. Unknown remains explicit rather than being coerced to false.
    veg: bool | None = None


class StagedFoodCart(Message):
    """Food cart evidence. It intentionally does not change ``Cart``."""

    cart_id: str = Field(min_length=1)
    items: list[FoodItem]
    coupon_applied: str | None = None
    # ``None`` represents unavailable checkout evidence; the food checker then
    # returns ASK rather than treating it as an allowed zero.
    quantity: Count | None = None
    total: Money | None = None
    eta_minutes: int = Field(strict=True, ge=0)
    veg: bool
    # Coupon details are optional because some platforms only reveal a code in
    # the cart. A code without details is not assumed eligible by the checker.
    coupon_details: Coupon | None = None
    hidden_text: list[str] = Field(default_factory=list)
