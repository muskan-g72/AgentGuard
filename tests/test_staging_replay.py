from __future__ import annotations

import json

import pytest

from app import staging
from app.staging import stage_cart_details
from guard.checker import check
from guard.contract_parser import DEMO_CONTRACT


def test_s2_replay_stages_and_blocks_extras(monkeypatch):
    monkeypatch.setenv("REPLAY", "1")
    cart, hidden_text = stage_cart_details(
        "http://localhost:8000/checkout.html?scenario=s2&ticket=t1&insurance=1&meal=1&fee=0",
        DEMO_CONTRACT,
    )

    assert cart.total == 1350
    assert [(item.type, item.price) for item in cart.items[1:]] == [
        ("insurance", 250),
        ("meal", 100),
    ]
    assert hidden_text == []
    decision = check(DEMO_CONTRACT, cart, hidden_text)
    assert decision.result == "block"
    assert decision.remove_item_ids == ["x1", "m1"]


@pytest.fixture
def live_s2_response():
    raw = json.loads(staging._recording_path("s2").read_text(encoding="utf-8"))
    raw["result"]["checkout_html"] = (
        '<section id="cart">'
        '<div data-item-id="t1" data-item-type="ticket">T1</div>'
        '<div data-item-id="x1" data-item-type="insurance">Travel insurance</div>'
        '<div data-item-id="m1" data-item-type="meal">Priority meal</div>'
        '</section>'
    )
    raw["result"]["extraction_error"] = None
    return raw


def test_live_staging_cannot_overwrite_s2_replay(monkeypatch, tmp_path, live_s2_response):
    fixture_bytes = staging._recording_path("s2").read_bytes()
    fixture_path = tmp_path / "s2.json"
    fixture_path.write_bytes(fixture_bytes)
    monkeypatch.setattr(staging, "_RECORDINGS", tmp_path)
    monkeypatch.delenv("REPLAY", raising=False)
    monkeypatch.setattr(staging, "run_agent", lambda url, goal: live_s2_response)

    for _ in range(2):
        cart, _ = stage_cart_details(
            "https://demo-booking-tau.vercel.app/checkout.html?scenario=s2", DEMO_CONTRACT,
        )
        assert [item.id for item in cart.items] == ["t1", "x1", "m1"]

    assert fixture_path.read_bytes() == fixture_bytes
    recordings = list((tmp_path / "live").glob("s2_*.json"))
    assert len(recordings) == 2
    assert all(json.loads(path.read_text(encoding="utf-8")) == live_s2_response for path in recordings)
    monkeypatch.setenv("REPLAY", "1")
    replay_cart, _ = stage_cart_details("https://demo-booking-tau.vercel.app/?scenario=s2", DEMO_CONTRACT)
    assert replay_cart.total == 1350
    assert [item.id for item in replay_cart.items] == ["t1", "x1", "m1"]
    assert len(list((tmp_path / "live").glob("*.json"))) == 2


def test_live_recording_scenario_cannot_escape_live_directory(monkeypatch, tmp_path):
    fixture_path = tmp_path / "s2.json"
    fixture_path.write_text("stable fixture", encoding="utf-8")
    monkeypatch.setattr(staging, "_RECORDINGS", tmp_path)

    path = staging._save_recording("../s2", {"result": "raw response"})

    assert path.parent == tmp_path / "live"
    assert path.name.startswith("manual_")
    assert fixture_path.read_text(encoding="utf-8") == "stable fixture"


def test_item_ids_are_validated_from_rows_not_hardcoded(live_s2_response):
    replacements = {"t1": "ticket-42", "x1": "addon-A", "m1": "option-B"}
    result = live_s2_response["result"]
    for item in result["cart"]["items"]:
        old_id = item["id"]
        item["id"] = replacements[old_id]
        result["checkout_html"] = result["checkout_html"].replace(
            f'data-item-id="{old_id}"', f'data-item-id="{item["id"]}"',
        )

    cart, hidden_text = staging._parse(live_s2_response, verify_item_ids=True)

    assert [item.id for item in cart.items] == list(replacements.values())
    assert check(DEMO_CONTRACT, cart, hidden_text).remove_item_ids == ["addon-A", "option-B"]


@pytest.mark.parametrize("item_index, invented_id", [
    (0, "T1: Ludhiana-Delhi, 2026-10-25"),
    (1, "Travel insurance"),
    (1, "insurance"),
    (2, "Priority meal"),
    (2, "meal"),
    (1, ""),
])
def test_visible_names_and_types_are_not_row_ids(live_s2_response, item_index, invented_id):
    live_s2_response["result"]["cart"]["items"][item_index]["id"] = invented_id

    with pytest.raises(staging.StagingError, match="not a checkout row's data-item-id"):
        staging._parse(live_s2_response, verify_item_ids=True)


@pytest.mark.parametrize("problem, message", [
    ("missing_html", "Checkout HTML is missing"),
    ("no_rows", "no data-item-id rows"),
    ("empty_row_id", "empty data-item-id"),
    ("duplicate_row_id", "duplicate data-item-id"),
    ("duplicate_cart_id", "duplicate item ID"),
    ("missing_row_type", "different or missing checkout row type"),
    ("wrong_row_type", "different or missing checkout row type"),
])
def test_unverifiable_removal_targets_are_rejected(live_s2_response, problem, message):
    result = live_s2_response["result"]
    if problem == "missing_html":
        del result["checkout_html"]
    elif problem == "no_rows":
        result["checkout_html"] = '<section id="cart">Travel insurance</section>'
    elif problem == "empty_row_id":
        result["checkout_html"] = result["checkout_html"].replace('data-item-id="x1"', 'data-item-id=""')
    elif problem == "duplicate_row_id":
        result["checkout_html"] += '<div data-item-id="x1" data-item-type="insurance"></div>'
    elif problem == "duplicate_cart_id":
        result["cart"]["items"][2]["id"] = "x1"
    elif problem == "missing_row_type":
        result["checkout_html"] = result["checkout_html"].replace('data-item-type="insurance"', '')
    elif problem == "wrong_row_type":
        result["checkout_html"] = result["checkout_html"].replace('data-item-type="insurance"', 'data-item-type="meal"')

    with pytest.raises(staging.StagingError, match=message):
        staging._parse(live_s2_response, verify_item_ids=True)


@pytest.mark.parametrize("extraction_error", ["DOM attributes unavailable", "", 42])
def test_agent_extraction_problem_is_reported(extraction_error):
    raw = {"result": {"cart": None, "hidden_text": [], "checkout_html": None,
                      "extraction_error": extraction_error}}

    with pytest.raises(staging.StagingError, match="extraction"):
        staging._parse(raw, verify_item_ids=True)


def test_invalid_live_ids_retry_once_then_report_error(monkeypatch, tmp_path, live_s2_response):
    live_s2_response["result"]["cart"]["items"][1]["id"] = "Travel insurance"
    calls = []

    def run_agent(url, goal):
        calls.append(goal)
        return live_s2_response

    monkeypatch.delenv("REPLAY", raising=False)
    monkeypatch.setattr(staging, "_RECORDINGS", tmp_path)
    monkeypatch.setattr(staging, "run_agent", run_agent)

    with pytest.raises(staging.StagingError, match="after one extraction retry.*cannot be safely targeted"):
        stage_cart_details("https://demo-booking-tau.vercel.app/?scenario=s2", DEMO_CONTRACT)

    assert len(calls) == 2
    assert "Reinspect" in calls[1]
    assert len(list((tmp_path / "live").glob("*.json"))) == 2
    assert not (tmp_path / "s2.json").exists()


def test_valid_ids_can_be_extracted_on_retry(monkeypatch, tmp_path, live_s2_response):
    first_response = json.loads(json.dumps(live_s2_response))
    first_response["result"]["cart"]["items"][1]["id"] = "insurance"
    responses = iter([first_response, live_s2_response])
    monkeypatch.delenv("REPLAY", raising=False)
    monkeypatch.setattr(staging, "_RECORDINGS", tmp_path)
    monkeypatch.setattr(staging, "run_agent", lambda url, goal: next(responses))

    cart, _ = stage_cart_details("https://demo-booking-tau.vercel.app/?scenario=s2", DEMO_CONTRACT)

    assert [item.id for item in cart.items] == ["t1", "x1", "m1"]
    assert len(list((tmp_path / "live").glob("*.json"))) == 2
