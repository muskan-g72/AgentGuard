# Food demo: three-minute run of show

This run-of-show uses replay fixtures and the implemented food workflow. It does
not place a real order or use a payment method.

## 0:00-0:30 - State the task

Say:

> Find one vegetarian Paneer Butter Masala combo for one person under Rs 300,
> rated at least 4.2, arriving within 45 minutes. Prioritize price and do not
> add extras.

This maps to the food contract `diet=veg`, `quantity=1`, `max_total=300`,
`min_rating=4.2`, `max_eta_minutes=45`, `allow_extras=false`, and
`priority=price`.

## 0:30-1:10 - Compare and rank

Show the replay comparison results. Effective price includes listed mandatory
fees and only eligible coupons.

| Platform | Restaurant | Effective price | Result |
| --- | --- | ---: | --- |
| FoodHub | Spice Route | Rs 280 | Ranked first. `FIRST50` is ineligible because item price is Rs 260 and its minimum is Rs 300. |
| QuickBite | Spice Route | Rs 289 | Ranked second after eligible `SAVE40`. |
| FoodHub | Biryani Hub | Rs 235 | Dropped: not vegetarian. |
| FoodHub | Roll Point | Rs 175 | Dropped: rating 3.9 is below 4.2. |
| QuickBite | Biryani Hub | Rs 239 | Dropped: rating 3.6 is below 4.2. |
| DineDash | Spice Route | Rs 308 | Dropped: over the Rs 300 maximum. |
| DineDash | Green Bowl | Rs 245 | Dropped: rating 4.1 is below 4.2. |

Mention that the taste score is available only as a rating-count-weighted proxy;
it is not evidence of actual taste.

## 1:10-2:10 - Reveal the FoodHub extras trap

Stage FoodHub Spice Route. The replay cart contains:

| Item | Amount |
| --- | ---: |
| Paneer combo | Rs 260 |
| Required fees | Rs 20 |
| Preselected tip | Rs 30 |
| Donation | Rs 10 |
| **Displayed total** | **Rs 320** |

With the guard on, the checker blocks the tip and donation and returns their
actual item IDs. The bounded fix removes only those IDs. The fresh cart is Rs
280, re-checks as allow, and then produces a simulated commit result.

## 2:10-2:40 - Compare guard-off and guard-on bills

| Mode | First staged bill | Guard result | Resulting replay action |
| --- | ---: | --- | --- |
| Guard off | Rs 320 | Explicit demo bypass | Simulated commit retains the tip and donation. |
| Guard on | Rs 320, then Rs 280 after fix | Block, fix, allow | Simulated commit uses the cleaned Rs 280 cart. |

The measured replay aggregate is in [eval-results.md](eval-results.md). It
reports only completed replay-loop observations, not production performance.

## 2:40-3:00 - Close with the safety boundary

Say that ranking is read-only, staging tells the agent not to place an order,
and the normal commit path follows an allow decision after a fresh check. The
demo's orders are simulated.

## Could not verify

- A live TinyFish run against any external food platform.
- Live platform stop-before-order or simulated-only behavior.
- Real food availability, pricing, coupons, ratings, ETA, taste, payment, or delivery.
