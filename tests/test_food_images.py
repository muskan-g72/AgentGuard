import json
import re
import subprocess

from fastapi.testclient import TestClient

from app.main import create_app
from app.release import PUBLIC_ASSETS, ROOT, release


IMAGE_NAMES = {
    "paneer-butter-masala.webp",
    "chicken-biryani.webp",
    "paneer-kathi-roll.webp",
    "veg-biryani.webp",
    "veg-thali.webp",
}


def test_every_food_option_has_a_safe_local_image():
    data = json.loads((ROOT / "data/food.json").read_text())
    for option in data["options"]:
        image = option["image"]
        assert re.fullmatch(r"/food-demo/images/[a-z0-9-]+\.webp", image)
        assert image.rsplit("/", 1)[1] in IMAGE_NAMES
        assert option["image_alt"].strip()
        assert (ROOT / image.lstrip("/")).is_file()
        assert "http" not in image.lower()


def test_food_image_routes_and_fallback_are_local():
    with TestClient(create_app(), base_url="http://localhost") as client:
        for name in IMAGE_NAMES:
            response = client.get(f"/food-demo/images/{name}")
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("image/webp")
        assert client.get("/food-demo/images/not-a-dish.webp").status_code == 404
    source = (ROOT / "food-demo/site.mjs").read_text(encoding="utf-8")
    assert "this.src='/food-demo/plate.svg'" in source
    assert "object-fit:cover" in (ROOT / "food-demo/styles.css").read_text(encoding="utf-8")


def test_static_release_and_bundle_include_food_images(tmp_path):
    version = release()
    for name in IMAGE_NAMES:
        path = f"food-demo/images/{name}"
        assert path in version["public_assets"]
        assert path in PUBLIC_ASSETS
    output = tmp_path / "food-sites"
    result = subprocess.run(["node", "scripts/build_food_sites.mjs", str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    for name in IMAGE_NAMES:
        assert (output / "food-demo/images" / name).is_file()
