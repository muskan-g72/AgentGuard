from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.tasks import InvalidTransitionError, task_events, transition


@pytest.fixture
def client():
    return TestClient(main.app)


def create(client, **extra):
    body = {"sentence": "Book one Ludhiana to Delhi ticket", "scenario": "s1", "guard_enabled": True}
    body.update(extra)
    response = client.post("/tasks", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_task_happy_path_through_confirm(client):
    created = create(client)
    confirmed = client.post(f"/tasks/{created['task_id']}/confirm", json={})
    assert confirmed.status_code == 200
    assert confirmed.json() == {"status": "awaiting_confirmation"}
    task = client.get(f"/tasks/{created['task_id']}").json()
    assert task["contract"]["source"] in {"parsed", "fallback"}
    assert task["status"] == "awaiting_confirmation"


def test_illegal_transition_is_rejected_and_logged(client):
    task_id = create(client)["task_id"]
    with pytest.raises(InvalidTransitionError, match="awaiting_confirmation -> done"):
        transition(task_id, "done")
    assert task_events(task_id)[-1]["type"] == "transition_rejected"


def test_invalid_contract_is_rejected(client):
    task_id = create(client)["task_id"]
    contract = client.get(f"/tasks/{task_id}").json()["contract"]
    contract["max_total"] = 0
    contract["unknown"] = True
    response = client.post(f"/tasks/{task_id}/confirm", json={"contract": contract})
    assert response.status_code == 422


def test_parser_failure_uses_fallback(client, monkeypatch):
    def fail(_sentence):
        raise RuntimeError("parser unavailable")

    monkeypatch.setattr(main, "parse_contract", fail)
    created = create(client)
    assert created["draft_contract"]["source"] == "fallback"


def test_events_are_ordered(client):
    task_id = create(client)["task_id"]
    response = main.events(task_id)
    assert response.media_type == "text/event-stream"
    rows = task_events(task_id)
    assert [row["id"] for row in rows] == sorted(row["id"] for row in rows)


def test_unconfirmed_task_cannot_transition_to_staging(client):
    task_id = create(client)["task_id"]
    with pytest.raises(InvalidTransitionError):
        transition(task_id, "staging")
