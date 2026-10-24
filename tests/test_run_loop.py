"""Bounded check/fix/recheck behavior at the authoritative API boundary."""

from fastapi.testclient import TestClient

from app.main import create_app
from guard.contract_parser import DEMO_CONTRACT


def reviewed(client, scenario="s2"):
    task = client.post("/tasks", json={"sentence": "demo", "scenario": scenario,
                                       "draft_contract": DEMO_CONTRACT.model_dump()}).json()
    answers = {question["key"]: "don't care" for question in task["questions"]}
    client.post(f"/tasks/{task['task_id']}/answers", json={"answers": answers}).raise_for_status()
    return client.post(f"/tasks/{task['task_id']}/confirm", json={}).json()


def test_s2_block_fix_recheck_records_decisions_and_only_latest_approval(tmp_path):
    client = TestClient(create_app(tmp_path / "loop.db"), base_url="http://localhost")
    task = reviewed(client)
    cart = client.post("/api/carts", json={"scenario": "s2", "insurance": True, "meal": True}).json()
    blocked = client.post(f"/api/carts/{cart['cart_id']}/check", json={"task_id": task["task_id"], "cart": cart["cart"]}).json()
    assert blocked["decision"]["remove_item_ids"] == ["x1", "m1"]
    fixed = client.put(f"/api/carts/{cart['cart_id']}", json={"scenario": "s2", "insurance": False, "meal": False}).json()
    allowed = client.post(f"/api/carts/{cart['cart_id']}/check", json={"task_id": task["task_id"], "cart": fixed["cart"]}).json()
    assert allowed["decision"]["result"] == "allow" and allowed["approval"]
    current = client.get(f"/tasks/{task['task_id']}").json()
    assert [event["payload"]["decision"]["result"] for event in current["decision_history"]] == ["block", "allow"]


def test_unknown_required_cart_evidence_blocks_progress_without_approval(tmp_path):
    client = TestClient(create_app(tmp_path / "ask.db"), base_url="http://localhost")
    task = reviewed(client, "s6")
    cart = client.post("/api/carts", json={"scenario": "s6"}).json()
    result = client.post(f"/api/carts/{cart['cart_id']}/check", json={"task_id": task["task_id"], "cart": cart["cart"]}).json()
    assert result["decision"]["result"] == "ask"
    assert result["approval"] is None
    assert client.get(f"/tasks/{task['task_id']}").json()["status"] == "blocked"


def test_guard_cannot_be_disabled(tmp_path):
    client = TestClient(create_app(tmp_path / "guard.db"), base_url="http://localhost")
    response = client.post("/tasks", json={"sentence": "demo", "guard_enabled": False})
    assert response.status_code == 422
