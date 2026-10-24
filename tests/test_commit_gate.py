"""The real outgoing request can commit only the exact approved cart once."""

from fastapi.testclient import TestClient

from app.main import create_app
from guard.contract_parser import DEMO_CONTRACT


def prepared(tmp_path):
    client = TestClient(create_app(tmp_path / "gate.db"), base_url="http://localhost")
    task = client.post("/tasks", json={"sentence": "demo", "draft_contract": DEMO_CONTRACT.model_dump()}).json()
    answers = {question["key"]: "don't care" for question in task["questions"]}
    client.post(f"/tasks/{task['task_id']}/answers", json={"answers": answers}).raise_for_status()
    task = client.post(f"/tasks/{task['task_id']}/confirm", json={}).json()
    cart = client.post("/api/carts", json={"scenario": "s1"}).json()
    checked = client.post(f"/api/carts/{cart['cart_id']}/check", json={"task_id": task["task_id"], "cart": cart["cart"]}).json()
    body = {"task_id": task["task_id"], "approval": checked["approval"], "order_request": {
        "cart_id": cart["cart_id"],
        "items": [{"id": item["id"], "price": item["price"]} for item in cart["cart"]["items"]],
        "total": cart["cart"]["total"], "fields": {},
    }}
    return client, task, cart, body


def test_blocked_cart_never_receives_approval(tmp_path):
    client, task, _, _ = prepared(tmp_path)
    bad = client.post("/api/carts", json={"scenario": "s2", "insurance": True, "meal": True}).json()
    result = client.post(f"/api/carts/{bad['cart_id']}/check", json={"task_id": task["task_id"], "cart": bad["cart"]})
    assert result.json()["decision"]["result"] == "block"
    assert result.json()["approval"] is None


def test_cart_change_after_allow_refuses_commit(tmp_path):
    client, _, cart, body = prepared(tmp_path)
    client.put(f"/api/carts/{cart['cart_id']}", json={"scenario": "s1", "date": "2026-10-26"}).raise_for_status()
    assert client.post(f"/api/carts/{cart['cart_id']}/confirm", json=body).status_code == 409


def test_outgoing_total_mismatch_refuses_commit(tmp_path):
    client, _, cart, body = prepared(tmp_path)
    body["order_request"]["total"] = 999
    assert client.post(f"/api/carts/{cart['cart_id']}/confirm", json=body).status_code == 409


def test_allow_commits_exactly_once_idempotently(tmp_path):
    client, _, cart, body = prepared(tmp_path)
    first = client.post(f"/api/carts/{cart['cart_id']}/confirm", json=body)
    second = client.post(f"/api/carts/{cart['cart_id']}/confirm", json=body)
    assert first.status_code == second.status_code == 200
    assert first.json()["order_id"] == second.json()["order_id"]
    with client.app.state.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1
