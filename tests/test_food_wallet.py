from __future__ import annotations

from app.food_compare import compare_all, rank_options
from guard.food_models import FoodContract, WalletEntry
from guard.food_rank import breakdown


URLS = [
    "https://demo-booking-tau.vercel.app/foodhub/",
    "https://demo-booking-tau.vercel.app/quickbite/",
    "https://demo-booking-tau.vercel.app/dinedash/",
]


def contract(priority: str = "price", maximum: int = 300) -> FoodContract:
    return FoodContract(diet="veg", quantity=1, max_total=maximum, min_rating=4.2,
                        max_eta_minutes=45, allow_extras=False, priority=priority)


def options(monkeypatch):
    monkeypatch.setenv("REPLAY", "1")
    return compare_all(URLS).options


def option(items, platform: str, restaurant: str):
    return next(item for item in items if item.platform == platform and item.restaurant == restaurant)


def test_default_breakdowns_leave_the_demo_prices_unchanged(monkeypatch):
    items = options(monkeypatch)
    foodhub = breakdown(option(items, "FoodHub", "Spice Route"))
    quickbite = breakdown(option(items, "QuickBite", "Spice Route"))
    assert foodhub == {
        "item_price": 260, "delivery": 0, "platform_fee": 5, "packaging": 15,
        "coupon": {"code": "FIRST50", "discount": 0, "eligible": False,
                   "reason": "Item price Rs 260 is below coupon minimum order Rs 300."},
        "voucher": {"code": None, "discount": 0, "eligible": False, "reason": "No voucher supplied."},
        "menu_total": 280, "effective_price": 280, "savings": 0,
    }
    assert quickbite["effective_price"] == 289
    assert quickbite["coupon"] == {"code": "SAVE40", "discount": 40, "eligible": True,
                                    "reason": "Applied before any wallet voucher."}


def test_quickbite_voucher_changes_price_ranking_and_explains_stacking(monkeypatch):
    items = options(monkeypatch)
    wallet = [WalletEntry(platform="QuickBite", kind="gift_voucher", amount=60, min_order=250, code="QB60")]
    ranked = rank_options(items, contract(), wallet)
    assert [(entry.platform, entry.restaurant) for entry in ranked.ranked] == [
        ("QuickBite", "Spice Route"), ("FoodHub", "Spice Route"),
    ]
    detail = ranked.details["|".join((ranked.ranked[0].platform, ranked.ranked[0].restaurant, ranked.ranked[0].dish, ranked.ranked[0].url))]
    assert detail["effective_price"] == 229
    assert detail["coupon"]["discount"] == 40
    assert detail["voucher"] == {"code": "QB60", "discount": 60, "eligible": True,
                                  "reason": "Applied after the eligible coupon."}


def test_wrong_platform_and_below_minimum_vouchers_are_ignored(monkeypatch):
    items = options(monkeypatch)
    foodhub = option(items, "FoodHub", "Spice Route")
    wrong = breakdown(foodhub, [WalletEntry(platform="QuickBite", kind="wallet_credit", amount=60, min_order=1, code="QB60")])
    below = breakdown(foodhub, [WalletEntry(platform="FoodHub", kind="gift_voucher", amount=60, min_order=300, code="FH60")])
    assert wrong["effective_price"] == 280
    assert wrong["voucher"]["eligible"] is False
    assert "only to QuickBite" in wrong["voucher"]["reason"]
    assert below["effective_price"] == 280
    assert below["voucher"]["eligible"] is False
    assert "below voucher minimum order Rs 300" in below["voucher"]["reason"]


def test_wallet_stacking_never_makes_the_payable_negative(monkeypatch):
    quickbite = option(options(monkeypatch), "QuickBite", "Spice Route")
    result = breakdown(quickbite, [WalletEntry(platform="QuickBite", kind="wallet_credit", amount=1000, min_order=1, code="QB1000")])
    assert result["effective_price"] == 0
    assert result["voucher"]["discount"] == 289
    assert result["savings"] == result["menu_total"]


def test_each_priority_uses_the_documented_metric_and_badges(monkeypatch):
    items = options(monkeypatch)
    expected = {"price": "FoodHub", "taste": "FoodHub", "fastest": "DineDash", "value": "FoodHub"}
    for priority, platform in expected.items():
        ranked = rank_options(items, contract(priority, maximum=350))
        assert ranked.ranked[0].platform == platform
        detail = ranked.details["|".join((ranked.ranked[0].platform, ranked.ranked[0].restaurant, ranked.ranked[0].dish, ranked.ranked[0].url))]
        assert "recommended" in detail["badges"]
        assert detail["value_formula"] == "taste_score / effective_price"
