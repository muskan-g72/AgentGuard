"""Run endpoint authorization and operator/public separation."""

from fastapi.testclient import TestClient

from app.main import create_app
from guard.contract_parser import DEMO_CONTRACT


def task(client, review=False):
    value = client.post("/tasks", json={"sentence": "demo", "draft_contract": DEMO_CONTRACT.model_dump()}).json()
    if review:
        answers = {question["key"]: "don't care" for question in value["questions"]}
        client.post(f"/tasks/{value['task_id']}/answers", json={"answers": answers}).raise_for_status()
        value = client.post(f"/tasks/{value['task_id']}/confirm", json={}).json()
    return value


def test_unconfirmed_run_is_refused_before_browser_work(tmp_path, monkeypatch):
    client = TestClient(create_app(tmp_path / "run.db"), base_url="http://localhost")
    called = []
    monkeypatch.setattr("app.workflow.run_task", lambda *_args, **_kwargs: called.append(True))
    value = task(client)
    response = client.post(f"/tasks/{value['task_id']}/run", json={})
    assert response.status_code == 409
    assert called == []


def test_reviewed_local_run_uses_integrated_orchestrator(tmp_path, monkeypatch):
    client = TestClient(create_app(tmp_path / "run.db"), base_url="http://localhost")
    value = task(client, review=True)
    monkeypatch.setattr("app.workflow.run_task", lambda store, task_id, mode, cart_url, confirm: {
        "task_id": task_id, "status": "allowed", "mode": mode,
    })
    response = client.post(f"/tasks/{value['task_id']}/run", json={"mode": "local"})
    assert response.status_code == 200
    assert response.json()["status"] == "allowed"


def test_durable_public_backend_never_runs_paid_agent(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTGUARD_DEPLOYMENT_MODE", "durable")
    monkeypatch.setenv("AGENTGUARD_VOLUME_PATH", str(tmp_path))
    monkeypatch.setenv("AGENTGUARD_DB", str(tmp_path / "public.db"))
    monkeypatch.setenv("AGENTGUARD_PUBLIC_ORIGIN", "https://demo-booking-tau.vercel.app")
    monkeypatch.setattr(type(tmp_path), "is_mount", lambda self: self == tmp_path)
    client = TestClient(create_app(), base_url="https://demo-booking-tau.vercel.app")
    value = task(client, review=True)
    assert client.post(f"/tasks/{value['task_id']}/run", json={}).status_code == 403
