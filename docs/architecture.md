# Architecture

## Shared guard foundation

`guard/models.py` defines the strict v2 train contract/cart/order messages and
the common `Decision` type. The original train checker, request checker, task
store, approval binding, receipt chain, and simulated train order flow remain in
place. All money at these boundaries is a whole JSON integer.

## Food compare and guarded run loop

Food-specific messages live in `guard/food_models.py` rather than changing the
train contract schema:

| Model | Purpose |
| --- | --- |
| `FoodContract` | Vegetarian requirement, quantity, budget, rating/ETA limits, extras policy, and ranking priority. |
| `FoodOption` | Read-only comparison result from one platform. |
| `Fees`, `Coupon` | Integer delivery/platform/packaging fees and coupon terms. |
| `StagedFoodCart` | Checkout evidence: typed items, coupon code/details, quantity, total, ETA, vegetarian evidence, and hidden text. |

`guard/food_rank.py` is pure logic. It selects the best eligible coupon, derives
effective price and taste proxy, drops noncompliant options with recorded
reasons, and ranks survivors. The three configured demo paths are FoodHub,
QuickBite, and DineDash under `https://demo-booking-tau.vercel.app/`.

`app/food_compare.py` runs platform comparisons concurrently. In replay mode it
loads `recordings/food/{foodhub,quickbite,dinedash}.json`. In live mode it starts
TinyFish runs, polls them, validates structured output, and saves live raw
responses under ignored `recordings/food/live/` paths. Live behavior is
unverified.

```text
FoodContract + three platform URLs
  -> compare_all (parallel)
  -> guard.food_rank.rank
  -> Store.create_food_task (comparison/ranking events)
  -> app.food_workflow.run_food_task
       -> stage_winner (stops before order)
       -> guard.food_checker.check_food_cart
       -> one fix_staged_cart pass only when removal IDs exist
       -> re-check
       -> commit_staged_order only after allow
```

The normal guarded path records `food_stage_started`, `food_staged`,
`food_decision`, optional fix/recheck events, and simulated commit events in the
same SQLite task event chain. `app/food_workflow.py` verifies task status,
stored decision, cart hash, and cart total before its guarded commit call.

`guard_off` is implemented as an explicit demo bypass in the food workflow and
is used by the evaluator for before/after measurement. It is not part of the
normal guarded path.

## Food checker

`guard/food_checker.py` is deterministic and has no network or LLM calls. In
order, it asks for missing total/quantity, blocks non-vegetarian food for a veg
contract, blocks a quantity mismatch, blocks unauthorized tip/donation/membership
items with their actual IDs, blocks budget and unexplained-total differences,
blocks an unverifiable/ineligible applied coupon, and asks on hidden
instruction-like text only after the preceding checks allow. `guard.checker`
re-exports this function for compatibility.

## Simulation boundary

The food commit prompt instructs the agent to proceed only when the site itself
identifies the order as simulated and to avoid payment or personal data. In
replay it returns a fixture-like simulated order ID. The code does not integrate
a payment provider. Food commits currently record task events rather than a
normal immutable `/api/orders` snapshot.

## Evaluation

`scripts/eval_food.py` runs `clean`, `extras`, `qty2`, `hidden`, and `nototal`
through the existing food run loop, guard off and on, for a configurable number
of repetitions. It defaults to replay and writes measured observations to
`docs/eval-results.md`. It defines its rates in that generated document; it does
not claim external-agent or production performance.

## Planned

- Food browser UI and user-facing food-contract review.
- Natural-language food contract parsing.
- Persistent food order snapshots through the standard order API.
- Verified live TinyFish/public deployment behavior.
- Payment, delivery, reservation, or external-order integrations.

## Could not verify from the code

- That a live platform is reachable or returns complete, accurate option/cart evidence.
- Stop-before-order and simulated-only behavior of a live TinyFish run.
- Any real payment, restaurant order, delivery, coupon redemption, ETA, rating, or taste claim.
