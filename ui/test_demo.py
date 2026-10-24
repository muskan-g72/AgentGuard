from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ui.server import app


@pytest.fixture
def demo_client():
    with TestClient(app) as client:
        yield client


def test_demo_serves_ui_and_only_public_assets(demo_client):
    response = demo_client.get("/")
    assert response.status_code == 200
    assert 'Run demo' in response.text
    for path in ("/ui/app.mjs", "/app.js", "/checkout.js", "/checkout.html", "/index.html"):
        assert demo_client.get(path).status_code == 200
    for path in ("/.env", "/.git/config", "/app/main.py", "/guard/checker.py", "/ui/server.py", "/ui/test_demo.py"):
        assert demo_client.get(path).status_code == 404


def test_s7_simulated_merchant_confirms_actual_request_total(demo_client):
    response = demo_client.post("/api/order", json={
        "cart_id": "c_001", "items": [{"id": "t1", "price": 1000}, {"id": "x1", "price": 250}, {"id": "f1", "price": 250}],
        "total": 1500, "fields": {},
    })
    assert response.status_code == 200
    assert response.json()["total"] == 1500
    assert response.json()["simulated"] is True
    assert len(response.json()["items"]) == 3


@pytest.mark.parametrize("total", ["1000", 1000.0, True, None, -1, 999])
def test_merchant_rejects_invalid_integer_money(demo_client, total):
    response = demo_client.post("/api/order", json={"cart_id": "c", "items": [{"id": "t1", "price": 1000}], "total": total, "fields": {}})
    assert response.status_code == 400


def test_proxy_rejects_arbitrary_urls_and_paths(demo_client):
    for path in ("https://example.com", "/../secrets", "/tasks/../health", "/admin"):
        assert demo_client.get("/api/task-proxy", params={"path": path}).status_code == 400
