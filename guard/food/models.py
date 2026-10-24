"""Food comparison inputs; these are not Schema v2 authorization contracts."""

from __future__ import annotations

from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import ConfigDict, Field, field_validator, model_validator

from guard.models import Count, Message, Money

Platform = Literal["FoodHub", "QuickBite", "DineDash"]
PLATFORMS: tuple[Platform, ...] = ("FoodHub", "QuickBite", "DineDash")
Rating = Annotated[float, Field(ge=0, le=5, allow_inf_nan=False)]
NonnegativeInt = Annotated[int, Field(strict=True, ge=0)]


class FoodMessage(Message):
    model_config = ConfigDict(revalidate_instances="always")


class FoodCriteria(FoodMessage):
    """Read-only filters, never authorization to stage or place an order.

    Pricing is defined for one serving in this first food comparison pass.
    """

    diet: Literal["veg"] = "veg"
    quantity: Count = Field(default=1, le=1)
    max_total: Money = 300
    min_rating: Rating = 4.2
    max_eta_minutes: NonnegativeInt = 45
    allow_extras: bool = False
    priority: Literal["price", "taste"] = "price"

    @field_validator("allow_extras")
    @classmethod
    def no_extras(cls, value: bool) -> bool:
        if value:
            raise ValueError("Food comparison does not authorize extras")
        return value


class Fees(FoodMessage):
    delivery: Money | None
    platform: Money | None
    packaging: Money | None


class Coupon(FoodMessage):
    code: str = Field(min_length=1)
    type: Literal["flat", "percent"]
    value: Money
    max_discount: Money | None
    min_order: Money

    @model_validator(mode="after")
    def valid_percentage(self):
        if self.type == "percent" and self.value > 100:
            raise ValueError("Percentage coupons cannot exceed 100 percent")
        if self.type == "percent" and self.max_discount is None:
            raise ValueError("Percentage coupons need a known max_discount")
        return self


class FoodOption(FoodMessage):
    platform: Platform
    restaurant: str = Field(min_length=1)
    dish: str = Field(min_length=1)
    veg: bool | None
    item_price: Money | None
    rating: Rating | None
    rating_count: NonnegativeInt | None
    eta_minutes: NonnegativeInt | None
    fees: Fees
    coupons: list[Coupon]
    review_snippets: list[str]
    url: str

    @field_validator("url")
    @classmethod
    def https_option_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("An option must have an HTTPS URL without embedded credentials")
        return value

    @model_validator(mode="after")
    def unique_coupon_codes(self):
        codes = [coupon.code for coupon in self.coupons]
        if len(codes) != len(set(codes)):
            raise ValueError("Coupon codes must be unique per option")
        return self


class PriceBreakdown(FoodMessage):
    subtotal: Money
    discount: Money
    effective_price: Money
    coupon_code: str | None


class RankedOption(FoodMessage):
    option: FoodOption
    effective_price: Money
    discount: Money
    coupon_code: str | None
    taste_score: Rating | None


class RejectedOption(FoodMessage):
    index: NonnegativeInt
    platform: Platform | None
    restaurant: str | None
    dish: str | None
    reasons: list[str]


class Ranking(FoodMessage):
    ranked: list[RankedOption]
    rejected: list[RejectedOption]
