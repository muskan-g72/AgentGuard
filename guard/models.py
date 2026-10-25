"""Data models for the AgentGuard shared JSON messages."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


Money = Annotated[int, Field(strict=True, ge=0)]
Count = Annotated[int, Field(strict=True, ge=1)]


class Message(BaseModel):
    """Reject extra fields and coercions at the authorization boundary."""

    model_config = ConfigDict(extra="forbid", strict=True, serialize_by_alias=True)


class Route(Message):
    from_: str = Field(alias="from", min_length=1)
    to: str = Field(min_length=1)


class Requirements(Message):
    """True means required, false means prohibited, and null means don't care."""

    refundable: bool | None = None
    seat_confirmed: bool | None = None
    baggage: bool | None = None


class Attributes(Requirements):
    """Here null means the cart attribute is unknown."""


class Contract(Message):
    """The user's authorization for a booking."""

    route: Route
    date: str
    quantity: Count
    max_total: Money
    allow_extras: bool
    requirements: Requirements = Field(default_factory=Requirements)
    source: Literal["parsed", "fallback"]


class Item(Message):
    """One staged cart item."""

    id: str
    type: Literal["ticket", "insurance", "meal", "fee"]
    price: Money
    # Existing checkout/replay evidence uses a station-pair string. Native v2
    # producers may use the structured contract route instead.
    route: Route | str | None = None
    date: str | None = None


class Cart(Message):
    """The cart inspected before confirmation."""

    cart_id: str
    items: list[Item]
    total: Money | None
    passengers: Count | None = None
    attributes: Attributes = Field(default_factory=Attributes)
    hidden_text: list[str] = Field(default_factory=list)


class RequestItem(Message):
    id: str
    price: Money


class OrderRequest(Message):
    cart_id: str = Field(min_length=1)
    items: list[RequestItem]
    total: Money
    fields: dict[str, object]


class Decision(Message):
    """A checker response using the shared decision JSON field names."""

    result: Literal["allow", "block", "ask"]
    reasons: list[str] = Field(default_factory=list)
    remove_item_ids: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    differing_fields: list[str] = Field(default_factory=list)
