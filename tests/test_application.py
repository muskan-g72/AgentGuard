"""Real SQLite/API integration; no paid services are called."""

from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3

from fastapi.testclient import TestClient
import pytest

from app import main
from app.main import create_app
from app.store import Store
from guard.contract_parser import DEMO_CONTRACT


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "workflow.db")
    with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
        yield client


def reviewed_task(client, scenario="s1"):
    result = client.post("/tasks", json={"sentence": "A train ticket", "scenario": scenario,
                                        "draft_contract": DEMO_CONTRACT.model_dump(mode="json")})
    assert result.status_code == 200, result.text
    task = result.json()
    answers = {q["key"]: "don't care" for q in task["questions"]}
    assert client.post(f'/tasks/{task["task_id"]}/answers', json={"answers": answers}).status_code == 200
    response = client.post(f'/tasks/{task["task_id"]}/confirm', json={})
    assert response.status_code == 200, response.text
    return response.json()


def staged_cart(client, **state):
    response = client.post("/api/carts", json=state)
    assert response.status_code == 200, response.text
    return response.json()


def evaluate(client, task, record, evidence=None):
    return client.post(f'/api/carts/{record["cart_id"]}/check', json={
        "task_id": task["task_id"], "cart": evidence or record["cart"]})


def outgoing(cart):
    return {"cart_id": cart["cart_id"], "items": [{"id": i["id"], "price": i["price"]} for i in cart["items"]],
            "total": cart["total"], "fields": {}}


def approved(client):
    task = reviewed_task(client)
    record = staged_cart(client)
    check = evaluate(client, task, record).json()
    assert check["decision"]["result"] == "allow"
    return task, record, {"task_id": task["task_id"], "approval": check["approval"],
                          "order_request": outgoing(record["cart"])}


def order_count(client):
    with client.app.state.store.connection() as db:
        return db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]


@pytest.mark.parametrize("state,result,removed", [
    ({}, "allow", []),
    ({"insurance": True, "meal": True}, "block", ["x1", "m1"]),
    ({"fee": True}, "block", ["f1"]),
    ({"ticket": "t3"}, "block", []),
    ({"scenario": "s5"}, "ask", []),
    ({"scenario": "s6"}, "ask", []),
])
def test_authoritative_contents_produce_actual_decisions(client, state, result, removed):
    task = reviewed_task(client)
    record = staged_cart(client, **state)
    check = evaluate(client, task, record).json()
    assert check["decision"]["result"] == result
    assert check["decision"]["remove_item_ids"] == removed
    assert bool(check["approval"]) == (result == "allow")
    if state.get("scenario") == "s5":
        assert check["decision"]["flags"]
    assert order_count(client) == 0


def test_removal_requires_fresh_extraction_and_recheck(client):
    task = reviewed_task(client, "s2")
    record = staged_cart(client, scenario="s2", insurance=True, meal=True)
    assert evaluate(client, task, record).json()["decision"]["result"] == "block"
    fresh = client.put(f'/api/carts/{record["cart_id"]}', json=record["state"] | {"insurance": False, "meal": False}).json()
    assert evaluate(client, task, fresh, record["cart"]).status_code == 409
    assert evaluate(client, task, fresh).json()["decision"]["result"] == "allow"


def test_scenario_label_does_not_override_valid_cart_contents(client):
    task = reviewed_task(client, "s4")
    record = staged_cart(client, scenario="s4", ticket="t1")
    assert evaluate(client, task, record).json()["decision"]["result"] == "allow"


def test_unanswered_questions_and_unreviewed_fallback_cannot_approve(client):
    task = client.post("/tasks", json={"sentence": "Book a train", "draft_contract": DEMO_CONTRACT.model_dump()}).json()
    record = staged_cart(client)
    assert evaluate(client, task, record).status_code == 409
    assert client.post(f'/tasks/{task["task_id"]}/confirm', json={}).status_code == 409
    assert order_count(client) == 0


def test_fallback_with_explicit_words_still_requires_missing_preference_answers(client):
    task = client.post("/tasks", json={"sentence": "A refundable ticket with baggage and a confirmed seat",
                                       "draft_contract": DEMO_CONTRACT.model_dump()}).json()
    assert len(task["questions"]) == 3
    assert not task["reviewed"]


@pytest.mark.parametrize("failure", ["missing", "import", "invalid", "network"])
def test_checker_failures_issue_neither_approval_nor_order(client, monkeypatch, failure):
    task = reviewed_task(client)
    record = staged_cart(client)
    if failure == "missing":
        monkeypatch.setattr(main, "check", None)
    else:
        def broken(*_):
            if failure == "import":
                raise ImportError("missing checker")
            if failure == "invalid":
                return {"result": "surprise"}
            raise OSError("pretend external failure; never approve")
        monkeypatch.setattr(main, "check", broken)
    result = evaluate(client, task, record)
    assert result.status_code == 503
    assert order_count(client) == 0
    with client.app.state.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0


@pytest.mark.parametrize("invalid", ["float", "missing", "wrong_id", "changed_total", "missing_hidden"])
def test_invalid_or_disagreeing_extraction_cannot_approve(client, invalid):
    task = reviewed_task(client)
    record = staged_cart(client, scenario="s5" if invalid == "missing_hidden" else "s1")
    evidence = json.loads(json.dumps(record["cart"]))
    if invalid == "float":
        evidence["total"] = 1000.0
    elif invalid == "missing":
        del evidence["items"]
    elif invalid == "wrong_id":
        evidence["items"][0]["id"] = "invented"
    elif invalid == "changed_total":
        evidence["total"] = 1
    else:
        evidence["hidden_text"] = []
    assert evaluate(client, task, record, evidence).status_code in (409, 422)
    assert order_count(client) == 0


def test_unchanged_approved_cart_creates_one_persistent_immutable_order(client):
    task, record, body = approved(client)
    response = client.post(f'/api/carts/{record["cart_id"]}/confirm', json=body)
    assert response.status_code == 200, response.text
    order = response.json()
    assert order["simulated"] is True
    assert order["cart"] == record["cart"]
    assert client.get('/api/orders/' + order["order_id"]).json() == order
    assert Store(client.app.state.store.path).order(order["order_id"]) == order
    assert client.get('/tasks/' + task["task_id"]).json()["status"] == "done"
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with client.app.state.store.connection() as db:
            db.execute("UPDATE orders SET snapshot='{}'")
    assert order_count(client) == 1


def test_same_price_requested_date_change_invalidates_approval(client):
    _, record, body = approved(client)
    updated = client.put(f'/api/carts/{record["cart_id"]}', json=record["state"] | {"date": "2026-10-26"}).json()
    assert updated["cart"]["total"] == record["cart"]["total"]
    assert client.post(f'/api/carts/{record["cart_id"]}/confirm', json=body).status_code == 409
    assert order_count(client) == 0


def test_same_price_actual_ticket_date_change_is_detected_by_content_hash(client):
    _, record, body = approved(client)
    changed = record["cart"]
    changed["items"][0]["date"] = "2026-10-26"
    with client.app.state.store.connection() as db:
        db.execute("UPDATE carts SET cart=? WHERE id=?", (json.dumps(changed), record["cart_id"]))
    assert client.post(f'/api/carts/{record["cart_id"]}/confirm', json=body).status_code == 409
    assert order_count(client) == 0


def test_duplicate_concurrent_confirmation_is_idempotent(client):
    _, record, body = approved(client)
    def confirm(_):
        response = client.post(f'/api/carts/{record["cart_id"]}/confirm', json=body)
        assert response.status_code == 200, response.text
        return response.json()["order_id"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(confirm, range(8)))
    assert len(set(ids)) == 1
    assert order_count(client) == 1


def test_confirmed_task_cannot_issue_another_approval_or_order(client):
    task, record, body = approved(client)
    assert client.post(f'/api/carts/{record["cart_id"]}/confirm', json=body).status_code == 200
    assert evaluate(client, task, record).status_code == 409
    assert order_count(client) == 1


def test_failed_or_paused_task_cannot_commit_an_older_approval(client):
    task, record, body = approved(client)
    client.app.state.store.event(task["task_id"], "failed", "A later extraction failed.")
    assert client.post(f'/api/carts/{record["cart_id"]}/confirm', json=body).status_code == 409
    assert order_count(client) == 0


@pytest.mark.parametrize("tamper", ["approval", "price", "date_item", "fields", "task"])
def test_real_outgoing_request_cannot_tamper_with_approval(client, tamper):
    _, record, body = approved(client)
    if tamper == "approval":
        body["approval"] = "client-supplied-allow"
    elif tamper == "price":
        body["order_request"]["items"][0]["price"] = body["order_request"]["total"] = 900
    elif tamper == "date_item":
        body["order_request"]["items"][0]["id"] = "t3"
    elif tamper == "fields":
        body["order_request"]["fields"]["insurance"] = True
    else:
        body["task_id"] = reviewed_task(client)["task_id"]
    assert client.post(f'/api/carts/{record["cart_id"]}/confirm', json=body).status_code == 409
    assert order_count(client) == 0


def test_missing_checker_at_commit_prevents_order_even_with_valid_approval(client, monkeypatch):
    _, record, body = approved(client)
    monkeypatch.setattr(main, "check_request", None)
    assert client.post(f'/api/carts/{record["cart_id"]}/confirm', json=body).status_code == 503
    assert order_count(client) == 0


def test_direct_confirmation_navigation_and_unknown_order_cannot_create_records(client):
    assert client.get("/confirmation.html?cart_id=c_001&ticket=t1&total=1000").status_code == 200
    assert client.get("/api/orders/order_c_001").status_code == 404
    assert order_count(client) == 0


def test_disable_guard_and_repository_secret_paths_are_rejected(client):
    assert client.post('/tasks', json={"sentence": "book", "guard_enabled": False}).status_code == 422
    for path in ["/.env", "/.git/config", "/data/workflow.db", "/guard/models.py"]:
        assert client.get(path).status_code == 404


def test_static_frontend_failure_cannot_silently_approve(client):
    assert client.post('/stage', json={"cart_url": "http://localhost/checkout.html", "scenario": "s1"}).status_code == 422
    assert order_count(client) == 0
