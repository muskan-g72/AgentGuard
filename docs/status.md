# AgentGuard Food Vertical Status Report

> **Branch**: `feature/food-vertical`  
> **Evaluation Mode**: Fixture replay (`REPLAY=1`) unless explicitly noted.  
> **Integrity Notice**: All numbers, latencies, and outcomes documented below are directly measured from test runs or fixture data. Live external execution was not verified due to lack of a live `TINYFISH_API_KEY` and remote endpoints.

---

## 1. Feature Status Table

| Feature Area | Status | Evidence & Verification Details |
| :--- | :--- | :--- |
| **compare** | **Works** | `POST /food/compare` triggers `compare_all()` in `app/food_compare.py`, querying platform URLs concurrently via `ThreadPoolExecutor`. In replay mode (`REPLAY=1`), loads fixture files `recordings/food/{foodhub,quickbite,dinedash}.json` (labelled **fixture**). Correctly extracts 7 dish options across 3 platforms and handles per-platform failures gracefully without dropping surviving options (`test_food_compare_reports_a_platform_failure_and_keeps_other_results`). Live execution via TinyFish Agent API was not verified live. |
| **rank** | **Works** | `guard/food_rank.py:rank` deterministically enforces contract requirements (`diet`, `min_rating`, `max_eta_minutes`, `effective_price <= max_total`) and ranks surviving options by priority (e.g. `priority="price"`). Verified in `tests/test_food_rank.py` and step 3 HTTP API test: FoodHub Spice Route ranked #1 (effective price Rs 280), QuickBite Spice Route ranked #2 (effective price Rs 289 after Rs 40 coupon). Dropped options (5 dishes) list explicit reasons (FoodHub Biryani Hub: "not vegetarian"; FoodHub Roll Point: "rating 3.9 is below 4.2"; QuickBite Biryani Hub: "rating 3.6 is below 4.2"; DineDash Spice Route: "effective price Rs 308 exceeds Rs 300"; DineDash Green Bowl: "rating 4.1 is below 4.2"). |
| **stage** | **Works** | `app/food_compare.py:stage_winner` stages the recommended cart without placing an order. In replay mode (`REPLAY=1`), loads the scenario-keyed cart (`clean`, `extras`, `qty2`, `hidden`, `nototal`) from fixture `recordings/food/foodhub.json` (labelled **fixture**). Extracts structured cart evidence: `cart_id`, item list with types/prices, quantity, total, and hidden text. Verified in `tests/test_food_api.py`, `scripts/eval_food.py`, and step 3 test. Live staging not verified live. |
| **check** | **Works** | Deterministic cart verification in `guard/food_checker.py:check_food_cart`. Operates locally with zero network or LLM dependencies in strict fail-closed order: missing fields -> `ask`; non-vegetarian dish on veg contract -> `block`; quantity mismatch -> `block`; unauthorized extras -> `block` with `remove_item_ids`; total exceeding budget -> `block`; unexpected total discrepancy -> `block`; coupon ineligibility -> `block`; hidden prompt injection -> `ask`. Verified in `tests/test_food_models.py`, `tests/test_food_api.py`, and step 3 test. |
| **fix** | **Works** | `app/food_workflow.py:run_food_task` initiates a single bounded fix pass when `decision.result == "block"` and `remove_item_ids` is non-empty. Calls `browser.fix_cart(option, cart, remove_item_ids)`. In replay mode (`REPLAY=1`), strips identified extras (`["tip", "donation"]`) and recalculates total from Rs 320 down to Rs 280. Emits event `food_fix_started` with `remove_item_ids=['tip', 'donation']`. Verified in step 3 test and `test_food_block_fix_allow_commit_uses_the_allow_gate`. |
| **re-check** | **Works** | Following a fix, `run_food_task` re-checks the fresh cart evidence against the contract. Records `food_recheck` event with fresh cart (total Rs 280) and records a new `food_decision` (`result="allow"`). Verified in step 3 HTTP API test and `tests/test_food_api.py`. |
| **commit** | **Works** | `app/food_workflow.py:commit_food_task` enforces the allow-before-commit gate: requires task status `allowed`, stored decision `allow`, matching cart hash digest, and valid integer total. In replay mode, commits simulated order `food_replay_foodhub_foodhub_spice_extras` at Rs 280 and emits `food_commit_result`. For blocked/asked scenarios (`qty2`, `hidden`, `nototal`), commit never starts (`food_commit_started` is never emitted). Verified in step 3 test and `tests/test_commit_gate.py`. |
| **guard toggle** | **Works** | Controlled via `guard_off: bool` in `FoodRunRequest`. When `guard_off=True`, explicitly logs `food_guard_off_enabled` and `food_guard_off_bypass` events, bypasses check/fix gates, and commits the preticked cart at Rs 320. Verified in step 3 API test and `test_guard_off_orders_the_preticked_food_cart_and_marks_events`. (For train booking tasks, disabling guard remains strictly rejected with HTTP 422: `WorkflowError: The confirmation guard cannot be disabled.`). |
| **replay toggle** | **Works** | Configured via `REPLAY=1` environment variable. When enabled, all staging, comparison, and commit actions resolve against checked-in fixtures in `recordings/food/` and `recordings/s*.json` with zero external network egress. When disabled, invokes TinyFish Agent API (requires `TINYFISH_API_KEY`). Evaluator `scripts/eval_food.py` defaults to replay and supports `--live`. Verified in `tests/test_staging_replay.py` and step 3 test. |
| **events timeline** | **Works** | Persistent, append-only SQLite store (`app/store.py`) with SHA-256 hash chaining (`prev_hash`, `hash`) and SSE streaming (`GET /tasks/{task_id}/events`). Cryptographic receipt verification (`GET /tasks/{task_id}/receipt/verify`) detects event tampering. Step 3 verified the exact 10-event sequence for extras: `food_compare_done` -> `food_ranked` -> `food_stage_started` -> `food_staged` -> `food_decision` -> `food_fix_started` -> `food_recheck` -> `food_decision` -> `food_commit_started` -> `food_commit_result`. |
| **UI** | **Partly** | The web UI at `index.html`, `checkout.html`, and `confirmation.html` functions for the train booking vertical (covered by Playwright E2E tests in `tests/test_browser_flow.py`). However, there is no dedicated food vertical web UI on `feature/food-vertical`. Food comparison, staging, and run flows are operated exclusively via the FastAPI HTTP endpoints and evaluation scripts. (Food demo UI pages were created on remote branches `origin/integration/merge-all` and `origin/frontend-changes`, but per rules are not merged). |

---

## 2. Limitations and Unfixed Items

Per the task rules, only small bugs necessary for the required flows were fixed. The following larger architectural gaps are cataloged below and left untouched:

1. **Food Vertical Web UI**:
   - `feature/food-vertical` lacks front-end templates or interactive UI components for food comparison, scenario selection, and order staging.
   - Evidence: Root `index.html` and `checkout.html` only bind train ticketing elements (`ticket-select`, train dates).

2. **Absence of User Review Checkpoint for Food Tasks**:
   - Train booking tasks follow an explicit lifecycle: `sentence` -> `questions` -> `answers` -> `confirm` (reviewed contract) -> `stage` -> `check` -> `commit`.
   - Food tasks currently proceed directly from `POST /food/compare` to `POST /food/run` without an intermediate user confirmation or clarification step.

3. **Single-Pass Bound on Food Cart Fixes**:
   - `run_food_task` executes at most one fix pass. If a cart has multiple independent or non-item issues, or if removing an extra triggers a new constraint violation, the task halts at `blocked` without multi-turn recovery.

4. **Live Verification Unavailable**:
   - Live TinyFish execution against real food ordering platforms was not verified live due to the absence of active `TINYFISH_API_KEY` credentials in the test environment and live platform mock deployments. All evaluations rely on clearly labelled fixture recordings.

5. **Separate Data Models**:
   - `guard/food_models.py` (`FoodContract`, `FoodOption`, `StagedFoodCart`) operates independently of `guard/models.py` (`Contract`, `Cart`, `OrderRequest`). A unified schema v3 across verticals remains planned.
