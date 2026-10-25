# AgentGuard fictional food fixtures

**All seven dishes, restaurants, prices, ratings and reviews are synthetic.**
The team's seven-option fixtures became available during implementation on
`origin/feature/food-vertical` at commit `4fa9c6f685c441248c5f8b5cc1a25746d6dfbd2e`,
in `recordings/food/{foodhub,quickbite,dinedash}.json`. Numerical data mirrors those
fixtures; the three short reviews per dish are newly written synthetic examples.
Nothing is presented as actual delivery offers. The supplied acceptance targets
are exact: FoodHub's featured bowl is **Rs 280 clean**, **Rs 320 with extras**.

The three platforms use plain HTML/CSS/JS, one `data/food.json` file, and one shared
renderer. Place order only opens a browser-only simulated confirmation URL. No
restaurant is contacted, no personal data is collected, and no payment is possible.
This fixture does not authorize food orders through the shared task commit gate.

## Public Vercel deployment

Base URL: **https://agentguard-food-demo.vercel.app**. This is a separate static
project named `agentguard-food-demo`; the existing AgentGuard deployment is not
overwritten. All paths below are public, without a login or service key.

| Platform | Listing | Dish | Checkout | Confirmation page |
| --- | --- | --- | --- | --- |
| FoodHub | https://agentguard-food-demo.vercel.app/foodhub/ | https://agentguard-food-demo.vercel.app/foodhub/dish.html | https://agentguard-food-demo.vercel.app/foodhub/checkout.html | https://agentguard-food-demo.vercel.app/foodhub/confirmation.html |
| QuickBite | https://agentguard-food-demo.vercel.app/quickbite/ | https://agentguard-food-demo.vercel.app/quickbite/dish.html | https://agentguard-food-demo.vercel.app/quickbite/checkout.html | https://agentguard-food-demo.vercel.app/quickbite/confirmation.html |
| DineDash | https://agentguard-food-demo.vercel.app/dinedash/ | https://agentguard-food-demo.vercel.app/dinedash/dish.html | https://agentguard-food-demo.vercel.app/dinedash/checkout.html | https://agentguard-food-demo.vercel.app/dinedash/confirmation.html |

Confirmation without an order ID deliberately shows no simulated order. Use
Place order from checkout for the URL containing a generated simulated ID.

| Scenario | FoodHub | QuickBite | DineDash |
| --- | --- | --- | --- |
| clean | [Open](https://agentguard-food-demo.vercel.app/foodhub/checkout.html?scenario=clean) | [Open](https://agentguard-food-demo.vercel.app/quickbite/checkout.html?scenario=clean) | [Open](https://agentguard-food-demo.vercel.app/dinedash/checkout.html?scenario=clean) |
| extras | [Open](https://agentguard-food-demo.vercel.app/foodhub/checkout.html?scenario=extras) | [Open](https://agentguard-food-demo.vercel.app/quickbite/checkout.html?scenario=extras) | [Open](https://agentguard-food-demo.vercel.app/dinedash/checkout.html?scenario=extras) |
| qty2 | [Open](https://agentguard-food-demo.vercel.app/foodhub/checkout.html?scenario=qty2) | [Open](https://agentguard-food-demo.vercel.app/quickbite/checkout.html?scenario=qty2) | [Open](https://agentguard-food-demo.vercel.app/dinedash/checkout.html?scenario=qty2) |
| hidden | [Open](https://agentguard-food-demo.vercel.app/foodhub/checkout.html?scenario=hidden) | [Open](https://agentguard-food-demo.vercel.app/quickbite/checkout.html?scenario=hidden) | [Open](https://agentguard-food-demo.vercel.app/dinedash/checkout.html?scenario=hidden) |
| nototal | [Open](https://agentguard-food-demo.vercel.app/foodhub/checkout.html?scenario=nototal) | [Open](https://agentguard-food-demo.vercel.app/quickbite/checkout.html?scenario=nototal) | [Open](https://agentguard-food-demo.vercel.app/dinedash/checkout.html?scenario=nototal) |

## Local preview commands

```powershell
cd C:/Users/ayush/AgentGuard/.tools/food-vertical
node scripts/build_food_sites.mjs
C:/Users/ayush/AgentGuard/.venv/Scripts/python.exe -B -m http.server 8135 --bind 127.0.0.1 --directory dist/food-sites
```

Packaging only copies an allowlist of public files. The output is a static Vercel
project as-is, without frameworks, backend code, databases or credentials. It
refuses unrelated output files instead of deleting them. The `ui.server:app`
launcher also serves these paths alongside the protected booking application.

## Exact local page URLs

| Platform | Listing | Dish detail | Checkout |
| --- | --- | --- | --- |
| FoodHub | http://127.0.0.1:8135/foodhub/ | http://127.0.0.1:8135/foodhub/dish.html?dish=fh-spice-route-paneer | http://127.0.0.1:8135/foodhub/checkout.html?dish=fh-spice-route-paneer |
| QuickBite | http://127.0.0.1:8135/quickbite/ | http://127.0.0.1:8135/quickbite/dish.html?dish=qb-spice-route-paneer | http://127.0.0.1:8135/quickbite/checkout.html?dish=qb-spice-route-paneer |
| DineDash | http://127.0.0.1:8135/dinedash/ | http://127.0.0.1:8135/dinedash/dish.html?dish=dd-spice-route-paneer | http://127.0.0.1:8135/dinedash/checkout.html?dish=dd-spice-route-paneer |

Confirmation follows Place order at `/{platform}/confirmation.html` with all state
and a browser-generated `order_id=sim_...` in the query. Without an ID it displays
“No simulated order found.” No real server order or signed receipt is claimed.

## Exact local scenario URLs

Each URL defaults to that platform's featured dish and canonicalizes all state.

| Scenario | FoodHub | QuickBite | DineDash |
| --- | --- | --- | --- |
| clean | http://127.0.0.1:8135/foodhub/checkout.html?scenario=clean | http://127.0.0.1:8135/quickbite/checkout.html?scenario=clean | http://127.0.0.1:8135/dinedash/checkout.html?scenario=clean |
| extras | http://127.0.0.1:8135/foodhub/checkout.html?scenario=extras | http://127.0.0.1:8135/quickbite/checkout.html?scenario=extras | http://127.0.0.1:8135/dinedash/checkout.html?scenario=extras |
| qty2 | http://127.0.0.1:8135/foodhub/checkout.html?scenario=qty2 | http://127.0.0.1:8135/quickbite/checkout.html?scenario=qty2 | http://127.0.0.1:8135/dinedash/checkout.html?scenario=qty2 |
| hidden | http://127.0.0.1:8135/foodhub/checkout.html?scenario=hidden | http://127.0.0.1:8135/quickbite/checkout.html?scenario=hidden | http://127.0.0.1:8135/dinedash/checkout.html?scenario=hidden |
| nototal | http://127.0.0.1:8135/foodhub/checkout.html?scenario=nototal | http://127.0.0.1:8135/quickbite/checkout.html?scenario=nototal | http://127.0.0.1:8135/dinedash/checkout.html?scenario=nototal |

Scenarios persist through listing/detail navigation. FoodHub extras select tip 30
and donation 10; QuickBite extras select Gold 149; DineDash has no defaults.
Explicit URL values override defaults, so removed extras stay removed in a fresh
context. `qty2` defaults to two only if `qty` is absent. Every selection is encoded
as `platform`, `dish`, `qty`, `coupon`, `tip`, `donation`, `gold`, and `scenario`.

`hidden` includes the specified off-screen `data-hidden="true"` instruction.
`nototal` displays “calculated at payment” with `data-total="unknown"`. Every bill
row has `data-item-id`, `data-item-type` and integer `data-price`. Coupon rows are
negative; unchecked extras contribute zero. Rows sum to the known total. Fees and
extras stay flat per order; quantity changes the item subtotal and coupon math.

## Read-only comparison

The five existing starter files were continued, not replaced. `guard/food/` holds
strict comparison models, integer coupon arithmetic and deterministic ranking.
`app/food_compare.py` runs exactly three injected read-only readers in parallel.
Any source failure/invalid data prevents selecting a partial winner. The new
`app/food_catalog.py` supplies synthetic readers from the shared fixture file.

One best eligible coupon is applied, never stacked. Eligibility uses item price
alone, excluding fees. Percent discounts round down to whole rupees and honor
`max_discount`. Tip, donation and membership never enter effective comparison
price. The comparison pass supports one serving.

Taste is `(rating * rating_count + 3.8 * 50) / (rating_count + 50)`: a proxy, not
ground truth. Sorting uses exact rational arithmetic before converting display
scores to floats. Only rating metrics may have decimals; all money is integer
rupees. Ties are stable regardless of thread completion order.

```powershell
C:/Users/ayush/AgentGuard/.venv/Scripts/python.exe -B -m scripts.compare_food --priority price
C:/Users/ayush/AgentGuard/.venv/Scripts/python.exe -B -m scripts.compare_food --priority taste
```

Both fixture priorities choose FoodHub's Spice Route paneer combo (Rs 280), ahead
of QuickBite's Rs 289 option. FoodHub's FIRST50 is ineligible for quantity one:
the Rs 260 item is below its Rs 300 minimum. These are fixture results, not actual restaurant claims.
Pass `--base-url` to use the public deployment instead of the reserved
`food-demo.example` placeholder in comparison result URLs.

Schema v2, task API, checker and commit gate remain unchanged. Food contract/cart
extensions, live comparison adapters, staging/fixing and food commit integration
are deferred. The fixture's DOM row types do not alter the shared cart model.

## Validation

```powershell
node --test ui/*.test.mjs food-demo/logic.test.mjs
C:/Users/ayush/AgentGuard/.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp=.tools/food-tests tests ui/test_demo.py
C:/Users/ayush/AgentGuard/.venv/Scripts/python.exe -B scripts/check_food_sites.py
```

Browser QA checks all three platforms, four page types and five scenarios,
280/320 totals, Gold, coupon eligibility, quantity changes, fresh-context URL
reopening, hidden/missing totals, invalid input and 390/320 px mobile layouts. It
asserts the fixture never POSTs an order/payment. Set `FOOD_BASE_URL` to repeat the
same checks against the public deployment.
