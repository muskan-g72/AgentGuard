from fastapi.testclient import TestClient

from app.main import create_app


def test_single_runtime_serves_dashboard_train_and_food(tmp_path, monkeypatch):
    monkeypatch.setenv("REPLAY", "1")
    with TestClient(create_app(tmp_path / "runtime.db"), base_url="http://localhost") as client:
        assert 'id="workspace"' in client.get("/").text
        assert client.get("/ui/").status_code == 200
        assert client.get("/train/").status_code == 200
        assert client.get("/train/checkout.html").status_code == 200
        assert client.get("/food-demo/").status_code == 200
        assert client.get("/foodhub/").status_code == 200
        assert client.get("/quickbite/").status_code == 200
        assert client.get("/dinedash/").status_code == 200
        assert client.get("/data/food.json").json()["synthetic"] is True

