# Three-minute food demo

## 0:00–0:30 — state the contract

Say: “Order one vegetarian meal, under Rs 300, with rating at least 4.2, delivery within 45 minutes. Prefer price. No extras.”

Show:

```json
{"diet":"veg","quantity":1,"max_total":300,"min_rating":4.2,"max_eta_minutes":45,"allow_extras":false,"priority":"price"}
```

## 0:30–1:10 — compare and rank

Call `POST /food/compare` with the FoodHub, QuickBite, and DineDash URLs. Explain that effective price includes required fees and eligible coupons. Taste is a proxy based on rating and rating count.

| Platform | Restaurant / dish | Effective price | Result |
| --- | --- | ---: | --- |
| FoodHub | Spice Route — Paneer Butter Masala combo | Rs 280 | Recommended |
| QuickBite | Spice Route — Paneer Butter Masala combo | Rs 289 | Ranked second |
| FoodHub | Biryani Hub — Chicken Biryani | Rs 235 | Dropped: not vegetarian |
| FoodHub | Roll Point — Paneer Kathi Roll | Rs 175 | Dropped: rating 3.9 is below 4.2 |
| QuickBite | Biryani Hub — Veg Biryani | Rs 239 | Dropped: rating 3.6 is below 4.2 |
| DineDash | Spice Route — Paneer Butter Masala combo | Rs 308 | Dropped: over Rs 300 cap |
| DineDash | Green Bowl — Veg Thali | Rs 245 | Dropped: rating 4.1 is below 4.2 |

## 1:10–2:05 — show the FoodHub extras trap

Run the recommended FoodHub option with `?scenario=extras`. The staged cart is Rs 320:

| Item | Price |
| --- | ---: |
| Dish | Rs 260 |
| Required fees | Rs 20 |
| Pre-ticked tip | Rs 30 |
| Pre-ticked donation | Rs 10 |

With the guard on, the food checker blocks the tip and donation, returns their IDs, and the fix run removes only those IDs. The re-check allows the clean Rs 280 cart. The commit event then records a simulated order.

## 2:05–2:40 — compare guard off and guard on

Run the same task with `guard_off: true`. Point out the recorded `food_guard_off_enabled` and `food_guard_off_bypass` events. The simulated bill remains Rs 320.

Run with the guard on. The recorded bill after the bounded fix is Rs 280. The difference is Rs 40, from the tip and donation.

## 2:40–3:00 — show evidence

Open `GET /tasks/{task_id}` and read the timeline: compare, rank, stage, decision, fix, re-check, commit. Explain that the normal commit path requires an allow decision and unchanged staged-cart hash. Orders are simulated; no payment is taken.

## What this script does not show

Live food-platform deployment and live TinyFish browser runs are **Planned** verification. The current demo uses checked-in replay fixtures.
