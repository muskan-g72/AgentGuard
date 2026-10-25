# AgentGuard

AgentGuard is a simulated booking and food-order guard. It stages an action, checks the staged data against a user contract, and only starts a simulated commit after an allow decision. It does not collect payment or personal data.

## What exists

- Train booking pages use URL state for six train scenarios.
- The train checker in `guard/checker.py` is deterministic and has no network or LLM access.
- The FastAPI task store records task events, cart evidence, decisions, approvals, and simulated orders in SQLite.
- Food comparison uses three simulated paths on `demo-booking-tau.vercel.app`: FoodHub, QuickBite, and DineDash.
- Food fixture replay compares seven listed options, ranks them, stages FoodHub Spice Route, checks extras, optionally removes listed extras, re-checks, and commits a simulated order.

## Food flow

1. `POST /food/compare` accepts a food contract and platform URLs.
2. It compares platform options, calculates effective price, records dropped reasons, and stores a recommended option in a task.
3. `POST /food/run` stages that option without ordering.
4. `guard/food_checker.py` checks the staged food cart.
5. A block with listed removable extras runs one food fix and then re-checks.
6. A normal commit starts only after an allow decision, matching stored cart hash, and allowed task status. The `guard_off` request flag is an explicit demo bypass and is recorded in events.

Food contract fields are `diet`, `quantity`, `max_total`, `min_rating`, `max_eta_minutes`, `allow_extras`, and `priority`. Money is integer rupees. Effective price is item price plus delivery, platform, and packaging fees, minus the best eligible coupon. Taste score is a rating/count proxy; it is not ground truth.

Orders are simulated. The live food paths and live TinyFish runs are **Planned** for verification; checked-in food fixtures are clearly labelled fixtures, not live recordings.

## Installation, Test, and Run Commands

### 1. Installation

Create and activate a virtual environment, then install dependencies from `requirements.txt`:

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Linux / macOS (Bash):**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

*(Optional: If running browser UI integration tests from scratch in a fresh environment, ensure Playwright browsers are installed: `python -m playwright install chromium`)*

### 2. Testing

Run the full automated test suite:

```bash
python -m pytest -q
```

To run only the food vertical tests:

```bash
python -m pytest tests/test_food_api.py tests/test_food_compare.py tests/test_food_rank.py tests/test_eval_food.py -q
```

### 3. Running the API Server

Start the local FastAPI development server:

**Windows (PowerShell):**
```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Linux / macOS (Bash):**
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The API will be available at `http://127.0.0.1:8000`, with interactive OpenAPI documentation at `http://127.0.0.1:8000/docs`.

### 4. Running the Food Evaluator

Run the benchmark evaluation in fixture replay mode:

**Windows (PowerShell):**
```powershell
$env:REPLAY="1"
python scripts\eval_food.py
```

**Linux / macOS (Bash):**
```bash
export REPLAY="1"
python scripts/eval_food.py
```

Results are recorded to `docs/eval-results.md`. (Use `--live` only when running against live endpoints with `TINYFISH_API_KEY` set).

## Known limits

- Food replay is fixture-backed. It does not prove browser behavior on a deployed food platform.
- The food workflow has no user-confirmation endpoint between compare and run. **Planned:** explicit food-contract confirmation.
- The food fix supports one pass only and removes only IDs returned by the food checker.
- `guard_off` intentionally bypasses food checking and the normal commit gate for the before/after demo. It is not a safe production mode.
- The train and food cart models are separate. `StagedFoodCart` does not replace the shared train `Cart` schema.
