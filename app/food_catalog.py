"""Read the explicitly synthetic shared fixture file; perform no network I/O."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urljoin

from guard.food.models import FoodCriteria, FoodOption, PLATFORMS

from .food_compare import compare_platforms

CATALOG = Path(__file__).resolve().parents[1] / "data" / "food.json"


def load_food_options(path: Path = CATALOG, *, base_url: str = "https://food-demo.example") -> list[FoodOption]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("synthetic") is not True:
        raise ValueError("This loader is for explicitly labelled synthetic fixtures")
    options = []
    for row in data["options"]:
        values = {key: value for key, value in row.items() if key != "id"}
        values["url"] = urljoin(base_url.rstrip("/") + "/", values["url"])
        options.append(FoodOption.model_validate(values))
    return options


def compare_food_fixtures(criteria: FoodCriteria | dict, *, base_url: str = "https://food-demo.example"):
    snapshot = load_food_options(base_url=base_url)
    readers = {platform: (lambda _criteria, platform=platform: [option.model_copy(deep=True)
               for option in snapshot if option.platform == platform]) for platform in PLATFORMS}
    return compare_platforms(criteria, readers)
