# AgentGuard demo UI

This folder contains a buildless, mobile-friendly four-step demo. It uses mock
Schema v2 JSON by default and can connect to the task API through a same-origin
server proxy. No files in `app/` or `guard/` are changed by this work.

## Start

From the repository root, with the existing Python environment installed:

```powershell
.venv/Scripts/python.exe -B -m uvicorn ui.server:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. Press **Run demo** to walk through s2, including
questions, contract confirmation, the initial block, removal, re-check, outgoing
request check, and a proof receipt. **Reset** starts a fresh view.

The page clearly labels mock replay. Its receipt verification checks the local
fixture event chain; its signature is a placeholder, not a backend HMAC. The
frontend contains no receipt key or service credentials. The Guard OFF comparison
is explicitly labelled as an illustration; it never sends a second unchecked
order. Turning repairs off preserves the shared schema's mandatory commit gate.

## Booking sandbox

`http://127.0.0.1:8000/index.html` opens the existing protected booking site.
Its search form remains editable, validates station and passenger inputs, filters
the route/date, and displays per-passenger and group prices. Changing a native
scenario preserves the current search fields in the URL.

| Scenario | Behavior |
| --- | --- |
| s1–s6 | Existing clean, extras, fee, wrong-date, hidden-text, and missing-data scenarios |
| s7 / ui_lies | Dashboard mock only: a clean Rs 1,000 cart produces a changed Rs 1,500 request that is blocked |
| s8 | Dashboard mock only: choose “Yes” for refundable to demonstrate a non-refundable ticket being blocked |

Selecting s7 or s8 in the booking scenario dropdown opens the corresponding mock
scenario in the control room. These cases do not extend the native backend's
inventory or bypass its confirmation guard. The mock uses the same 2026-10-25
baseline date as `origin/main`; its wrong-date scenario uses 2026-10-26.

The UI launcher mounts the unchanged native application for booking routes.
Server-owned carts, explicit contract review, approvals, outgoing-request checks,
and response-backed confirmation remain in `app/` and `guard/`. There is no
unchecked `/api/order` merchant endpoint. No real payment is taken.

## Connect Muskan's API

Start the backend on port 8001, then choose **Data source → Connected task API**
in the UI, or open `/ui/?api=1`. The local proxy defaults to
`http://127.0.0.1:8001`; override it before starting the UI server:

```powershell
$env:AGENTGUARD_API_URL = 'http://127.0.0.1:8001'
```

The browser talks only to `/api/task-proxy?path=...`. The server forwards the
schema's endpoints, including SSE and `Last-Event-ID`. `EventSource` drives live
status changes; polling fills in carts/decisions and recovers from stream errors.
An API failure stays visible; the UI never silently turns it into a successful
mock run. Ambiguous run failures are recovered with GET, never by replaying POST.
`AGENTGUARD_API_TOKEN`, if needed, belongs only in the server environment.

Receipts show the verification result returned by `/receipt/verify`. False,
missing, malformed, or failed verification never displays a verified badge.

The current backend accepts only s1–s6 and has its own reviewed-task/run workflow.
The dashboard API adapter still needs integration against those response shapes
and run options; use the default mock mode for the complete dashboard demo.
Unsupported requests remain visible errors. S7 and s8 are dashboard mocks only.
The schema file and native backend are unchanged.

## Build and deployment boundary

`node ui/build.mjs` copies public booking/UI assets to ignored `dist/` for static
preview. Protected checkout still requires the native backend; copying HTML alone
does not provide its API or approvals. The frontend does not include receipt keys,
service credentials, databases, or backend source.

Keep `origin/main`'s deployment/proxy setup. This change does not replace it with
a standalone merchant or static-only production configuration. The combined local
entry point is `ui.server:app`; deploying the dashboard needs that entry point or
an equivalent explicit UI asset mount. Mock replay needs no external credentials.

## Checks

```powershell
node --test ui/*.test.mjs
.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp=.tools/ui-pytest tests ui/test_demo.py
```

Browser QA uses Playwright against the running UI server. `ui/e2e.py` exercises
the guided flow, manual questions, mock request/requirements checks, reset, mobile
overflow, API error states, search validation/filtering, per-passenger prices, and
screenshots. The existing `tests/` suite checks the real protected booking flow.

For browser QA only, install `playwright` into your local environment and run
`python -m playwright install chromium` before `python -B ui/e2e.py`.
