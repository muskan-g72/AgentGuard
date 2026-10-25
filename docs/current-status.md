# AgentGuard current status

## Unified-product implementation update

On branch `complete-agentguard-product`, the local runtime now serves the main
dashboard at `/`, `/ui/` as an alias, train fixtures under `/train/`, and food
entry/fixture routes from `app.main:app`. Food comparison creates an unconfirmed
task; `/food/{task_id}/confirm` is required before `/food/run`. Food simulated
orders persist in `food_orders` and are available through the order and receipt
APIs. Replay is credential-free; live food requires the deployment kill switch
and operator header. No deployment or paid API call has been performed.

Remaining known blocker: public anonymous session ownership/authentication is not
yet implemented, so the backend must not be exposed publicly until that boundary
is added.

> Public-demo readiness has now been prepared locally; see
> [public-demo-readiness.md](public-demo-readiness.md) for the observed public
> asset version, Fly/SQLite + Vercel proxy configuration, deployment commands,
> blockers, and separate opt-in smoke commands. The readiness changes passed
> 163 relevant tests, including two real proxy/browser/restart tests. No cloud
> deployment or live API smoke was executed. The 287-test workflow result below
> remains the prior full-suite result, not a new full-suite claim.

> 25 October readiness update: the Linux/amd64 image was built under Docker
> Engine in the existing Ubuntu WSL2 distro. A protected simulated order, cart,
> approval and stable SQLite storage identity survived container restarts; the
> order also survived a second restart. The live process used one Uvicorn worker,
> and `/data/workflow.db` was confirmed as the literal mounted database path.
> Temporary containers/keepalives were removed; the image and test database were
> retained. Vercel login now works for account `pragunaggarwal36-2286` and team
> `pragunaggarwal36-2286s-projects`, but that scope does not own or expose
> `demo-booking-tau.vercel.app`; the owning project/team/deployment remain a
> blocker. Proposed Fly resources are unprovisioned `agentguard-pragun-demo` in
> Singapore (`sin`), one shared CPU/512MB Machine, one worker and one 1GB volume.

Verified locally on 24 October 2026. Nothing was committed, pushed, merged,
deployed, or sent to teammates. All orders are simulated; no payments or personal
details are involved. Existing uncommitted work was preserved.

## Audit before editing

- `guard/models.py`, `checker.py`, `contract_parser.py`, `intent_gap.py`,
  `request_check.py`, `page_scan.py`, `hidden_text.py` already contained the v2
  integer-money models, positive/negative requirements, deterministic questions
  and answer mapping, request validation and HTML/hidden-text scanners.
- Existing contract fields: `route` (`from`, `to`), `date`, `quantity`,
  `max_total`, `allow_extras`, `requirements`, `source`. Cart fields: `cart_id`,
  `items`, `total`, `passengers`, `attributes`, `hidden_text`. Item fields: `id`,
  `type`, `price`, optional `route`/`date`. Decisions include `differing_fields`.
  Requirements true mean required, false prohibited, null no constraint.
  Constrained unknown attributes return ASK. Item types remain ticket,
  insurance, meal, fee. Item routes support the existing station-pair string
  and structured route. Money remains JSON integers.
- `app/staging.py` built TinyFish goals, verified IDs against agent-supplied
  checkout HTML, retried extraction once, and supported replay/live recordings.
  It had no independent browser extraction or fix loop. `app/tinyfish_client.py`
  used blocking `/run` with a 360-second timeout and no progress. The CLI used
  the fixed demo contract. Only `recordings/s2.json` was available for replay.
- `app/main.py` exposed `/stage` with a fixed contract and a missing-guard
  ALLOW stub. `app/log.py` stored events, not orders. `checkout.html` always
  navigated on Confirm; `confirmation.html` fabricated an order from URL values.
  No authoritative carts, approvals, orders, or browser fix/commit sessions
  existed. The TinyFish browser was external.
- No Playwright code/dependency existed. No applicable `AGENTS.md` or
  `docs/schema.md` was found. The chat-supplied schema and existing v2 models
  were retained; no shared message fields changed.
- A fresh baseline run passed **220 tests**; the earlier report was not used as
  current evidence.

## Changes and file references

- `app/catalog.py`: authoritative simulated inventory and validated booking
  state. The server computes prices. Scenarios choose rendered content, never
  checker decisions. s6 total/passenger evidence stays null.
- `app/store.py`: SQLite reviewed tasks, required clarification answers,
  versioned carts, random server-issued approval tokens, contract/cart hashes,
  and immutable simulated order snapshots. Requested-state changes increment
  cart version even at the same fare. `BEGIN IMMEDIATE` encloses approval
  validation, fresh checking, actual-request comparison and order creation.
  Duplicate confirmation is idempotent; a task cannot create a second order.
  Database triggers reject order updates/deletes.
- `app/main.py`: same-origin website/API, explicit task review, clarification,
  cart checks, order confirmation and record lookup. Missing checkers, errors,
  invalid extraction and unresolved ASK cannot approve or order. Removed the
  fail-open stub and broad CORS. Only explicit public assets are served;
  `.env`, `.git`, source and databases are not public. Hosts are loopback-only.
- `checkout.html`, new `checkout.js`, `confirmation.html`, `styles.css`: render
  server carts with stable DOM evidence attributes; require answers and explicit
  instruction authorization; check/fix and submit the real outgoing request.
  Confirm starts disabled and needs a server approval. Confirmation pages fetch
  a valid server `order_id`; booking URL values cannot fabricate an order.
- `app/browser.py`: independent Python Playwright extraction of actual rows,
  checkbox selection, totals, passengers and computed hidden text. It does not
  call the frontend extractor or substitute catalogue/fixture values. Removal
  uses actual returned `data-item-id` values and actual checkbox controls.
- `app/workflow.py`: stage -> independent extract/reconcile -> check -> one
  removal pass -> fresh extract/recheck -> optional explicit confirmation via
  the actual button. Non-removable fees stop BLOCK; ASK stays paused. Local
  staging/fixing/confirming share a Playwright context. TinyFish is always a
  separate browser. History and screenshots are retained.
- `app/tinyfish_client.py`: documented `/run-sse`, progress/heartbeat reporting,
  structured output, 120-second server duration limit, 20-second socket timeout,
  stream deadline and best-effort cancellation on failure. No beta strict mode,
  `max_steps`, capture, profile or premium capabilities are requested. Raw HTTP
  error bodies, headers and keys are not printed. Hosted protection preflight
  runs before a paid call.
- `app/staging.py`: v2 goals, integer/null/checkbox instructions, exact staged
  URL, merged hidden-text evidence, timestamped unique live recordings and a
  single-run smoke option. The checked-in s2 recording is unchanged. Replay is
  clearly labelled separately from live execution.
- `guard/request_check.py`: added exact localhost/127.0.0.1 host entries for
  local simulated requests. Existing demo-host checks remain. The host near-miss
  test uses `localhost.evil.example`.
- `pyproject.toml`: optional `browser` dependencies, browser pytest marker, and
  packaging of `app`. `.env.example` documents URLs/database; `.gitignore`
  excludes runtime screenshots/live recordings. `scripts/browser_demo.py`,
  `stage_once.py`, `inspect_records.py` provide reproducible commands.
- Added `tests/test_application.py`, `test_browser_flow.py`, and
  `test_tinyfish_client.py`. Earlier guard/replay tests remain intact.

## Verified behavior

Latest full suite: **287 passed**, including **20 real Chromium browser tests**.
One upstream Starlette TestClient/httpx deprecation warning remains. The normal
suite makes no paid API calls.

| Actual rendered/cart content | Result |
| --- | --- |
| s1: T1, Rs 1,000, one passenger, no extras | ALLOW |
| s2: T1, checked insurance/meal, Rs 1,350 | BLOCK, actual IDs `x1`, `m1` |
| s2 after real removal and fresh extraction | ALLOW, Rs 1,000 |
| s3 fee with no removal control | BLOCK, no order |
| s4 actual wrong-date T3 | BLOCK |
| s4 label but explicitly selected correct-date T1 | ALLOW; contents determine decisions |
| s5 existing off-screen instruction note | ASK with flags |
| s6 absent total/passenger evidence | ASK, nulls preserved |

Verified with actual Chromium and local SQLite/API:

- Checkbox changes update DOM, total, URL and server cart version. Reopening
  the exact URL in a fresh context restores the state/selections. A new UI
  context acquires its own approval before enabling Confirm.
- The actual UI requires all answers and explicit instruction authorization.
  Unreviewed fallbacks and unanswered questions cannot approve.
- Missing/import-error/failing/invalid-result checkers, invalid extraction,
  altered DOM and omitted hidden text create neither approval nor order.
- Unchanged approval creates one persistent immutable order. Same-price
  requested-date changes invalidate the version; actual ticket-date changes
  are caught by the content hash. Outgoing item/price/fields/task/token
  tampering is rejected. Concurrent duplicate confirmations return one order.
  Failed tasks cannot commit an older approval. DB order updates are rejected.
- Direct confirmation navigation using arbitrary cart values or an unknown
  order ID stays unconfirmed. Order snapshots survive DB reopening.
- Desktop and 390px mobile overflow checks passed and generated screenshots.
  A headed s2 demonstration completed BLOCK -> remove -> ALLOW -> confirm.
  Its checkout/order screenshots were visually inspected. Verified demo task:
  `6f5439b3-57a7-443c-9e3e-ca79e8677650`; order:
  `order_bfcdb828d5274d8cae87f2db74c279b4`. Artifacts are in ignored
  `test-results/` and `data/workflow.db`.
- Replay CLI returned saved s2 BLOCK. The replay/browser workflow reconciled
  saved content against independently rendered local/server content before
  fixing/rechecking. A mismatching URL failed instead of replacing evidence.

## Mocked/replayed and live status

TinyFish SSE lifecycle, progress, protocol fields, safe HTTP failures, incomplete
streams, URL restrictions and single-run retry limits are verified with mocked
HTTP/agent responses. They are not live-run evidence. Replay reads only saved
JSON, not an external agent session.

Official documentation inspected:
[overview](https://docs.tinyfish.ai/agent-api),
[API reference](https://docs.tinyfish.ai/agent-api/reference), and
[structured output](https://docs.tinyfish.ai/key-concepts/structured-output).
Documented account-gated capture and beta options are not used.

After local checks passed, exactly one live smoke command was attempted. An
existing key was detected without printing it. The public checkout was reachable
but still lacked protected server-backed confirmation. Preflight stopped with:

> Live smoke blocked: hosted checkout has no protected server-backed Confirm
> button. No paid agent call was made.

**No live TinyFish agent run occurred.** No repeated attempts were made. Live
LLM parsing was not exercised. No keys were printed or written to git.

## Remaining blockers and planned work

- Protect and host the backend/frontend before attempting live automation.
  The public Vercel frontend was not deployed/changed and cannot reach this
  loopback backend. Deployment is outside this local change.
- Live results must supply the exact staged URL. A separate Playwright browser
  must match the agent cart; a local mirror must then match that full content
  against server records. The local mirror has its own explicitly recorded
  server cart ID. Disagreement, unavailable machine attributes or transient
  cookie-only state stops the run rather than guessing. This live path remains
  implemented but unverified because preflight blocked the hosted site.
- The catalogue has no independently established refund/seat/baggage facts.
  Attributes remain unknown; requiring any pauses ASK. Hidden-instruction ASK
  has no automatic override; it stays paused for trusted review/removal and a
  fresh check. LLMs cannot approve.
- `scan_html` is heuristic and does not evaluate external CSS/scripts or layout;
  Playwright reads computed styles independently.
- `/tasks/{id}/events` returns persisted, hash-chained events as a finite SSE
  response by default; `follow=true` enables a bounded live stream. TinyFish
  progress is streamed to the terminal. No production authentication was added.
- `/tasks/{id}/receipt` and `/tasks/{id}/receipt/verify` expose an HMAC-signed
  proof receipt when `RECEIPT_KEY` is configured. Local DB snapshots and hashes
  bind approval to content, but do not protect against the database owner
  rewriting storage.
- Client timeout cancellation is best effort; remote duration is also bounded
  by the provider's server limit. The TestClient deprecation warning is upstream.

## Exact Windows PowerShell commands

Run in the repository root. Preserve your existing `.env`; do not overwrite keys.
Create the virtual environment only if needed, then install dependencies/browser:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,browser]"
.\.venv\Scripts\python.exe -m playwright install chromium
```

Start backend and website together in one terminal (no separate static server):

```powershell
$env:AGENTGUARD_DB = "data/workflow.db"
$env:DEMO_LOCAL_URL = "http://127.0.0.1:8001"
$env:RECEIPT_KEY = "<generate-a-local-high-entropy-value>"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001/index.html?scenario=s2`, select a train, prepare
instructions, answer the questions and explicitly authorize the contract. Use
Check or Check and remove unauthorized extras, then Confirm only after ALLOW.
`python -m http.server` cannot run the protected checkout API.

Run unit/integration tests, real browser tests, or the complete suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider -m "not browser"
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider -m browser
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Run a visible s2 stage/check/fix/recheck/confirm demo. `--review-demo` explicitly
reviews the printed fixed contract and answers all preferences "don't care".
Omit `--confirm` to stop at the checked cart:

```powershell
.\.venv\Scripts\python.exe scripts/browser_demo.py --scenario s2 --review-demo --headed --confirm
```

The demo CLI and backend must use the same database. For a custom DB, set the
backend's `AGENTGUARD_DB` and pass the same path using CLI `--db`.

Replay staging, without network/browser/key:

```powershell
.\.venv\Scripts\python.exe scripts/stage_once.py --mode replay --scenario s2
```

Replay plus real local browser reconciliation and fixing (backend running):

```powershell
.\.venv\Scripts\python.exe scripts/browser_demo.py --mode replay --scenario s2 --review-demo --headed
```

Once the hosted confirmation/backend blocker is resolved, run one live staging
attempt. This command refuses an unprotected hosted demo and never confirms or
issues an approval:

```powershell
.\.venv\Scripts\python.exe scripts/stage_once.py --mode live --scenario s2 --review-demo
```

For different reviewed instructions, use `--contract .\reviewed-contract.json`
instead of `--review-demo`. `DEMO_URL` is the allowed public demo root. Live
execution rejects localhost/unrelated hosts/non-booking paths. Unique timestamped
responses go to ignored `recordings/live/`, never `recordings/s2.json`.

Inspect health, decisions/events and order records. Substitute IDs printed by
your own run, or use the verified sample IDs while using the existing local DB:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
.\.venv\Scripts\python.exe scripts/inspect_records.py --task-id 6f5439b3-57a7-443c-9e3e-ca79e8677650
.\.venv\Scripts\python.exe scripts/inspect_records.py --order-id order_bfcdb828d5274d8cae87f2db74c279b4
Invoke-RestMethod http://127.0.0.1:8001/tasks/6f5439b3-57a7-443c-9e3e-ca79e8677650/events
```

API: `POST /tasks`, `POST /tasks/{id}/answers`, `POST /tasks/{id}/confirm`,
`POST /tasks/{id}/run` (`mode`, optional `cart_url`, `confirm`), `GET /tasks/{id}`,
`GET /tasks/{id}/events`, `GET /tasks/{id}/receipt`,
`GET /tasks/{id}/receipt/verify`; `POST /api/carts`, `GET/PUT /api/carts/{id}`,
`POST /api/carts/{id}/check`, `POST /api/carts/{id}/confirm`,
`GET /api/orders/{id}`, `GET /health`. `POST /stage` requires a reviewed
`task_id` and never issues approval on agent-supplied evidence alone.
