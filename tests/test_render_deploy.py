"""Small checks for the replay-only Render startup boundary."""

from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from app.staging import stage_cart_evidence
from app.tinyfish_client import TinyFishError, validate_replay_url
from guard.contract_parser import DEMO_CONTRACT


def test_healthz_is_a_small_ready_response(tmp_path):
    with TestClient(create_app(tmp_path / "render.db"), base_url="http://localhost") as client:
        assert client.get("/healthz").json() == {"status": "ok"}


def test_render_host_allowlist_is_exact_and_healthz_allows_probe(monkeypatch, tmp_path):
    host = "agentguard-demo.onrender.com"
    monkeypatch.setenv("ALLOWED_HOSTS", host)
    monkeypatch.setenv("PUBLIC_BASE_URL", f"https://{host}")
    with TestClient(create_app(tmp_path / "render.db"), base_url=f"https://{host}") as client:
        assert client.get("/").status_code == 200
        assert client.get("/", headers={"Host": host + ".evil.example"}).status_code == 400
        assert client.get("/", headers={"Host": "localhost"}).status_code == 200
        assert client.get("/healthz", headers={"Host": "render-internal.invalid"}).json() == {"status": "ok"}


def test_replay_origin_uses_exact_public_host(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://agentguard-demo.onrender.com")
    assert validate_replay_url("https://agentguard-demo.onrender.com/checkout.html")
    with pytest.raises(TinyFishError):
        validate_replay_url("https://agentguard-demo.onrender.com.evil.example/checkout.html")


def test_replay_staging_accepts_the_public_host(monkeypatch):
    monkeypatch.setenv("REPLAY", "1")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://agentguard-demo.onrender.com")
    evidence = stage_cart_evidence("https://agentguard-demo.onrender.com/checkout.html", DEMO_CONTRACT, scenario="s1")
    assert evidence.mode == "fixture_replay" and evidence.cart.total == 1000


def test_missing_key_fails_live_stage_closed(monkeypatch, tmp_path):
    monkeypatch.delenv("REPLAY", raising=False)
    monkeypatch.delenv("TINYFISH_API_KEY", raising=False)
    with TestClient(create_app(tmp_path / "render.db"), base_url="http://localhost") as client:
        response = client.post("/stage", json={"task_id": "unused", "scenario": "s1"})
    assert response.status_code == 503
    assert "TINYFISH_API_KEY" in response.json()["detail"]
