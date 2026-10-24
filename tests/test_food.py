"""Synthetic food comparison tests; none of these are real restaurant claims."""

import itertools
import threading
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.food_catalog import compare_food_fixtures, load_food_options
from app.food_compare import compare_platforms
from guard.food.models import FoodCriteria, FoodOption, PLATFORMS
from guard.food.pricing import effective_price, taste_score
from guard.food.ranking import rank_options


def option(**changes):
    raw = {"platform": "FoodHub", "restaurant": "Synthetic Test Kitchen", "dish": "Synthetic bowl", "veg": True,
           "item_price": 250, "rating": 4.4, "rating_count": 100, "eta_minutes": 35,
           "fees": {"delivery": 20, "platform": 10, "packaging": 10}, "coupons": [],
           "review_snippets": ["Synthetic review one.", "Synthetic review two.", "Synthetic review three."],
           "url": "https://food-fixture.example/dish"}
    raw.update(changes)
    return FoodOption.model_validate(raw)


def coupon(code="TEST", *, kind="flat", value=50, cap=50, minimum=250):
    return {"code": code, "type": kind, "value": value, "max_discount": cap, "min_order": minimum}


def test_best_eligible_coupon_does_not_stack_or_use_fees_for_eligibility():
    row = option(coupons=[coupon("TOO_HIGH", value=150, minimum=280), coupon("FLAT40", value=40),
                          coupon("HALF", kind="percent", value=50, cap=70)])
    result = effective_price(row)
    assert result.subtotal == 290
    assert result.discount == 70
    assert result.effective_price == 220
    assert result.coupon_code == "HALF"


def test_percentage_rounds_down_and_flat_discount_ignores_percentage_cap():
    assert effective_price(option(item_price=249, coupons=[coupon(kind="percent", value=15, cap=100, minimum=200)])).discount == 37
    assert effective_price(option(coupons=[coupon(value=60, cap=0)])).discount == 60
    assert effective_price(option(coupons=[coupon(kind="percent", value=100, cap=0)])).discount == 0


def test_coupon_ties_are_stable_and_oversized_coupons_fail_closed():
    coupons = [coupon("B"), coupon("A")]
    for ordered in itertools.permutations(coupons):
        assert effective_price(option(coupons=list(ordered))).coupon_code == "A"
    with pytest.raises(ValueError, match="exceeds"):
        effective_price(option(coupons=[coupon(value=1000)]))


@pytest.mark.parametrize("value", ["250", 250.0, 250.5, True, -1, Decimal("250")])
def test_money_never_coerces_strings_floats_bools_or_decimal(value):
    with pytest.raises(ValidationError):
        option(item_price=value)
    with pytest.raises(ValidationError):
        option(fees={"delivery": value, "platform": 10, "packaging": 10})
    with pytest.raises(ValidationError):
        option(coupons=[coupon(value=value)])
    with pytest.raises(ValidationError):
        FoodCriteria(max_total=value)


@pytest.mark.parametrize("changes", [{"quantity": 2}, {"quantity": True}, {"allow_extras": True},
                                     {"min_rating": float("nan")}, {"max_eta_minutes": 45.5}])
def test_invalid_comparison_criteria_do_not_proceed(changes):
    with pytest.raises(ValidationError):
        FoodCriteria(**changes)


def test_unknown_needed_facts_are_rejected_without_assuming_zero():
    ranking = rank_options({}, [option(veg=None, rating=None, eta_minutes=None,
                                      fees={"delivery": None, "platform": 0, "packaging": 0})])
    assert ranking.ranked == []
    assert len(ranking.rejected[0].reasons) == 4


def test_all_failing_constraints_are_recorded_and_boundaries_are_inclusive():
    ranking = rank_options({}, [option(veg=False, rating=4.1, eta_minutes=46, item_price=301),
                               option(rating=4.2, eta_minutes=45, item_price=260)])
    assert len(ranking.rejected[0].reasons) == 4
    assert len(ranking.ranked) == 1
    assert ranking.ranked[0].effective_price == 300


def test_taste_proxy_shrinks_low_counts_and_zero_count_to_prior():
    assert taste_score(option(rating=5.0, rating_count=0)) == 3.8
    assert taste_score(option(rating=4.4, rating_count=100)) == pytest.approx((4.4 * 100 + 3.8 * 50) / 150)
    ranking = rank_options({"priority": "taste"}, [option(dish="Few ratings", rating=4.9, rating_count=1),
                                                  option(dish="Many ratings", rating=4.5, rating_count=500)])
    assert ranking.ranked[0].option.dish == "Many ratings"


def test_taste_priority_uses_price_on_a_taste_tie():
    ranking = rank_options({"priority": "taste"}, [option(dish="Expensive", item_price=250), option(dish="Cheaper", item_price=200)])
    assert [row.option.dish for row in ranking.ranked] == ["Cheaper", "Expensive"]
    assert rank_options({"priority": "taste"}, [option(rating_count=None)]).ranked == []
    assert rank_options({"priority": "price"}, [option(rating_count=None)]).ranked[0].taste_score is None


def test_invalid_extra_fields_and_mutated_models_cannot_be_ranked():
    raw = option().model_dump()
    raw["tip"] = 30
    ranking = rank_options({}, [raw])
    assert ranking.ranked == []
    assert "tip" in ranking.rejected[0].reasons[0]
    mutated = option()
    mutated.item_price = "250"
    assert rank_options({}, [mutated]).ranked == []


def test_parallel_sources_are_really_concurrent_and_ties_are_repeatable():
    barrier = threading.Barrier(3, timeout=5)
    seen = set()
    lock = threading.Lock()
    def reader(platform):
        def compare(criteria):
            with lock:
                seen.add(platform)
            barrier.wait()
            criteria.max_total = 0  # Each reader receives an isolated copy.
            return [option(platform=platform)]
        return compare
    report = compare_platforms({}, {platform: reader(platform) for platform in PLATFORMS})
    assert seen == set(PLATFORMS)
    assert report.complete is True
    assert report.winner.option.platform == "FoodHub"
    assert [entry.option.platform for entry in report.ranked] == list(PLATFORMS)


def test_partial_failures_or_wrong_provenance_never_select_a_winner():
    def failed(_criteria):
        raise RuntimeError("vendor-secret-do-not-log")
    readers = {platform: lambda _criteria, p=platform: [option(platform=p)] for platform in PLATFORMS}
    readers["QuickBite"] = failed
    report = compare_platforms({}, readers)
    assert report.complete is False and report.winner is None
    assert len(report.ranked) == 2
    assert "vendor-secret" not in report.model_dump_json()
    readers["QuickBite"] = lambda _criteria: [option(platform="DineDash")]
    assert compare_platforms({}, readers).winner is None
    readers["QuickBite"] = lambda _criteria: [{"platform": "QuickBite", "item_price": "250"}]
    assert compare_platforms({}, readers).winner is None
    with pytest.raises(ValueError, match="exactly"):
        compare_platforms({}, {"FoodHub": lambda _: []})


def test_no_match_is_a_completed_comparison_without_a_winner():
    report = compare_platforms({}, {platform: lambda _criteria: [] for platform in PLATFORMS})
    assert report.complete and report.winner is None and report.ranked == []


def test_synthetic_catalog_prices_and_expected_priority_choices():
    rows = load_food_options()
    assert len(rows) == 7
    assert all(len(row.review_snippets) == 3 for row in rows)
    assert [effective_price(row).effective_price for row in rows] == [280, 235, 175, 289, 239, 308, 245]
    foodhub = next(row for row in rows if row.platform == "FoodHub" and row.restaurant == "Spice Route")
    assert effective_price(foodhub).effective_price == 280
    assert effective_price(foodhub).coupon_code is None
    assert 280 + 30 + 10 == 320
    price = compare_food_fixtures({"priority": "price"})
    taste = compare_food_fixtures({"priority": "taste"})
    assert price.complete and price.winner.option.platform == "FoodHub"
    assert taste.winner.option.platform == "FoodHub"
    assert len(price.rejected) == 5
    assert [entry.effective_price for entry in price.ranked] == [280, 289]


def test_flat_coupon_may_have_no_cap_but_percent_cap_must_be_known():
    assert effective_price(option(coupons=[coupon(cap=None)])).discount == 50
    with pytest.raises(ValidationError, match="known max_discount"):
        option(coupons=[coupon(kind="percent", cap=None)])
