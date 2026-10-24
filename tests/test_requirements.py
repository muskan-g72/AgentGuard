import pytest

from guard.checker import check
from guard.models import Cart, Contract
from guard.scenarios import CONTRACT, SCENARIOS


FIELDS = ("refundable", "seat_confirmed", "baggage")


def pair(requirements, attributes):
    contract = Contract.model_validate(CONTRACT.model_dump() | {"requirements": requirements})
    cart = Cart.model_validate(SCENARIOS["s1"][0].model_dump() | {"attributes": attributes})
    return contract, cart


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("required", [True, False])
def test_known_requirement_mismatch_blocks(field, required):
    decision = check(*pair({field: required}, {field: not required}))
    assert decision.result == "block"
    assert decision.differing_fields == [f"attributes.{field}"]
    assert "but you asked for" in decision.reasons[0]


def test_refundable_reason_is_plain():
    decision = check(*pair({"refundable": True}, {"refundable": False}))
    assert decision.reasons == ["Ticket is not refundable but you asked for refundable."]


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("required", [True, False])
def test_required_unknown_attribute_asks(field, required):
    decision = check(*pair({field: required}, {field: None}))
    assert decision.result == "ask"
    assert decision.differing_fields == [f"attributes.{field}"]


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("required", [True, False])
def test_matching_requirement_allows(field, required):
    assert check(*pair({field: required}, {field: required})).result == "allow"


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("actual", [True, False, None])
def test_unconstrained_attribute_never_blocks(field, actual):
    assert check(*pair({field: None}, {field: actual})).result == "allow"


def test_known_mismatch_outweighs_another_unknown_requirement():
    decision = check(*pair(
        {"refundable": True, "seat_confirmed": True},
        {"refundable": None, "seat_confirmed": False},
    ))
    assert decision.result == "block"
    assert decision.differing_fields == ["attributes.seat_confirmed"]


def test_requirement_unknown_cannot_weaken_forbidden_extra_block():
    contract, _ = pair({"refundable": True}, {})
    assert check(contract, SCENARIOS["s2"][0]).result == "block"
