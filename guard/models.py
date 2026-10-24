"""Data models for the AgentGuard shared JSON messages."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Route(BaseModel):
    model_config = ConfigDict(extra="forbid", serialize_by_alias=True)

    from_: str = Field(alias="from")
    to: str


class Requirements(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refundable: bool | None = None
    seat_confirmed: bool | None = None
    baggage: bool | None = None


class Contract(BaseModel):
    """The user's authorization for a booking."""

    model_config = ConfigDict(extra="forbid")

    route: Route
    date: str
    quantity: int = Field(ge=1)
    max_total: int = Field(ge=0)
    allow_extras: bool
    requirements: Requirements = Field(default_factory=Requirements)
    source: Literal["parsed", "fallback"] = "fallback"


class Item(BaseModel):
    """One staged cart item."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal["ticket", "insurance", "meal", "fee"]
    price: int = Field(ge=0)
    route: str | None = None
    date: str | None = None


class CartAttributes(Requirements):
    pass


class Cart(BaseModel):
    """The cart inspected before confirmation."""

    model_config = ConfigDict(extra="forbid")

    cart_id: str
    items: list[Item]
    total: int | None
    passengers: int | None = Field(default=None, ge=1)
    attributes: CartAttributes = Field(default_factory=CartAttributes)
    hidden_text: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    """A checker response using the shared decision JSON field names."""

    model_config = ConfigDict(extra="forbid")

    result: Literal["allow", "block", "ask"]
    reasons: list[str] = Field(default_factory=list)
    remove_item_ids: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    differing_fields: list[str] = Field(default_factory=list)
