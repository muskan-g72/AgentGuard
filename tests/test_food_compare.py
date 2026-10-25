from __future__ import annotations

from pathlib import Path
import pytest

from app.food_compare import compare_all, compare_platform, effective_price, rank_options, stage_winner, taste_score
from guard.food_models import FoodContract


URLS = [
    "https://demo-booking-tau.vercel.app/foodhub/",
    "https://demo-booking-tau.vercel.app/quickbite/",
    "https://demo-booking-tau.vercel.app/dinedash/",
]


def contract(priority: str = "price") -> FoodContract:
    return FoodContract(
        diet="veg", quantity=1, max_total=300, min_rating=4.2,
        max_eta_minutes=45, allow_extras=False, priority=priority,
    )


def test_replay_compare_all_returns_the_seven_fixture_options(monkeypatch):
    monkeypatch.setenv("REPLAY", "1")
    result = compare_all(URLS)
    assert result.failures == {}
    assert len(result.options) == 7
    assert {option.platform for option in result.options} == {"FoodHub", "QuickBite", "DineDash"}


def test_effective_prices_and_ranking_record_every_rejection(monkeypatch):
    monkeypatch.setenv("REPLAY", "1")
    options = compare_all(URLS).options
    prices = {(option.platform, option.restaurant): effective_price(option) for option in options}
    assert prices == {
        ("FoodHub", "Spice Route"): 280, ("FoodHub", "Biryani Hub"): 235,
        ("FoodHub", "Roll Point"): 175, ("QuickBite", "Spice Route"): 289,
        ("QuickBite", "Biryani Hub"): 239, ("DineDash", "Spice Route"): 308,
        ("DineDash", "Green Bowl"): 245,
    }
    ranking = rank_options(options, contract())
    assert [(option.platform, option.restaurant) for option in ranking.ranked] == [
        ("FoodHub", "Spice Route"), ("QuickBite", "Spice Route"),
    ]
    rejected = {(entry.option.platform, entry.option.restaurant): entry.reasons for entry in ranking.rejected}
    assert "not vegetarian" in rejected[("FoodHub", "Biryani Hub")]
    assert "rating 3.9 is below 4.2" in rejected[("FoodHub", "Roll Point")]
    assert "effective price Rs 308 exceeds Rs 300" in rejected[("DineDash", "Spice Route")]
    assert "rating 4.1 is below 4.2" in rejected[("DineDash", "Green Bowl")]
    assert taste_score(ranking.ranked[0]) > 4.0


def test_replay_stages_foodhub_extras_as_evidence(monkeypatch):
    monkeypatch.setenv("REPLAY", "1")
    winner = next(option for option in compare_platform(URLS[0]) if option.restaurant == "Spice Route")
    extras = stage_winner(winner.model_copy(update={"url": winner.url + "?scenario=extras"}), contract())
    assert extras.total == 320
    assert {(item.type, item.price) for item in extras.items} >= {("tip", 30), ("donation", 10)}
    clean = stage_winner(winner.model_copy(update={"url": winner.url + "?scenario=clean"}), contract())
    assert clean.total == 280
    assert all(item.type not in {"tip", "donation", "membership"} for item in clean.items)


def test_food_urls_are_limited_to_the_three_configured_paths(monkeypatch):
    from app.tinyfish_client import TinyFishError, validate_demo_url

    assert validate_demo_url(URLS[0]) == URLS[0]
    with pytest.raises(TinyFishError):
        validate_demo_url("https://demo-booking-tau.vercel.app/not-food/")
    monkeypatch.setenv("TINYFISH_FOOD_PATH_PREFIXES", "/foodhub/")
    with pytest.raises(TinyFishError):
        validate_demo_url(URLS[1])



def test_data_food_and_recordings_agree_on_all_options():
    import json
    root = Path(__file__).resolve().parents[1]
    data_path = root / "data" / "food.json"
    assert data_path.exists(), "data/food.json missing"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    data_options = data["options"]
    assert len(data_options) == 7

    rec_options = []
    for platform in ["foodhub", "quickbite", "dinedash"]:
        rec_path = root / "recordings" / "food" / f"{platform}.json"
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
        rec_options.extend(rec["options"])
    assert len(rec_options) == 7

    def opt_key(opt):
        return (opt["platform"].lower(), opt["restaurant"].lower(), opt["dish"].lower())

    data_by_key = {opt_key(o): o for o in data_options}
    rec_by_key = {opt_key(o): o for o in rec_options}
    assert set(data_by_key) == set(rec_by_key)

    for key, d_opt in data_by_key.items():
        r_opt = rec_by_key[key]
        assert d_opt["veg"] == r_opt["veg"], f"veg mismatch for {key}"
        assert d_opt["item_price"] == r_opt["item_price"], f"price mismatch for {key}"
        assert d_opt["fees"] == r_opt["fees"], f"fees mismatch for {key}"
        assert d_opt["rating"] == r_opt["rating"], f"rating mismatch for {key}"
        assert d_opt["rating_count"] == r_opt["rating_count"], f"rating_count mismatch for {key}"
        assert d_opt["eta_minutes"] == r_opt["eta_minutes"], f"eta mismatch for {key}"

        d_coupons = [{k: c[k] for k in sorted(c) if k != "description"} for c in d_opt.get("coupons", [])]
        r_coupons = [{k: c[k] for k in sorted(c) if k != "description"} for c in r_opt.get("coupons", [])]
        assert d_coupons == r_coupons, f"coupons mismatch for {key}"
