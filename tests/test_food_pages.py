"""Public fixture routes and isolated deployment packaging, without payments."""

import json
from pathlib import Path
import shutil
import subprocess

from fastapi.testclient import TestClient

from ui.server import app

ROOT = Path(__file__).resolve().parents[1]


def test_all_platform_pages_and_public_data_are_served():
    with TestClient(app, base_url="http://localhost") as client:
        for platform in ("foodhub", "quickbite", "dinedash"):
            for page, kind in (("", "listing"), ("dish.html", "dish"), ("checkout.html", "checkout"), ("confirmation.html", "confirmation")):
                response = client.get(f"/{platform}/{page}")
                assert response.status_code == 200
                assert f'data-platform="{platform}"' in response.text
                assert f'data-page="{kind}"' in response.text
        data = client.get("/data/food.json").json()
        assert data["synthetic"] is True and len(data["options"]) == 7
        assert client.get("/food-demo/").status_code == 200
        assert client.get("/food-demo/logic.mjs").status_code == 200
        for secret in ("/data/workflow.db", "/data/private.json", "/.env", "/food-demo/vercel.json", "/foodhub/../.env"):
            assert client.get(secret).status_code == 404


def test_food_bundle_contains_only_static_fictional_fixture_files(tmp_path):
    node = shutil.which("node")
    assert node, "Node is required for the frontend tests and copy-only bundle"
    target = tmp_path / "static-food"
    subprocess.run([node, str(ROOT / "scripts/build_food_sites.mjs"), str(target)], cwd=ROOT, check=True, capture_output=True)
    assert {file.name for file in target.iterdir()} == {"foodhub", "quickbite", "dinedash", "food-demo", "data", "vercel.json"}
    assert list((target / "data").iterdir()) == [target / "data/food.json"]
    assert len(list(target.glob("*/*.html"))) == 13
    assert json.loads((target / "data/food.json").read_text())["synthetic"] is True
    config = json.loads((target / "vercel.json").read_text())
    assert config["framework"] is None
    assert not any(file.suffix in (".py", ".db", ".sqlite3") or file.name.startswith(".env") for file in target.rglob("*"))
    # Refuse unrelated files rather than delete or upload them.
    (target / "data" / "private.db").write_text("preserve me")
    result = subprocess.run([node, str(ROOT / "scripts/build_food_sites.mjs"), str(target)], cwd=ROOT, capture_output=True)
    assert result.returncode != 0
    assert (target / "data" / "private.db").read_text() == "preserve me"
