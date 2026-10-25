"""Anonymous session isolation and durable-session safety checks."""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.store import Store, WorkflowError
from guard.contract_parser import DEMO_CONTRACT


def _train_approved(client):
    created = client.post("/tasks", json={"sentence": "Book a train", "draft_contract": DEMO_CONTRACT.model_dump()}).json()
    answers = {q["key"]: "don't care" for q in created["questions"]}
    client.post(f"/tasks/{created['task_id']}/answers", json={"answers": answers}).raise_for_status()
    reviewed = client.post(f"/tasks/{created['task_id']}/confirm", json={}).json()
    cart = client.post("/api/carts", json={}).json()
    checked = client.post(f"/api/carts/{cart['cart_id']}/check", json={
        "task_id": reviewed["task_id"], "cart": cart["cart"]}).json()
    assert checked["decision"]["result"] == "allow"
    outgoing = {"cart_id": cart["cart_id"],
                "items": [{"id": i["id"], "price": i["price"]} for i in cart["cart"]["items"]],
                "total": cart["cart"]["total"], "fields": {}}
    order = client.post(f"/api/carts/{cart['cart_id']}/confirm", json={
        "task_id": reviewed["task_id"], "approval": checked["approval"], "order_request": outgoing}).json()
    return reviewed, cart, order


def test_browser_session_receives_cookie_and_isolated_train_resources(tmp_path, monkeypatch):
    monkeypatch.setenv("RECEIPT_KEY", "test-receipt-key")
    app = create_app(tmp_path / "sessions.db")
    with TestClient(app, base_url="http://localhost") as first, TestClient(app, base_url="http://localhost") as second:
        initial = first.get("/health")
        task, cart, order = _train_approved(first)
        cookie = first.cookies.get("agentguard_session")
        assert cookie and "HttpOnly" in initial.headers.get("set-cookie", "")
        assert second.get(f"/tasks/{task['task_id']}").status_code == 404
        assert second.get(f"/api/carts/{cart['cart_id']}").status_code == 404
        assert second.put(f"/api/carts/{cart['cart_id']}", json={}).status_code == 404
        assert second.get(f"/api/orders/{order['order_id']}").status_code == 404
        assert second.get(f"/tasks/{task['task_id']}/receipt").status_code == 404
        assert second.get(f"/tasks/{task['task_id']}/receipt/verify").status_code == 404


def test_tampered_cookie_rotates_and_cannot_read_resource(tmp_path, monkeypatch):
    monkeypatch.setenv("RECEIPT_KEY", "test-receipt-key")
    app = create_app(tmp_path / "tamper.db")
    with TestClient(app, base_url="http://localhost") as first, TestClient(app, base_url="http://localhost") as second:
        task, _, _ = _train_approved(first)
        original = first.cookies.get("agentguard_session")
        second.cookies.set("agentguard_session", original[:-1] + ("A" if original[-1] != "A" else "B"))
        response = second.get(f"/tasks/{task['task_id']}")
        assert response.status_code == 404
        assert response.cookies.get("agentguard_session")
        assert original not in response.text


def test_food_session_ownership_and_cross_origin_state_change(tmp_path, monkeypatch):
    monkeypatch.setenv("REPLAY", "1")
    monkeypatch.setenv("RECEIPT_KEY", "test-receipt-key")
    app = create_app(tmp_path / "food-sessions.db")
    contract = {"diet": "veg", "quantity": 1, "max_total": 300, "min_rating": 4.2,
                "max_eta_minutes": 45, "allow_extras": False, "priority": "price"}
    urls = ["https://demo-booking-tau.vercel.app/foodhub/",
            "https://demo-booking-tau.vercel.app/quickbite/",
            "https://demo-booking-tau.vercel.app/dinedash/"]
    with TestClient(app, base_url="http://localhost") as first, TestClient(app, base_url="http://localhost") as second:
        compared = first.post("/food/compare", json={"contract": contract, "platform_urls": urls}).json()
        first.post(f"/food/{compared['task_id']}/confirm", json={}).raise_for_status()
        run = first.post("/food/run", json={"task_id": compared["task_id"], "scenario": "clean"})
        assert run.status_code == 200, run.text
        task = first.get(f"/tasks/{compared['task_id']}").json()
        order_id = task["food_order_id"]
        assert second.get(f"/tasks/{compared['task_id']}").status_code == 404
        assert second.get(f"/api/orders/{order_id}").status_code == 404
        rejected = first.post("/tasks", headers={"Origin": "https://evil.example"},
                              json={"sentence": "Book a train", "draft_contract": DEMO_CONTRACT.model_dump()})
        assert rejected.status_code == 403


def test_durable_cookie_requires_secret_and_is_secure(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTGUARD_DEPLOYMENT_MODE", "durable")
    monkeypatch.setenv("AGENTGUARD_VOLUME_PATH", str(tmp_path))
    monkeypatch.setenv("AGENTGUARD_DB", str(tmp_path / "durable.db"))
    monkeypatch.setenv("AGENTGUARD_BACKEND_HOST", "demo.example")
    monkeypatch.setattr(type(tmp_path), "is_mount", lambda self: self == tmp_path)
    monkeypatch.delenv("AGENTGUARD_SESSION_SECRET", raising=False)
    with pytest.raises(ValueError, match="SESSION_SECRET"):
        create_app()
    monkeypatch.setenv("AGENTGUARD_SESSION_SECRET", "durable-test-secret")
    with TestClient(create_app(), base_url="https://demo.example") as client:
        cookie = client.get("/health").headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Secure" in cookie


def test_existing_database_migrates_owner_columns_without_data_loss(tmp_path):
    path = tmp_path / "legacy.db"
    body = {"task_id": "legacy", "status": "failed", "events": [], "contract": DEMO_CONTRACT.model_dump(), "reviewed": False, "questions": [], "answers": {}}
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
        db.execute("INSERT INTO tasks VALUES (?, ?)", ("legacy", json.dumps(body)))
    Store(path)
    with sqlite3.connect(path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(tasks)")}
        assert "owner_session_id" in columns
        assert json.loads(db.execute("SELECT body FROM tasks WHERE id='legacy'").fetchone()[0])["task_id"] == "legacy"
    with pytest.raises(WorkflowError) as error:
        Store(path).task("legacy", "new-session")
    assert error.value.status == 404


def test_public_responses_do_not_expose_session_secret(tmp_path, monkeypatch):
    secret = "never-return-this-secret"
    monkeypatch.setenv("AGENTGUARD_SESSION_SECRET", secret)
    app = create_app(tmp_path / "public.db")
    with TestClient(app, base_url="http://localhost") as client:
        for path in ("/health", "/version", "/", "/ui/"):
            response = client.get(path)
            assert secret not in response.text
