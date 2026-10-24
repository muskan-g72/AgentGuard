"""Task API, audit stream, and signed receipt integration tests."""

import json

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.main import create_app
from guard.contract_parser import DEMO_CONTRACT


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("RECEIPT_KEY", "test-only-receipt-key")
    with TestClient(create_app(tmp_path / "workflow.db"), base_url="http://localhost") as value:
        yield value


def create(client, *, review=False):
    response = client.post("/tasks", json={
        "sentence": "Book one Ludhiana to Delhi ticket",
        "scenario": "s1",
        "draft_contract": DEMO_CONTRACT.model_dump(mode="json"),
    })
    assert response.status_code == 200, response.text
    task = response.json()
    if review:
        answers = {question["key"]: "don't care" for question in task["questions"]}
        assert client.post(f"/tasks/{task['task_id']}/answers", json={"answers": answers}).status_code == 200
        response = client.post(f"/tasks/{task['task_id']}/confirm", json={})
        assert response.status_code == 200, response.text
        return response.json()
    return task


def test_task_happy_path_requires_answers_then_explicit_confirmation(client):
    task = create(client)
    assert task["status"] == "awaiting_answers"
    assert client.post(f"/tasks/{task['task_id']}/confirm", json={}).status_code == 409
    reviewed = create(client, review=True)
    assert reviewed["status"] == "awaiting_confirmation"
    assert reviewed["contract_confirmed"] is True


def test_invalid_contract_is_rejected(client):
    task = create(client, review=True)
    contract = task["contract"] | {"max_total": 0, "unknown": True}
    response = client.post(f"/tasks/{task['task_id']}/confirm", json={"contract": contract})
    assert response.status_code == 422


def test_parser_exception_uses_explicit_fallback(client, monkeypatch):
    monkeypatch.setattr(main, "parse_contract", lambda _: (_ for _ in ()).throw(RuntimeError("offline")))
    response = client.post("/tasks", json={"sentence": "Book a train"})
    assert response.status_code == 200
    assert response.json()["draft_contract"]["source"] == "fallback"


def test_events_are_ordered_hash_chained_and_streamed_as_sse(client):
    task = create(client, review=True)
    response = client.get(f"/tasks/{task['task_id']}/events")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert [event["id"] for event in events] == list(range(1, len(events) + 1))
    assert events[0]["prev_hash"] == "0" * 64
    assert all(events[index]["prev_hash"] == events[index - 1]["hash"] for index in range(1, len(events)))


def test_reviewed_contract_is_immutable_instead_of_silently_unconfirmed(client):
    task = create(client, review=True)
    changed = task["contract"] | {"max_total": 999}
    response = client.post(f"/tasks/{task['task_id']}/confirm", json={"contract": changed})
    assert response.status_code == 409
    current = client.get(f"/tasks/{task['task_id']}").json()
    assert current["contract"] == task["contract"]
    assert current["contract_confirmed"] is True


def test_receipt_verifies_and_persisted_event_tampering_is_detected(client):
    task = create(client, review=True)
    receipt = client.get(f"/tasks/{task['task_id']}/receipt")
    assert receipt.status_code == 200
    assert receipt.json()["signature"]
    assert client.get(f"/tasks/{task['task_id']}/receipt/verify").json() == {"valid": True}

    store = client.app.state.store
    with store.connection() as db:
        body = json.loads(db.execute("SELECT body FROM tasks WHERE id=?", (task["task_id"],)).fetchone()[0])
        body["events"][0]["payload"]["detail"] = "tampered"
        db.execute("UPDATE tasks SET body=? WHERE id=?", (json.dumps(body), task["task_id"]))
    assert client.get(f"/tasks/{task['task_id']}/receipt/verify").json() == {"valid": False, "broken_at": 1}


def test_receipts_fail_closed_without_signing_key(tmp_path, monkeypatch):
    monkeypatch.delenv("RECEIPT_KEY", raising=False)
    with TestClient(create_app(tmp_path / "unsigned.db"), base_url="http://localhost", raise_server_exceptions=False) as client:
        task = create(client)
        assert client.get(f"/tasks/{task['task_id']}/receipt").status_code == 503
        assert client.get("/health").json()["receipt_configured"] is False
