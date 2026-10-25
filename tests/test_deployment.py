"""Prepared deployment, production host policy and read-only readiness checks."""

import io
import json
from pathlib import Path
import shutil
import tomllib
from urllib.error import HTTPError

from fastapi.testclient import TestClient
import pytest

from app.config import Settings, PUBLIC_ORIGIN
from app.main import create_app
from app.readiness import ReadinessError, verify_readiness
from app.release import ASSETS, PUBLIC_ASSETS, ROOT, release
from guard.request_check import check_request
from guard.contract_parser import DEMO_CONTRACT
from scripts.prepare_deployment import prepare
from test_application import approved


@pytest.fixture
def artifact_root(tmp_path):
    files = [ROOT / name for name in (*ASSETS, *PUBLIC_ASSETS, "pyproject.toml", "requirements-deploy.txt", "README.md", "deploy/fly.toml.template")]
    files += list((ROOT / "app").glob("*.py")) + list((ROOT / "guard").glob("*.py"))
    for file in files:
        target = tmp_path / file.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, target)
    return tmp_path


def test_prepared_proxy_routes_every_path_to_one_backend_and_caches_nothing(artifact_root):
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "COPY app/*.py ./app/" in dockerfile and "COPY . " not in dockerfile
    assert "**/.env*" in (ROOT / ".dockerignore").read_text()
    result = prepare("agentguard-test-only", "bom", artifact_root)
    output = artifact_root / ".vercel" / "output"
    config = json.loads((output / "config.json").read_text())
    assert config["version"] == 3
    assert config["routes"][1]["dest"] == "https://agentguard-test-only.fly.dev/$1"
    assert config["routes"][1]["headers"]["Cache-Control"] == "no-store"
    assert config["routes"][1]["headers"]["x-vercel-enable-rewrite-caching"] == "0"
    assert list((output / "static").iterdir()) == [output / "static" / "deployment.json"]
    assert not (output / "functions").exists()
    descriptor = json.loads((output / "static" / "deployment.json").read_text())
    assert descriptor["release_id"] == release()["release_id"] == result["release_id"]
    fly = tomllib.loads((artifact_root / "deploy/generated/fly.toml").read_text())
    assert fly["mounts"][0]["destination"] == "/data"
    assert fly["env"]["AGENTGUARD_DB"] == "/data/workflow.db"
    assert fly["env"]["AGENTGUARD_ENABLE_AGENT_RUNS"] == "false"
    assert fly["deploy"]["strategy"] == "immediate"
    assert fly["http_service"]["min_machines_running"] == 1
    assert fly["http_service"]["checks"][0]["headers"]["Host"] == "agentguard-test-only.fly.dev"


def test_generator_refuses_stale_output_instead_of_silently_shipping_it(artifact_root):
    static = artifact_root / ".vercel/output/static"
    static.mkdir(parents=True)
    stale = static / "checkout.html"
    stale.write_text("old unsafe checkout")
    with pytest.raises(ValueError, match="unrelated artifacts"):
        prepare("agentguard-test-only", "bom", artifact_root)
    assert stale.read_text() == "old unsafe checkout"


def test_durable_mode_refuses_an_unmounted_directory_and_serverless_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTGUARD_DEPLOYMENT_MODE", "durable")
    monkeypatch.setenv("AGENTGUARD_VOLUME_PATH", str(tmp_path))
    monkeypatch.setenv("AGENTGUARD_DB", str(tmp_path / "workflow.db"))
    with pytest.raises(ValueError, match="real mounted"):
        Settings.load(ROOT)
    monkeypatch.setenv("VERCEL", "1")
    with pytest.raises(ValueError, match="Vercel Functions"):
        Settings.load(ROOT)


def test_public_host_and_approval_survive_application_restart_with_same_database(tmp_path, monkeypatch):
    # A mount is mocked here; the real process test separately verifies DB reuse.
    monkeypatch.setenv("AGENTGUARD_DEPLOYMENT_MODE", "durable")
    monkeypatch.setenv("AGENTGUARD_VOLUME_PATH", str(tmp_path))
    monkeypatch.setenv("AGENTGUARD_DB", str(tmp_path / "workflow.db"))
    monkeypatch.setenv("AGENTGUARD_BACKEND_HOST", "agentguard-test-only.fly.dev")
    monkeypatch.setenv("AGENTGUARD_SESSION_SECRET", "test-session-secret")
    monkeypatch.setattr(Path, "is_mount", lambda self: self == tmp_path)
    app = create_app()
    with TestClient(app, base_url="https://agentguard-test-only.fly.dev") as first:
        _, record, confirmation = approved(first)
        session_cookie = first.cookies.get("agentguard_session")
        health = first.get("/health").json()
        assert health["storage"]["durable"] is True
        assert first.post("/stage", json={"task_id": confirmation["task_id"]}).status_code == 403
        assert first.post('/tasks/' + confirmation["task_id"] + '/run', json={}).status_code == 403
        assert first.get("/health", headers={"Host": "agentguard-test-only.fly.dev.evil.example"}).status_code == 400
    with TestClient(create_app(), base_url=PUBLIC_ORIGIN) as second:
        second.cookies.set("agentguard_session", session_cookie)
        after = second.get("/health").json()
        assert health["storage"]["storage_id"] == after["storage"]["storage_id"]
        assert health["instance_id"] != after["instance_id"]
        response = second.post('/api/carts/' + record["cart_id"] + '/confirm', json=confirmation)
        assert response.status_code == 200, response.text
        assert second.post('/api/carts/' + record["cart_id"] + '/confirm', json=confirmation).json()["order_id"] == response.json()["order_id"]
        assert second.get("/health").headers["Cache-Control"] == "no-store"


def test_checker_host_configuration_is_explicit_and_deterministic():
    request = {"cart_id": "c", "items": [{"id": "t1", "price": 1000}], "total": 1000, "fields": {}}
    allowed = frozenset({"agentguard-test-only.fly.dev"})
    assert check_request(DEMO_CONTRACT, request, "agentguard-test-only.fly.dev", allowed_hosts=allowed).result == "allow"
    assert check_request(DEMO_CONTRACT, request, "agentguard-test-only.fly.dev.evil", allowed_hosts=allowed).result == "block"


class Response(io.BytesIO):
    status = 200
    def __enter__(self):
        return self
    def __exit__(self, *_):
        self.close()


def ready_responses():
    version = release()
    values = {"/" + name: (ROOT / name).read_bytes() for name in (*ASSETS, *PUBLIC_ASSETS)}
    health = {"release_id": version["release_id"], "db_ok": True, "checker_available": True,
              "receipt_configured": True,
              "session_configured": True,
              "confirmation_protected": True, "public_origin": PUBLIC_ORIGIN,
              "storage": {"durable": True, "storage_id": "persistent-test-id"}}
    values.update({"/version": json.dumps(version).encode(), "/health": json.dumps(health).encode(),
                   "/deployment.json": json.dumps(version | {"public_origin": PUBLIC_ORIGIN}).encode()})
    return values


def opener_for(values):
    def opener(url, timeout):
        from urllib.parse import urlparse
        path = urlparse(url).path
        if path not in values:
            raise HTTPError(url, 404, "not found", {}, None)
        return Response(values[path])
    return opener


def test_read_only_preflight_accepts_exact_matching_protected_release():
    values = ready_responses()
    result = verify_readiness(PUBLIC_ORIGIN, expected_release=release()["release_id"], opener=opener_for(values))
    assert result["ready"] is True and result["durable"] is True


def test_direct_backend_preflight_checks_the_configured_public_origin():
    result = verify_readiness("https://agentguard-test-only.fly.dev", require_proxy=False,
                              expected_public_origin=PUBLIC_ORIGIN, opener=opener_for(ready_responses()))
    assert result["ready"] is True


@pytest.mark.parametrize("fault", ["ephemeral", "wrong_release", "stale_asset", "wrong_proxy", "missing_checker", "missing_receipt_key", "missing_session_secret", "missing_storage_id"])
def test_preflight_rejects_inconsistent_or_ephemeral_deployment(fault):
    values = ready_responses()
    health = json.loads(values["/health"])
    if fault == "ephemeral":
        health["storage"]["durable"] = False
    elif fault == "missing_checker":
        health["checker_available"] = False
    elif fault == "missing_receipt_key":
        health["receipt_configured"] = False
    elif fault == "missing_session_secret":
        health["session_configured"] = False
    elif fault == "missing_storage_id":
        health["storage"].pop("storage_id")
    elif fault == "wrong_release":
        health["release_id"] = "old"
    elif fault == "stale_asset":
        values["/confirmation.html"] = b"old URL-based confirmation"
    else:
        proxy = json.loads(values["/deployment.json"])
        proxy["release_id"] = "old"
        values["/deployment.json"] = json.dumps(proxy).encode()
    values["/health"] = json.dumps(health).encode()
    with pytest.raises(ReadinessError):
        verify_readiness(PUBLIC_ORIGIN, opener=opener_for(values))
