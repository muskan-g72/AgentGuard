from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.drivers import PageUnverified, ReplayDriver, TinyFishDriver
from app.main import create_app
from app.store import TRANSITIONS, verify_receipt
from guard.models import OrderRequest


class SpyDriver(ReplayDriver):
    def __init__(self):
        self.commits = []
        self.stages = 0

    def stage(self, contract, scenario):
        self.stages += 1
        return super().stage(contract, scenario)

    def commit(self, request):
        self.commits.append(request.model_dump())
        return super().commit(request)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("TINYFISH_API_KEY", raising=False)
    api = create_app(db_path=":memory:", receipt_key="test-demo-receipt-key", driver=SpyDriver())
    with TestClient(api) as value:
        yield value


def ready(client, scenario="s2", *, guard_enabled=True):
    response = client.post("/tasks", json={"sentence": "One ticket under Rs 1000", "scenario": scenario, "guard_enabled": guard_enabled})
    assert response.status_code == 200
    body = response.json()
    task_id = body["task_id"]
    assert len(body["questions"]) <= 3
    answers = {question["key"]: "don't care" for question in body["questions"]}
    if answers:
        assert client.post(f"/tasks/{task_id}/answers", json={"answers": answers}).status_code == 200
    assert client.post(f"/tasks/{task_id}/confirm").json() == {"status": "staging"}
    return task_id


def run_task(client, scenario="s2", **kwargs):
    task_id = ready(client, scenario, **kwargs)
    response = client.post(f"/tasks/{task_id}/run")
    assert response.status_code == 200, response.text
    return task_id, response.json()


def test_s2_end_to_end_repairs_rechecks_commits_and_signs(client):
    task_id, task = run_task(client)
    assert task["status"] == "done"
    assert [entry["result"] for entry in task["decision_history"]] == ["block", "allow", "allow"]
    assert task["decision_history"][0]["remove_item_ids"] == ["x1", "m1"]
    assert task["final"]["total"] == 1000
    assert task["cart"]["items"][0]["price"] == 1000
    assert len(client.app.state.service.driver.commits) == 1
    receipt = client.get(f"/tasks/{task_id}/receipt").json()
    assert receipt["events"][0]["prev_hash"] == "0" * 64
    assert client.get(f"/tasks/{task_id}/receipt/verify").json() == {"valid": True, "broken_at": None}
    statuses = [event["payload"]["to"] for event in task["events"] if event["type"] == "status"]
    assert statuses == ["awaiting_answers", "awaiting_confirmation", "staging", "checking", "blocked", "fixing", "checking", "allowed", "committing", "done"]


@pytest.mark.parametrize("scenario,result", [("s1", "done"), ("s3", "blocked"), ("s4", "blocked"), ("s5", "blocked"), ("s6", "blocked")])
def test_scenarios_fail_closed(client, scenario, result):
    task_id, task = run_task(client, scenario)
    assert task["status"] == result
    assert len(client.app.state.service.driver.commits) == (1 if result == "done" else 0)
    assert client.get(f"/tasks/{task_id}/receipt/verify").json()["valid"]


def test_question_answers_keep_false_and_null_distinct(client):
    draft = client.post("/tasks", json={"sentence": "Book a ticket"}).json()
    task_id = draft["task_id"]
    assert client.post(f"/tasks/{task_id}/confirm").status_code == 409
    assert client.post(f"/tasks/{task_id}/answers", json={"answers": {"baggage": "yes"}}).status_code == 409
    answers = {"refundable": "yes", "seat_confirmed": "don't care", "baggage": "no"}
    response = client.post(f"/tasks/{task_id}/answers", json={"answers": answers})
    assert response.json()["contract"]["requirements"] == {"refundable": True, "seat_confirmed": None, "baggage": False}
    assert client.get(f"/tasks/{task_id}/receipt/verify").json()["valid"]
    assert client.post(f"/tasks/{task_id}/answers", json={"answers": answers}).status_code == 409


def test_no_questions_goes_straight_to_confirmation(client, monkeypatch):
    from guard.scenarios import CONTRACT
    draft = CONTRACT.model_copy(deep=True)
    draft.requirements.refundable = True
    draft.requirements.seat_confirmed = True
    draft.requirements.baggage = False
    monkeypatch.setattr("app.service.parse_contract", lambda sentence: draft)
    body = client.post("/tasks", json={"sentence": "All preferences explicit"}).json()
    assert body["questions"] == []
    assert client.get(f"/tasks/{body['task_id']}").json()["status"] == "awaiting_confirmation"


def test_run_before_confirmation_and_rerun_are_rejected(client):
    task_id = client.post("/tasks", json={"sentence": "Book"}).json()["task_id"]
    assert client.post(f"/tasks/{task_id}/run").status_code == 409
    assert client.app.state.service.driver.stages == 0
    done_id, _ = run_task(client, "s1")
    assert client.post(f"/tasks/{done_id}/run").status_code == 409
    assert len(client.app.state.service.driver.commits) == 1


def allowed_task(client):
    """Pause a real run just before commit so tests attack the actual gate."""
    task_id = ready(client, "s1")
    service = client.app.state.service
    original = service.commit
    service.commit = lambda task_id: None
    try:
        task = client.post(f"/tasks/{task_id}/run").json()
    finally:
        service.commit = original
    assert task["status"] == "allowed"
    return task_id


@pytest.mark.parametrize("tamper,reason", [
    (lambda task: task.update(status="checking"), "status"),
    (lambda task: task["decision_history"][-1].update(result="block"), "decision"),
    (lambda task: task["decision_history"][-1].update(result="ask"), "decision"),
    (lambda task: task["cart"].update(total=999), "cart_hash"),
    (lambda task: task.update(allowed_cart_hash=None), "cart_hash"),
    (lambda task: task["contract"].update(max_total=1001), "contract_hash"),
    (lambda task: task["order_request"]["fields"].update(insurance=True), "order_request"),
])
def test_commit_gate_rejects_audits_and_never_calls_transport(client, tamper, reason):
    task_id = allowed_task(client)
    service = client.app.state.service
    service.store.mutate(task_id, lambda task, append: tamper(task))
    with pytest.raises(HTTPException) as rejected:
        service.commit(task_id)
    assert rejected.value.status_code == 409
    assert service.driver.commits == []
    event = service.store.get(task_id)["events"][-1]
    assert event["type"] == "commit_rejected"
    assert reason in event["payload"]["reasons"]


def test_commit_gate_consumes_authorization_once(client):
    task_id = allowed_task(client)
    service = client.app.state.service
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(service.commit, task_id) for _ in range(2)]
    successes = sum(future.exception() is None for future in futures)
    assert successes == 1
    assert len(service.driver.commits) == 1


def test_public_run_returns_409_when_cart_changes_at_gate(client, monkeypatch):
    service = client.app.state.service
    original = service.commit
    def change_then_commit(task_id):
        service.store.mutate(task_id, lambda task, append: task["cart"].update(total=999))
        return original(task_id)
    monkeypatch.setattr(service, "commit", change_then_commit)
    task_id = ready(client, "s1")
    assert client.post(f"/tasks/{task_id}/run").status_code == 409
    assert not service.driver.commits
    assert service.store.get(task_id)["events"][-1]["type"] == "commit_rejected"


def test_changed_outgoing_request_is_blocked_before_allowed(client, monkeypatch):
    driver = client.app.state.service.driver
    original = driver.prepare_request
    def inject(cart):
        request = original(cart)
        request.items.append({"id": "x1", "price": 250})
        request.total += 250
        return OrderRequest.model_validate(request)
    monkeypatch.setattr(driver, "prepare_request", inject)
    _, task = run_task(client, "s1")
    assert task["status"] == "blocked"
    assert task["decision_history"][-1]["phase"] == "request"
    assert driver.commits == []


def test_live_request_without_capture_blocks(client, monkeypatch):
    def unavailable(cart):
        raise PageUnverified()
    monkeypatch.setattr(client.app.state.service.driver, "prepare_request", unavailable)
    _, task = run_task(client, "s1")
    assert task["status"] == "blocked"
    assert task["decision_history"][-1]["flags"] == ["page_unverified"]
    assert client.app.state.service.driver.commits == []


@pytest.mark.parametrize("phase", ["stage", "fix", "prepare_request", "commit"])
def test_transport_failure_never_allows_or_completes(client, monkeypatch, phase):
    driver = client.app.state.service.driver
    def failure(*args):
        raise RuntimeError("secret-vendor-response")
    monkeypatch.setattr(driver, phase, failure)
    _, task = run_task(client, "s2" if phase == "fix" else "s1")
    assert task["status"] == "failed"
    assert "secret-vendor-response" not in json.dumps(task)
    assert not task["final"]
    assert not any(event["type"] == "transition_rejected" for event in task["events"])


def test_missing_receipt_key_fails_before_staging(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    driver = SpyDriver()
    with TestClient(create_app(db_path=":memory:", receipt_key="", driver=driver)) as value:
        task_id, task = run_task(value, "s1")
        assert task["status"] == "failed"
        assert driver.stages == 0
        assert value.get(f"/tasks/{task_id}/receipt").status_code == 503
        assert not value.get(f"/tasks/{task_id}/receipt/verify").json()["valid"]


def test_guard_disabled_does_not_bypass_mandatory_gate(client):
    _, task = run_task(client, "s2", guard_enabled=False)
    assert task["status"] == "blocked"
    assert not client.app.state.service.driver.commits


def test_all_invalid_transitions_are_rejected_and_logged(client):
    task_id = ready(client)
    store = client.app.state.store
    for origin in TRANSITIONS:
        for target in TRANSITIONS:
            if target not in TRANSITIONS[origin]:
                store.mutate(task_id, lambda task, append: task.update(status=origin))
                assert not store.transition(task_id, target)
                task = store.get(task_id)
                assert task["status"] == origin
                assert task["events"][-1]["type"] == "transition_rejected"


@pytest.mark.parametrize("part", ["event", "deleted_event", "reorder", "signature", "contract", "final", "task_id", "float_total", "extra_event_field"])
def test_receipt_tampering_is_detected(client, part):
    task_id, _ = run_task(client, "s1")
    receipt = client.get(f"/tasks/{task_id}/receipt").json()
    if part == "event":
        receipt["events"][2]["payload"]["injected"] = True
    elif part == "deleted_event":
        receipt["events"].pop()
    elif part == "reorder":
        receipt["events"][1], receipt["events"][2] = receipt["events"][2], receipt["events"][1]
    elif part == "signature":
        receipt["signature"] = "0" * 64
    elif part == "contract":
        receipt["contract"]["max_total"] += 1
    elif part == "final":
        receipt["final"]["total"] += 1
    elif part == "float_total":
        receipt["final"]["total"] = float(receipt["final"]["total"])
    elif part == "extra_event_field":
        receipt["events"][0]["injected"] = True
    else:
        receipt["task_id"] = "other"
    assert not verify_receipt(receipt, client.app.state.store.key)["valid"]


def test_database_event_tampering_breaks_verify_endpoint(client):
    task_id, _ = run_task(client, "s1")
    store = client.app.state.store
    event = store.get(task_id)["events"][0]
    event["payload"]["draft_contract"]["max_total"] = 5000
    store.db.execute("UPDATE events SET body=? WHERE task_id=? AND id=1", (json.dumps(event), task_id))
    assert client.get(f"/tasks/{task_id}/receipt/verify").json() == {"valid": False, "broken_at": 1}


def test_sse_stream_and_last_event_id(client):
    task_id, _ = run_task(client, "s1")
    response = client.get(f"/tasks/{task_id}/events")
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"status":"done"' in response.text
    ids = [int(line[4:]) for line in response.text.splitlines() if line.startswith("id: ")]
    last = ids[-2]
    resumed = client.get(f"/tasks/{task_id}/events", headers={"Last-Event-ID": str(last)})
    assert '"status":"done"' in resumed.text
    assert '"status":"committing"' not in resumed.text
    assert client.get(f"/tasks/{task_id}/events", headers={"Last-Event-ID": "bad"}).status_code == 400


def test_health_stage_missing_tasks_and_validation(client):
    assert client.get("/health").json() == {"replay": True, "tinyfish_configured": False, "db_ok": True}
    staged = client.post("/stage", json={"scenario": "s2"})
    assert staged.status_code == 200
    assert staged.json()["decision"]["result"] == "block"
    assert client.app.state.service.driver.commits == []
    for suffix in ("", "/events", "/receipt", "/receipt/verify"):
        assert client.get("/tasks/missing" + suffix).status_code == 404
    assert client.post("/tasks", json={"sentence": "Book", "scenario": "s7"}).status_code == 422
    assert client.post("/tasks", json={"sentence": "Book", "guard_enabled": "false"}).status_code == 422


def test_tasks_and_receipts_persist_after_restart(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    path = str(tmp_path / "tasks.sqlite3")
    with TestClient(create_app(db_path=path, receipt_key="persistent-key", driver=ReplayDriver())) as first:
        task_id, _ = run_task(first, "s2")
    with TestClient(create_app(db_path=path, receipt_key="persistent-key", driver=ReplayDriver())) as second:
        assert second.get(f"/tasks/{task_id}").json()["status"] == "done"
        assert second.get(f"/tasks/{task_id}/receipt/verify").json()["valid"]


@pytest.mark.parametrize("url", ["http://localhost:8000", "https://127.0.0.1", "https://demo-booking-tau.vercel.app.evil.test", "https://demo-booking-tau.vercel.app@evil.test", "https://demo-booking-tau.vercel.app/checkout.html"])
def test_tinyfish_only_accepts_public_demo(url):
    with pytest.raises(ValueError):
        TinyFishDriver(base_url=url)
