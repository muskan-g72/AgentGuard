# AgentGuard

AgentGuard is a simulated-order safety layer for agent-assisted shopping. It
contains the original train demo and a food comparison workflow. Monetary values
at authorization boundaries are whole integer rupees.

## Food workflow

The food API accepts a `FoodContract`, compares options from FoodHub, QuickBite,
and DineDash, ranks them deterministically, stages the winner, checks the staged
cart, performs one bounded fix when the checker supplies removal IDs, re-checks,
and commits only a simulated food order result after an allow decision.

Food comparison uses the checked-in replay fixtures by setting `REPLAY=1`. The
live path is implemented through TinyFish calls, but has not been verified
against a public platform.

```text
compare three platforms (parallel) -> rank -> stage winner without ordering
-> check -> optional one fix -> re-check -> simulated commit
```

`POST /food/compare` accepts a contract and platform URLs. `POST /food/run`
executes the persisted food task through the run loop. The food task and its
events are stored in the existing SQLite task store. The food commit records
events and a simulated result; it does not create a payment, collect personal
data, or write a standard `/api/orders` order snapshot.

### Food contract

```json
{
  "diet": "veg",
  "quantity": 1,
  "max_total": 300,
  "min_rating": 4.2,
  "max_eta_minutes": 45,
  "allow_extras": false,
  "priority": "price"
}
```

The common v2 names `quantity`, `max_total`, and `allow_extras` retain their
existing meanings. Food option prices, fees, coupon amounts, staged item prices,
and totals are strict integer rupees.

The effective price is item price plus delivery, platform, and packaging fees,
less the best coupon eligible on item price. A percentage coupon is capped by
its `max_discount` when one is supplied. Tips, donations, and memberships are
not part of an option's effective price.

For `priority: "taste"`, the ranker uses this displayed-rating proxy:

```text
(rating * rating_count + 3.8 * 50) / (rating_count + 50)
```

It is a ranking proxy, not a claim about actual taste or food quality.

### Food cart checks

`guard.food_checker.check_food_cart` is deterministic and has no network or
LLM dependency. It asks on a missing total or quantity; blocks a non-vegetarian
dish for a vegetarian contract, wrong quantity, forbidden tip/donation/membership
extras, over-budget total, unexplained total difference, or an unverifiable or
ineligible applied coupon. Hidden instruction-like text can tighten an otherwise
allow decision to `ask`; it cannot loosen a block.

The `guard_off` food-run option remains an explicit before/after demo bypass in
the code. It is not an authorization path for normal guarded runs.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,browser]"
.\.venv\Scripts\python.exe -m pytest -q

$env:REPLAY = "1"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

The evaluator runs each food scenario with guard off and on, three times by
default, and rewrites `docs/eval-results.md` with observed replay metrics:

```powershell
.\.venv\Scripts\python.exe scripts/eval_food.py --replay
.\.venv\Scripts\python.exe scripts/eval_food.py --live --runs 3
```

`--live` is opt-in and can invoke configured TinyFish runs. It was not run as
part of the checked-in evaluation.

## Planned

- Food-specific browser UI and a user review/confirmation screen for food contracts.
- Natural-language food-contract parsing.
- A persistent standard order snapshot for food commits, matching the train-order API.
- Production authentication, payment integration, and a verified public live-agent deployment.

## Could not verify from the code

- Live TinyFish comparison, staging, fixing, or simulated commit behavior.
- That any external platform exposes the fixture fields or honors stop-before-order instructions.
- Real-world menu availability, fees, coupons, ETAs, ratings, or taste.
- Any payment, delivery, reservation, or external order creation; the implementation is simulated.
