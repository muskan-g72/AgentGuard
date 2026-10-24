from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ui.server import app


@pytest.fixture
def demo_client():
    with TestClient(app, base_url="http://localhost") as client:
        yield client


def test_demo_serves_ui_and_only_public_assets(demo_client):
    response = demo_client.get("/")
    assert response.status_code == 200
    assert 'Run demo' in response.text
    for path in ("/ui/app.mjs", "/app.js", "/checkout.js", "/checkout.html", "/index.html"):
        assert demo_client.get(path).status_code == 200
    for path in ("/.env", "/.git/config", "/app/main.py", "/guard/checker.py", "/ui/server.py", "/ui/test_demo.py"):
        assert demo_client.get(path).status_code == 404


def test_ui_cannot_bypass_the_protected_merchant(demo_client):
    response = demo_client.post("/api/order", json={
        "cart_id": "c_001", "items": [{"id": "t1", "price": 1000}, {"id": "x1", "price": 250}, {"id": "f1", "price": 250}],
        "total": 1500, "fields": {},
    })
    assert response.status_code == 404
    assert demo_client.post("/api/carts/missing/confirm", json={}).status_code == 422
    assert demo_client.get("/health").json()["confirmation_protected"] is True


def test_origin_inventory_and_booking_assets_still_use_server_authority(demo_client):
    catalog = demo_client.get("/api/catalog").json()
    assert catalog["tickets"]["t1"]["date"] == "2026-10-25"
    response = demo_client.post("/api/carts", json={"passengers": 2, "insurance": True})
    assert response.status_code == 200
    assert response.json()["cart"]["total"] == 2250


def test_proxy_rejects_arbitrary_urls_and_paths(demo_client):
    for path in ("https://example.com", "/../secrets", "/tasks/../health", "/admin"):
        assert demo_client.get("/api/task-proxy", params={"path": path}).status_code == 400
