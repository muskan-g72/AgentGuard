from __future__ import annotations

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
    assert isinstance(cart.total, int)
    assert [(item.type, item.price) for item in cart.items[1:]] == [
        ("insurance", 250),
        ("meal", 100),
    ]
    assert hidden_text == []
    decision = check(DEMO_CONTRACT, cart, hidden_text)
    assert decision.result == "block"
    assert decision.remove_item_ids == ["x1", "m1"]


def test_stage_returns_integer_money_in_replay(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setenv("REPLAY", "1")
    response = TestClient(app).post(
        "/stage",
        json={"cart_url": "http://localhost:8000/checkout.html", "scenario": "s2"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cart"]["total"] == 1350
    assert isinstance(body["cart"]["total"], int)
    assert all(isinstance(item["price"], int) for item in body["cart"]["items"])


def test_stage_fails_closed_when_guard_is_unavailable(monkeypatch):
    from fastapi.testclient import TestClient
    import app.main as main

    events = []
    monkeypatch.setattr(main, "_GUARD_AVAILABLE", False)
    monkeypatch.setattr(main, "log_event", lambda _task_id, kind, _payload: events.append(kind))
    response = TestClient(main.app).post(
        "/stage",
        json={"cart_url": "http://localhost:8000/checkout.html", "scenario": "s2"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["result"] == "block"
    assert "guard_stubbed" in events
