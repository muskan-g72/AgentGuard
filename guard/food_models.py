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
    priority: Literal["price", "taste"]


class Coupon(Message):
    code: str = Field(min_length=1)
    type: Literal["flat", "percent"]
    value: Money
    max_discount: Money | None = None
    min_order: Money


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


class StagedFoodCart(Message):
    """Food cart evidence. It intentionally does not change ``Cart``."""

    cart_id: str = Field(min_length=1)
    items: list[FoodItem]
    coupon_applied: str | None = None
    quantity: Count
    total: Money
    eta_minutes: int = Field(strict=True, ge=0)
    veg: bool
    hidden_text: list[str] = Field(default_factory=list)
