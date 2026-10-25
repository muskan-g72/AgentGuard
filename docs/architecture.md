# Architecture

## Shared train flow

`guard/models.py` defines the train Schema v2 messages. Money is integer rupees. `guard/checker.py` checks a train cart without network or LLM calls. `app/store.py` stores tasks and appends hash-chained events. `app/workflow.py` stages, checks, removes returned extras once, re-checks, and can submit a simulated train order through the existing backend flow.

`app/main.py` exposes train task, cart, stage, event, receipt, and order routes. Train confirmation validates the stored approval, contract hash, cart hash, and outgoing request before creating one immutable simulated order.

## Food flow

Food models are separate from the train schema:

- `guard/food_models.py`: `FoodContract`, `FoodOption`, coupon, wallet, fee, and staged food-cart models.
- `guard/food_checker.py`: deterministic staged-cart checks.
- `app/food_compare.py`: platform comparison, coupon eligibility, effective price, taste proxy, ranking, fixture replay, and TinyFish adapter calls.
- `app/food_workflow.py`: food stage, check, fix, re-check, and commit adapter.

The food contract contains:

```json
{"diet":"veg","quantity":1,"max_total":300,"min_rating":4.2,"max_eta_minutes":45,"allow_extras":false,"priority":"price"}
```

`POST /food/compare` calls comparison and ranking. It accepts an optional wallet list, creates a food task, and writes `food_compare_done` and `food_ranked` events. It returns ranked options, dropped options with reasons, the recommended option, failed platforms, and the task ID.

`POST /food/run` reads the stored recommendation. It writes events for staging, decision, optional fix, re-check, and commit. The normal food commit gate requires task status `allowed`, a stored `allow` decision, and a cart hash matching the cart recorded at check time. A confirmed simulated total must equal the staged total.

`guard_off` is an explicit before/after-demo bypass. It skips the food check and normal food commit gate and writes `food_guard_off_enabled` and `food_guard_off_bypass` events.

## Comparison and ranking

FoodHub, QuickBite, and DineDash are simulated paths under `https://demo-booking-tau.vercel.app/`. In replay mode, `recordings/food/foodhub.json`, `quickbite.json`, and `dinedash.json` provide labelled fixture data.

Each option has an itemized breakdown: item price, delivery, platform fee, packaging, coupon, voucher, menu total, effective price, and savings. Effective price is item price plus listed fees, less the best eligible coupon and then one eligible wallet entry from that platform. Both use item price for their minimum-order check. A voucher cannot reduce the payable below zero. Tip, donation, and membership are extras and are not part of comparison price.

The taste score is `(rating * rating_count + 3.8 * 50) / (rating_count + 50)`. It is only a ranking proxy, not a factual measure of taste. The response includes the rating, count, first two snippets, and up to three matches from a fixed taste-word list. It supports `price`, `taste`, `fastest`, and `value` priorities. Value is `taste_score / effective_price`. Rows are labelled with the applicable cheapest, best-taste, fastest, best-value, and recommended badges.

Replay fixtures do not represent a voucher line in the staged checkout. The current implementation applies wallet entries only to comparison and ranking in replay. It returns `wallet_scope: "comparison_and_ranking_only"` and `wallet_applied_to_staging: false`. The food checker uses the recorded checkout price rather than a voucher-adjusted claim.

## Planned work

- Verify live food paths and TinyFish results after deployment.
- Add explicit food-contract confirmation before `POST /food/run`.
- Add more than one food-fix attempt if product requirements permit it.
- Provide a production authorization mode; `guard_off` is demo-only.
- Apply wallet credit to staged checkout evidence when live platforms reliably expose voucher lines.

## What is simulated

Train inventory, food options, carts, fees, coupons, order IDs, and orders are demo data. No real payment, reservation, or personal-data submission is implemented.
