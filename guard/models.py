"""Data models for the AgentGuard shared JSON messages."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    """The user's authorization for a booking."""

    model_config = ConfigDict(extra="forbid")

    route: str
    date: str
    quantity: int = Field(ge=1)
    max_total: Decimal = Field(ge=0)
    allow_extras: bool


class Item(BaseModel):
    """One staged cart item."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal["ticket", "insurance", "meal", "fee"]
    price: Decimal = Field(ge=0)
    route: str | None = None
    date: str | None = None


class Cart(BaseModel):
    """The cart inspected before confirmation."""

    model_config = ConfigDict(extra="forbid")

    cart_id: str
    items: list[Item]
    total: Decimal | None
    passengers: int | None = Field(default=None, ge=1)


class Decision(BaseModel):
    """A checker response using the shared decision JSON field names."""

    model_config = ConfigDict(extra="forbid")

    result: Literal["allow", "block", "ask"]
    reasons: list[str] = Field(default_factory=list)
    remove_item_ids: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
