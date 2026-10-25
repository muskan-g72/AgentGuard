"""Pure, deterministic food comparison arithmetic and ranking."""

from __future__ import annotations

from .food_models import Coupon, FoodContract, FoodOption, WalletEntry


TASTE_WORDS = ("crispy", "creamy", "spicy", "fresh", "soft", "flavourful", "rich", "hot")


def _coupon_discount(option: FoodOption, coupon: Coupon) -> int | None:
    if option.item_price < coupon.min_order:
        return None
    if coupon.type == "flat":
        return coupon.value
    discount = option.item_price * coupon.value // 100
    return min(discount, coupon.max_discount) if coupon.max_discount is not None else discount


def _best_coupon(option: FoodOption) -> tuple[Coupon | None, int, str]:
    if not option.coupons:
        return None, 0, "No coupon is available."
    eligible = [(coupon, _coupon_discount(option, coupon)) for coupon in option.coupons]
    eligible = [(coupon, discount) for coupon, discount in eligible if discount is not None]
    if not eligible:
        minimum = min(coupon.min_order for coupon in option.coupons)
        return option.coupons[0], 0, f"Item price Rs {option.item_price} is below coupon minimum order Rs {minimum}."
    coupon, discount = min(eligible, key=lambda entry: (-entry[1], entry[0].code))
    return coupon, discount, "Applied before any wallet voucher."


def eligible_coupon(option: FoodOption) -> Coupon | None:
    """Return the best eligible coupon, deterministically breaking ties by code."""

    coupon, discount, _ = _best_coupon(option)
    return coupon if discount else None


def _best_voucher(option: FoodOption, wallet: list[WalletEntry], payable: int) -> tuple[WalletEntry | None, int, bool, str]:
    matching = [entry for entry in wallet if entry.platform.casefold() == option.platform.casefold()]
    if not matching:
        if wallet:
            return wallet[0], 0, False, f"Voucher applies only to {wallet[0].platform}, not {option.platform}."
        return None, 0, False, "No voucher supplied."
    eligible = [entry for entry in matching if option.item_price >= entry.min_order]
    if not eligible:
        minimum = min(entry.min_order for entry in matching)
        return matching[0], 0, False, f"Item price Rs {option.item_price} is below voucher minimum order Rs {minimum}."
    entry = min(eligible, key=lambda value: (-min(value.amount, payable), value.code))
    return entry, min(entry.amount, payable), True, "Applied after the eligible coupon."


def breakdown(option: FoodOption, wallet: list[WalletEntry] | None = None) -> dict:
    """Explain every component of an option's payable price using integer rupees."""

    wallet = wallet or []
    menu_total = option.item_price + option.fees.delivery + option.fees.platform + option.fees.packaging
    coupon, coupon_discount, coupon_reason = _best_coupon(option)
    payable_after_coupon = max(0, menu_total - coupon_discount)
    voucher, voucher_discount, voucher_eligible, voucher_reason = _best_voucher(option, wallet, payable_after_coupon)
    effective = max(0, payable_after_coupon - voucher_discount)
    return {
        "item_price": option.item_price,
        "delivery": option.fees.delivery,
        "platform_fee": option.fees.platform,
        "packaging": option.fees.packaging,
        "coupon": {"code": coupon.code if coupon else None, "discount": coupon_discount, "eligible": coupon_discount > 0, "reason": coupon_reason},
        "voucher": {"code": voucher.code if voucher else None, "discount": voucher_discount, "eligible": voucher_eligible, "reason": voucher_reason},
        "menu_total": menu_total,
        "effective_price": effective,
        "savings": menu_total - effective,
    }


def effective_price(option: FoodOption, wallet: list[WalletEntry] | None = None) -> int:
    return breakdown(option, wallet)["effective_price"]


def taste_score(option: FoodOption) -> float:
    """A rating-count-weighted proxy, never presented as ground truth."""

    return (option.rating * option.rating_count + 3.8 * 50) / (option.rating_count + 50)


def taste_keywords(option: FoodOption) -> list[str]:
    text = " ".join(option.review_snippets).casefold()
    return [word for word in TASTE_WORDS if word in text][:3]


def _dropped_reasons(contract: FoodContract, option: FoodOption, price: int) -> list[str]:
    reasons: list[str] = []
    if contract.diet == "veg" and not option.veg:
        reasons.append("not vegetarian")
    if option.rating < contract.min_rating:
        reasons.append(f"rating {option.rating:g} is below {contract.min_rating:g}")
    if option.eta_minutes > contract.max_eta_minutes:
        reasons.append(f"ETA {option.eta_minutes} exceeds {contract.max_eta_minutes} minutes")
    if price > contract.max_total:
        reasons.append(f"effective price Rs {price} exceeds Rs {contract.max_total}")
    return reasons


def _identity(option: FoodOption) -> tuple[str, str, str, str]:
    return option.platform, option.restaurant, option.dish, option.url


def _why(option: FoodOption, detail: dict) -> list[str]:
    coupon = detail["coupon"]
    return [
        "Vegetarian dish.",
        f"Rating {option.rating:g} meets the minimum.",
        f"ETA {option.eta_minutes} minutes is within the maximum.",
        f"Effective price is Rs {detail['effective_price']}.",
        f"Coupon {coupon['code']} applied." if coupon["eligible"] else coupon["reason"],
    ]


def rank(contract: FoodContract, options: list[FoodOption], wallet: list[WalletEntry] | None = None) -> dict:
    """Drop disallowed options and rank survivors without I/O or an LLM."""

    ranked: list[dict] = []
    dropped: list[dict] = []
    for option in options:
        price_breakdown = breakdown(option, wallet)
        price = price_breakdown["effective_price"]
        reasons = _dropped_reasons(contract, option, price)
        score = taste_score(option)
        detail = {**price_breakdown, "taste_score": score, "value_score": score / price if price else None,
                  "value_formula": "taste_score / effective_price", "rating": option.rating,
                  "rating_count": option.rating_count, "review_snippets": option.review_snippets[:2],
                  "taste_keywords": taste_keywords(option)}
        if reasons:
            dropped.append({"option": option, "reasons": reasons, "detail": detail})
        else:
            ranked.append({"option": option, "detail": detail, "effective_price": price,
                           "taste_score": score, "why": _why(option, detail)})

    sorters = {
        "price": lambda entry: (entry["detail"]["effective_price"], -entry["detail"]["taste_score"], _identity(entry["option"])),
        "taste": lambda entry: (-entry["detail"]["taste_score"], entry["detail"]["effective_price"], _identity(entry["option"])),
        "fastest": lambda entry: (entry["option"].eta_minutes, entry["detail"]["effective_price"], _identity(entry["option"])),
        "value": lambda entry: (-(entry["detail"]["value_score"] if entry["detail"]["value_score"] is not None else float("inf")), entry["detail"]["effective_price"], _identity(entry["option"])),
    }
    ranked.sort(key=sorters[contract.priority])
    if ranked:
        cheapest = min(entry["detail"]["effective_price"] for entry in ranked)
        best_taste = max(entry["detail"]["taste_score"] for entry in ranked)
        fastest = min(entry["option"].eta_minutes for entry in ranked)
        best_value = max(entry["detail"]["value_score"] if entry["detail"]["value_score"] is not None else float("inf") for entry in ranked)
        for index, entry in enumerate(ranked):
            badges = []
            if entry["detail"]["effective_price"] == cheapest:
                badges.append("cheapest")
            if entry["detail"]["taste_score"] == best_taste:
                badges.append("best_taste")
            if entry["option"].eta_minutes == fastest:
                badges.append("fastest")
            if (entry["detail"]["value_score"] if entry["detail"]["value_score"] is not None else float("inf")) == best_value:
                badges.append("best_value")
            if index == 0:
                badges.append("recommended")
            entry["detail"]["badges"] = badges
    return {"ranked": ranked, "dropped": dropped}
