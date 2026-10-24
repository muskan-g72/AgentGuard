"""Strict JSON models implementing docs/schema.md (Schema v2)."""

from __future__ import annotations

from datetime import date as Date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Money = Annotated[int, Field(strict=True, ge=0)]
Count = Annotated[int, Field(strict=True, ge=1)]
Identifier = Annotated[str, Field(min_length=1)]
Status = Literal[
    "awaiting_answers", "awaiting_confirmation", "staging", "checking",
    "blocked", "fixing", "allowed", "committing", "done", "failed",
]


class Message(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, populate_by_name=True,
        serialize_by_alias=True, revalidate_instances="always",
    )


class Route(Message):
    from_: Identifier = Field(alias="from")
    to: Identifier


class Requirements(Message):
    refundable: bool | None = None
    seat_confirmed: bool | None = None
    baggage: bool | None = None


def _iso_date(value: str) -> str:
    if Date.fromisoformat(value).isoformat() != value:
        raise ValueError("Use an ISO date in YYYY-MM-DD format")
    return value


class Contract(Message):
    route: Route
    date: str
    quantity: Count
    max_total: Money
    allow_extras: bool
    requirements: Requirements = Field(default_factory=Requirements)
    source: Literal["parsed", "fallback"]

    _date = field_validator("date")(_iso_date)


class Item(Message):
    id: Identifier
    type: Literal["ticket", "insurance", "meal", "fee"]
    price: Money
    route: Route | None = None
    date: str | None = None

    @field_validator("date")
    @classmethod
    def validate_date(cls, value: str | None) -> str | None:
        return _iso_date(value) if value is not None else None


class Cart(Message):
    cart_id: Identifier
    items: list[Item]
    total: Money | None
    passengers: Count | None = None
    attributes: Requirements = Field(default_factory=Requirements)
    hidden_text: list[str] = Field(default_factory=list)


class OrderItem(Message):
    id: Identifier
    price: Money


class OrderRequest(Message):
    cart_id: Identifier
    items: list[OrderItem]
    total: Money
    fields: dict[str, Any] = Field(default_factory=dict)


class Decision(Message):
    result: Literal["allow", "block", "ask"]
    reasons: list[str] = Field(default_factory=list)
    remove_item_ids: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    differing_fields: list[str] = Field(default_factory=list)


class Question(Message):
    key: Literal["refundable", "seat_confirmed", "baggage"]
    text: str
    options: list[str] = Field(default_factory=lambda: ["yes", "no", "don't care"])
