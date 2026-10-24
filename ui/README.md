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

`http://127.0.0.1:8000/index.html` opens the booking fixture. Use its scenario
dropdown or `checkout.html?scenario=s7` for direct checkout.

| Scenario | Behavior |
| --- | --- |
| s1–s6 | Existing clean, extras, fee, wrong-date, hidden-text, and missing-data scenarios |
| s7 / ui_lies | Screen shows a Rs 1,000 ticket only; Place Order constructs a real POST to `/api/order` with Rs 250 insurance and a Rs 250 fee, total Rs 1,500 |
| s8 | Non-refundable ticket; choose “Yes” for refundable to demonstrate a requirement block |

Every cart exposes `window.agentGuardCart`, a Schema v2 snapshot with integer
rupees and attributes. The requirements row has `data-attribute` and `data-value`
for reliable extraction. Cart rows describe only selected items. The s7 additions
exist only in the outgoing request built by the click handler.

The simulated merchant returns the received items and total. Confirmation uses
that response, not the clean cart query string. The merchant intentionally accepts
s7's request when no interceptor is present: it is the adversarial booking fixture,
not a guard. No real payment is taken. A plain Python static server cannot handle
`POST /api/order`; use the server above or Vercel.

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

The current backend accepts only s1–s6. S7 and s8 work in the mock UI and booking
fixture; API mode reports unsupported scenarios clearly until the team adds them.
The schema file is unchanged.

## Vercel

`node ui/build.mjs` copies only public demo/UI files to `dist/`. The repository's
`vercel.json` selects that directory. `api/order.js` is the simulated merchant;
`api/task-proxy.js` is the optional server-only connection to the task API. The
`.vercelignore` excludes backend source, local environments, databases, and secrets.

After authenticating and linking the existing project:

```powershell
npx vercel login
npx vercel link
npx vercel --prod
```

Do not paste credentials into the UI. For a hosted backend, set
`AGENTGUARD_API_URL` in Vercel's server environment to its public HTTPS address.
Mock replay works without this variable. The judge-facing flow is at `/ui/`;
the original booking sandbox remains at `/index.html`.

## Checks

```powershell
node --test ui/demo.test.mjs ui/api.test.mjs
.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp=.tools/ui-pytest tests ui/test_demo.py
```

Browser QA uses Playwright against the running UI server. `ui/e2e.py` exercises
the guided flow, manual questions, s7's actual fetch, requirements, reset, mobile
overflow, API error states, and screenshots. Optional API integration requires the
existing task server running on 8001 with a local receipt key.

For browser QA only, install `playwright` into your local environment and run
`python -m playwright install chromium` before `python -B ui/e2e.py`.
