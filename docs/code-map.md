# AgentGuard code map

## Shared models and checking

- `guard/models.py` defines Schema v2 train `Contract`, `Cart`, `Decision`, and order-request models. Money is integer rupees.
- `guard/checker.py` compares a staged train cart with its contract. It has no network or LLM access.
- `guard/contract_parser.py` parses a user sentence into a train contract and falls back to the fixed demo contract when needed.
- `guard/food_models.py` defines the separate food comparison and staged-cart models. It does not change the train schema.

## Task and browser workflow

- `app/main.py` defines the FastAPI task, staging, event, receipt, and health endpoints.
- `app/store.py` persists tasks, status events, cart evidence, decisions, and receipts in SQLite.
- `app/workflow.py` runs the protected train flow: stage evidence, check it, remove authorized extras if blocked, re-check, and only then submit a simulated order.
- `app/staging.py` builds TinyFish staging goals, parses evidence, verifies item IDs, and handles train replay recordings.
- `app/tinyfish_client.py` owns TinyFish HTTP calls and the restricted simulated-demo origin policy.
- `app/browser.py` extracts rendered checkout evidence and removes only identified, removable extras.

## Food comparison

- `app/food_compare.py` compares food listings, calculates effective prices and taste proxies, ranks options, and stages a winner without placing an order.
- `recordings/food/*.json` are clearly labelled fixture data for replay. `recordings/food/live/` is reserved for raw live TinyFish results.

## Tests

- `tests/test_scenarios.py` covers the six train-cart checker scenarios.
- `tests/test_tasks.py`, `tests/test_run_loop.py`, and `tests/test_commit_gate.py` cover task state, run-loop, and commit-gate behavior.
- `tests/test_food_compare.py` covers fixture comparison, ranking, effective prices, staged food extras, and restricted food paths.

## Train task flow

1. A user instruction is parsed into a contract and stored as a task.
2. The user confirms the contract.
3. The browser stages a cart without submitting it.
4. The deterministic checker returns allow, block, or ask.
5. A block with removable extras can run a bounded fix and then re-check.
6. Commit requires an allow decision and matching approved cart evidence. Orders remain simulated.
