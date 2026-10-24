from __future__ import annotations

import time

import pytest

from guard.checker import check
from guard.scenarios import CONTRACT, SCENARIOS


@pytest.fixture
def s1():
    return SCENARIOS["s1"]


@pytest.fixture
def s2():
    return SCENARIOS["s2"]


@pytest.fixture
def s2_after_fix():
    return SCENARIOS["s2-after-fix"]


@pytest.fixture
def s3():
    return SCENARIOS["s3"]


@pytest.fixture
def s4():
    return SCENARIOS["s4"]


@pytest.fixture
def s5():
    return SCENARIOS["s5"]


@pytest.fixture
def s6():
    return SCENARIOS["s6"]


def decision_for(fixture_value):
    cart, hidden_text = fixture_value
    return check(CONTRACT, cart, hidden_text)


def test_s1_allows(s1):
    assert decision_for(s1).result == "allow"


def test_s2_blocks_and_removes_extras(s2):
    decision = decision_for(s2)
    assert decision.result == "block"
    assert decision.remove_item_ids == ["x1", "m1"]
    assert "Travel insurance costs Rs 250" in decision.reasons[0]
    assert "Priority meal costs Rs 100" in decision.reasons[1]


def test_s2_after_fix_allows(s2_after_fix):
    assert decision_for(s2_after_fix).result == "allow"


def test_s3_blocks(s3):
    assert decision_for(s3).result == "block"


def test_s4_blocks_wrong_date(s4):
    assert decision_for(s4).result == "block"


def test_s5_asks_with_flag(s5):
    decision = decision_for(s5)
    assert decision.result == "ask"
    assert decision.flags


def test_s6_asks_for_missing_information(s6):
    decision = decision_for(s6)
    assert decision.result == "ask"
    assert "cart total is missing" in " ".join(decision.reasons).lower()
    assert "passenger count is missing" in " ".join(decision.reasons).lower()


def test_check_is_well_under_ten_milliseconds(s1):
    cart, hidden_text = s1
    start = time.perf_counter()
    for _ in range(1_000):
        check(CONTRACT, cart, hidden_text)
    average_ms = (time.perf_counter() - start) * 1_000 / 1_000
    assert average_ms < 10
