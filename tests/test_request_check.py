import json

import pytest

from guard.models import Contract, OrderRequest
from guard.request_check import check_request
from guard.scenarios import CONTRACT


HOST = "demo-booking-tau.vercel.app"


@pytest.fixture
def body():
    return {"cart_id": "c_001", "items": [{"id": "t1", "price": 1000}], "total": 1000, "fields": {}}


def test_exact_budget_and_allowed_host_item_are_allowed(body):
    decision = check_request(CONTRACT, body, HOST)
    assert decision.result == "allow"
    assert decision.differing_fields == []


def test_one_rupee_over_budget_blocks_with_exact_field(body):
    body["total"] = body["items"][0]["price"] = 1001
    decision = check_request(CONTRACT, body, HOST)
    assert decision.result == "block"
    assert decision.differing_fields == ["total"]


@pytest.mark.parametrize("host", [
    "evil.example", HOST + ".evil.example", "prefix-" + HOST, "evil." + HOST,
    "https://" + HOST, HOST + ":443", HOST + "/checkout", HOST + "@evil.example", "localhost.evil.example", None,
])
def test_host_allowlist_is_exact_and_never_substring(body, host):
    decision = check_request(CONTRACT, body, host)
    assert decision.result == "block"
    assert decision.differing_fields == ["request_host"]


@pytest.mark.parametrize("item_id", ["x1", "m1", "f1", "t1-insurance", "unknown"])
def test_forbidden_extra_or_unknown_item_id_blocks(body, item_id):
    body["items"].append({"id": item_id, "price": 0})
    decision = check_request(CONTRACT, body, HOST)
    assert decision.result == "block"
    assert decision.differing_fields == ["items[1].id"]


def test_authorized_extra_is_allowed_but_unknown_id_still_blocks(body):
    contract = Contract.model_validate(CONTRACT.model_dump() | {"allow_extras": True})
    body["items"].append({"id": "x1", "price": 0})
    assert check_request(contract, body, HOST).result == "allow"
    body["items"][1]["id"] = "x1-other"
    assert check_request(contract, body, HOST).result == "block"


@pytest.mark.parametrize("location,expected", [
    ("top", "coupon"), ("item", "items[0].type"), ("fields", "fields.insurance"),
])
def test_unexpected_fields_block_at_exact_path(body, location, expected):
    if location == "top":
        body["coupon"] = "SURPRISE"
    elif location == "item":
        body["items"][0]["type"] = "ticket"
    else:
        body["fields"]["insurance"] = False
    decision = check_request(CONTRACT, body, HOST)
    assert decision.result == "block"
    assert decision.differing_fields == [expected]


@pytest.mark.parametrize("body", [None, "", b"\xff", "{broken", "[]", "null", [], 42, {}, '{"total":NaN}', '{"total":1,"total":2}'])
def test_missing_or_unparsable_body_asks(body):
    assert check_request(CONTRACT, body, HOST).result == "ask"


@pytest.mark.parametrize("field", ["cart_id", "items", "total", "fields"])
def test_missing_body_field_asks_with_exact_path(body, field):
    del body[field]
    decision = check_request(CONTRACT, body, HOST)
    assert decision.result == "ask"
    assert decision.differing_fields == [field]


@pytest.mark.parametrize("field,value,path", [
    ("total", "1000", "total"), ("total", 1000.0, "total"), ("total", True, "total"),
    ("cart_id", None, "cart_id"), ("items", [None], "items[0]"),
    ("items", [{"id": "t1", "price": 1.5}], "items[0].price"),
])
def test_invalid_body_values_never_allow(body, field, value, path):
    body[field] = value
    decision = check_request(CONTRACT, body, HOST)
    assert decision.result == "ask"
    assert decision.differing_fields == [path]


def test_known_violation_beats_missing_body_evidence(body):
    del body["cart_id"]
    body["fields"]["extra"] = True
    decision = check_request(CONTRACT, body, HOST)
    assert decision.result == "block"
    assert decision.differing_fields == ["fields.extra", "cart_id"]
    assert check_request(CONTRACT, None, "evil.example").result == "block"


def test_duplicate_item_id_blocks(body):
    body["items"].append({"id": "t1", "price": 0})
    decision = check_request(CONTRACT, body, HOST)
    assert decision.result == "block"
    assert "items[1].id" in decision.differing_fields


def test_inconsistent_sum_blocks_even_within_budget(body):
    body["items"][0]["price"] = 999
    decision = check_request(CONTRACT, body, HOST)
    assert decision.result == "block"
    assert decision.differing_fields == ["total"]


def test_empty_items_cannot_allow(body):
    body.update(items=[], total=0)
    assert check_request(CONTRACT, body, HOST).result == "block"


def test_json_bytes_and_model_bodies_are_supported(body):
    for request in [json.dumps(body), json.dumps(body).encode(), OrderRequest.model_validate(body)]:
        assert check_request(CONTRACT, request, HOST).result == "allow"


def test_request_check_does_not_mutate_inputs(body):
    before = json.dumps(body)
    check_request(CONTRACT, body, HOST)
    assert json.dumps(body) == before
