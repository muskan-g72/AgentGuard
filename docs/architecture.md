# Architecture

The authoritative runtime is `app.main:app`. It serves the dashboard at `/`,
the `/ui/` compatibility alias, train fixtures under `/train/`, and food entry
and fixture routes. `ui.server` remains a development compatibility shim only;
the dashboard calls same-origin task routes directly.

## Shared train flow

`guard/models.py` defines the train Schema v2 messages. Money is integer rupees. `guard/checker.py` checks a train cart without network or LLM calls. `app/store.py` stores tasks and appends hash-chained events. `app/workflow.py` stages, checks, removes returned extras once, re-checks, and can submit a simulated train order through the existing backend flow.

`app/main.py` exposes train task, cart, stage, event, receipt, and order routes. Train confirmation validates the stored approval, contract hash, cart hash, and outgoing request before creating one immutable simulated order.

## Food flow

Food models are separate from the train schema:

- `guard/food_models.py`: `FoodContract`, `FoodOption`, coupon, fee, and staged food-cart models.
- `guard/food_checker.py`: deterministic staged-cart checks.
- `app/food_compare.py`: platform comparison, coupon eligibility, effective price, taste proxy, ranking, fixture replay, and TinyFish adapter calls.
- `app/food_workflow.py`: food stage, check, fix, re-check, and commit adapter.

The food contract contains:

```json
{"diet":"veg","quantity":1,"max_total":300,"min_rating":4.2,"max_eta_minutes":45,"allow_extras":false,"priority":"price"}
```

`POST /food/compare` calls comparison and ranking. It creates a food task and writes `food_compare_done` and `food_ranked` events. It returns ranked options, dropped options with reasons, the recommended option, failed platforms, and the task ID.

`POST /food/{task_id}/confirm` explicitly authorizes the food contract. Until
that call, `POST /food/run` returns a conflict. The confirmed contract is
immutable. `/food/run` then writes events for staging, decision, optional fix,
re-check, and commit. Successful food commits are persisted in `food_orders`,
retrievable through `/api/orders/{order_id}`, and included in signed receipts.

The public food schema does not accept `guard_off`. Before/after measurements
use private evaluator state only; a normal browser caller cannot bypass the food
checker or commit gate.

## Comparison and ranking

FoodHub, QuickBite, and DineDash are simulated paths under `https://demo-booking-tau.vercel.app/`. In replay mode, `recordings/food/foodhub.json`, `quickbite.json`, and `dinedash.json` provide labelled fixture data.

Effective price is item price plus delivery, platform, and packaging fees, less the largest eligible coupon discount. A coupon is eligible when its minimum order is no greater than item price. Percent discounts are capped by `max_discount` when supplied. Tip, donation, and membership are extras and are not part of effective price.

The taste score is `(rating * rating_count + 3.8 * 50) / (rating_count + 50)`. It is only a ranking proxy, not a factual measure of taste.

## Planned work

- Verify live food paths and TinyFish results after deployment.
- Add session ownership and authenticated public-demo access before deployment.
- Add more than one food-fix attempt if product requirements permit it.
- Provide a production authorization mode; `guard_off` is demo-only.

## What is simulated

Train inventory, food options, carts, fees, coupons, order IDs, and orders are demo data. No real payment, reservation, or personal-data submission is implemented.
