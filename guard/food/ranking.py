"""Deterministic read-only eligibility filtering and ranking; no I/O or LLM."""

from __future__ import annotations

from pydantic import ValidationError

from .models import FoodCriteria, FoodOption, PLATFORMS, RankedOption, Ranking, RejectedOption
from .pricing import effective_price, taste_fraction, taste_score


def rank_options(criteria: FoodCriteria | dict, options: list[FoodOption | dict]) -> Ranking:
    criteria = FoodCriteria.model_validate(criteria)
    ranked, rejected = [], []
    for index, raw in enumerate(options):
        data = {key: getattr(raw, key, None) for key in ("platform", "restaurant", "dish")} if isinstance(raw, FoodOption) else raw
        metadata = data if isinstance(data, dict) else {}
        try:
            option = FoodOption.model_validate(raw)
        except ValidationError as error:
            fields = sorted({".".join(map(str, item["loc"])) or "option" for item in error.errors(include_input=False)})
            rejected.append(RejectedOption(
                index=index, platform=metadata.get("platform") if metadata.get("platform") in PLATFORMS else None,
                restaurant=metadata.get("restaurant") if isinstance(metadata.get("restaurant"), str) else None,
                dish=metadata.get("dish") if isinstance(metadata.get("dish"), str) else None,
                reasons=["Invalid option data at " + ", ".join(fields) + "."],
            ))
            continue
        reasons = []
        if option.veg is None:
            reasons.append("The dish's vegetarian status is unknown.")
        elif not option.veg:
            reasons.append("The dish does not meet the vegetarian diet requirement.")
        if option.rating is None:
            reasons.append("The restaurant rating is unknown.")
        elif option.rating < criteria.min_rating:
            reasons.append(f"Rating {option.rating:g} is below the required {criteria.min_rating:g}.")
        if option.eta_minutes is None:
            reasons.append("The delivery ETA is unknown.")
        elif option.eta_minutes > criteria.max_eta_minutes:
            reasons.append(f"ETA {option.eta_minutes} minutes exceeds the {criteria.max_eta_minutes}-minute limit.")
        try:
            price = effective_price(option)
            if price.effective_price > criteria.max_total:
                reasons.append(f"Effective price Rs {price.effective_price} exceeds your Rs {criteria.max_total} budget.")
        except ValueError as error:
            price = None
            reasons.append(str(error))
        if criteria.priority == "taste" and option.rating_count is None:
            reasons.append("The rating count needed for taste ranking is unknown.")
        if reasons:
            rejected.append(RejectedOption(index=index, platform=option.platform, restaurant=option.restaurant,
                                           dish=option.dish, reasons=reasons))
            continue
        ranked.append(RankedOption(option=option, effective_price=price.effective_price,
                                   discount=price.discount, coupon_code=price.coupon_code, taste_score=taste_score(option)))

    def key(entry):
        # Stable tie-breaking means thread completion order cannot change a winner.
        identity = (PLATFORMS.index(entry.option.platform), entry.option.restaurant, entry.option.dish, entry.option.url)
        if criteria.priority == "taste":
            return (-taste_fraction(entry.option), entry.effective_price, *identity)
        return (entry.effective_price, *identity)

    ranked.sort(key=key)
    return Ranking(ranked=ranked, rejected=rejected)
