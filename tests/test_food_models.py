"""Food models retain strict v2 money and represent missing cart evidence."""

import pytest
from pydantic import ValidationError

from guard.food_models import StagedFoodCart


def cart(**changes):
    body = {
        "cart_id": "foodhub-1",
        "items": [{"id": "dish", "type": "dish", "price": 280, "veg": True}],
        "coupon_applied": None,
        "quantity": 1,
        "total": 280,
        "eta_minutes": 35,
        "veg": True,
    }
    body.update(changes)
    return StagedFoodCart.model_validate(body)


def test_staged_food_cart_keeps_missing_total_and_quantity_as_unknown():
    staged = cart(quantity=None, total=None)
    assert staged.quantity is None
    assert staged.total is None


@pytest.mark.parametrize("field,value", [("total", 280.0), ("quantity", 1.0)])
def test_staged_food_cart_rejects_decimal_money_and_quantity(field, value):
    with pytest.raises(ValidationError):
        cart(**{field: value})


def test_item_level_veg_evidence_is_optional_but_strict_boolean():
    assert cart(items=[{"id": "dish", "type": "dish", "price": 280}]).items[0].veg is None
    with pytest.raises(ValidationError):
        cart(items=[{"id": "dish", "type": "dish", "price": 280, "veg": 1}])
