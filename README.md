# AgentGuard

A bodyguard for AI shopping agents: ask about missing preferences, block extras,
repair and re-check the cart, verify the outgoing order payload, and produce a
signed proof receipt. All payments and orders in this project are simulated.

[AgentGuard Schema v2](docs/schema.md) is the source of truth for all branches.
Tell the team before changing it. Money is always whole rupees as JSON integers.

## Run the demo UI

```powershell
.venv/Scripts/python.exe -B -m uvicorn ui.server:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/` and press **Run demo**. The four-step interface walks
through s2 with a labelled mock replay by default. It includes questions, contract
review, a live timeline, removed items, a proof receipt, and a Guard OFF/ON comparison.
Choose **Data source** to connect the task API. See [ui/README.md](ui/README.md)
for API integration, deployment, and the s7 click-time request and s8 non-refundable
fixtures. No `app/` or `guard/` source edits are needed for the UI.

## Run the API (PowerShell)

```powershell
py -3.14 -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
$env:RECEIPT_KEY = 'choose-a-private-local-demo-signing-key'
$env:AGENTGUARD_REPLAY = '1'
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Use Python 3.11 or newer. This checkout was tested with Python 3.14. Interactive
API documentation is at `http://127.0.0.1:8001/docs`.

Replay is the default and needs no TinyFish or LLM credentials. Set a local
`RECEIPT_KEY` before running tasks; without it, runs fail before staging and the
receipt endpoint returns 503. The default SQLite file is `agentguard.sqlite3`;
override it with `AGENTGUARD_DB`. Environment variable names are listed in
[.env.example](.env.example); values must be set in the shell. Secrets, databases,
and local environments are ignored by Git.

## Try the complete s2 replay

Run this Python example with the API running:

```python
import httpx

with httpx.Client(base_url="http://127.0.0.1:8001") as api:
    draft = api.post("/tasks", json={
        "sentence": "One Ludhiana to Delhi ticket on 2026-10-26, max Rs 1000, no extras",
        "scenario": "s2", "guard_enabled": True,
    }).raise_for_status().json()
    task_id = draft["task_id"]
    print("Review this draft:", draft["draft_contract"])
    if draft["questions"]:
        api.post(f"/tasks/{task_id}/answers", json={
            "answers": {q["key"]: "don't care" for q in draft["questions"]},
        }).raise_for_status()
    api.post(f"/tasks/{task_id}/confirm").raise_for_status()
    task = api.post(f"/tasks/{task_id}/run").raise_for_status().json()
    print(task["status"], task["final"])
    print(api.get(f"/tasks/{task_id}/receipt/verify").json())
```

The s2 run blocks Rs 250 insurance and a Rs 100 meal, removes them, checks the
repaired Rs 1000 cart and outgoing payload, commits once, and signs the receipt.
The fallback parser labels its fixed draft `source: "fallback"`; confirm the
displayed draft before running. `POST /tasks/{id}/confirm` accepts an optional
`{"contract": ...}` to edit the draft during confirmation.

The API implements all endpoints in [the schema](docs/schema.md), including
SSE status events with `Last-Event-ID`, decision history, receipt retrieval and
verification, health, and `POST /stage`. The `/stage` route accepts
`{sentence?, scenario?, contract?}` and returns `{contract, cart, decision}`;
it never commits. No pre-existing `/stage` implementation was present in this
checkout, so compatibility with another branch's request shape is unverified.

## Guard behavior

The checker and request checker are deterministic and perform no network or LLM
calls. Unknown totals, passenger counts, ticket routes/dates, or required
attributes produce `ask`. Known violations produce `block`, even if other facts
are unknown. A requirement set to false is enforced; null means don't care.
Only `allow` can lead to commit. Hidden instructions are flagged as `hidden_text`.
Unexpected extra outgoing form fields are blocked because the demo contract
authorizes no such fields.

Commit atomically checks the allowed status, latest allow decision, and unchanged
cart hash before calling the transport. It also re-checks the payload and binds
the confirmed contract. Rejected gates return 409 and write an audit event.
Concurrent or repeated commits cannot reuse authorization.

`guard_enabled: false` disables automatic repair. The mandatory checks and commit
gate still apply; this flag cannot authorize an unchecked order.

## Receipts

Each SQLite audit event hashes the previous hash plus canonical JSON of its
`id`, `ts`, `type`, and `payload`. Canonical JSON uses sorted keys, compact
separators, UTF-8, and no NaN/Infinity. `prev_hash` and `hash` are excluded from
the event body; the first previous hash is 64 zeros. Cart hashes use canonical
JSON of the complete validated cart, including nullable/default fields.

The stored signature is HMAC-SHA256 of the latest event hash using `RECEIPT_KEY`.
Verification checks the chain, signature, task identity, confirmed contract, and
final order. The signature is **demo-grade, not production security**. Keep the
same key across restarts to verify existing receipts. This demo does not provide
external timestamping, production authentication, or payment processing.

## TinyFish live staging

Set `AGENTGUARD_REPLAY=0` and `TINYFISH_API_KEY` to enable the TinyFish staging and
repair adapter. Live runs use only `https://demo-booking-tau.vercel.app`; localhost
and other origins are rejected. The client follows the
[official TinyFish streaming example](https://github.com/tinyfish-io/tinyfish-cookbook#rest-api).
An optional `OPENAI_API_KEY` enables contract drafting using the
[OpenAI Responses API with Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
The LLM only drafts the contract. Failed drafts fall back to a labelled demo draft.

The current public static site has no trusted outgoing-request capture.
Consequently, otherwise valid live carts stop with `page_unverified` before
commit. Agent-reported screen values are insufficient evidence of an outgoing
request. Live commit remains unavailable until a trusted interception adapter is
implemented. Replay verifies and submits the exact simulated merchant payload.

## Static booking site and scenarios

Serve the original demo separately:

```powershell
.venv/Scripts/python.exe -B -m uvicorn ui.server:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/index.html?scenario=s2`. The standalone pages use
query-string cart state and POST the actual order to a simulated merchant;
confirmation displays its response. They do not enforce the task API's commit
gate. Local tickets use 2026-10-26; s4 recommends the
wrong-date 2026-10-27 ticket. The public deployment has not been updated here.

| Scenario | Replay behavior |
| --- | --- |
| s1 | Rs 1000 valid ticket; verified simulated commit |
| s2 | Rs 1350 with extras; block, repair, re-check, commit Rs 1000 |
| s3 | Rs 1180 including mandatory fee; blocked |
| s4 | Wrong date; blocked |
| s5 | Hidden agent instructions; ask decision, blocked task |
| s6 | Missing total and passengers; ask decision, blocked task |

## Test

```powershell
.venv/Scripts/python.exe -B -m pytest -q
.venv/Scripts/python.exe -B -m guard.demo
```

Tests cover strict integer money, null/false requirements, cart and request
tampering, scenario replay, questions/confirmation, every rejected state
transition, concurrent commit attempts, transport failures, signed receipts,
SQLite persistence, and SSE replay. Tests use no live credentials or paid calls.

The UI has been checked in Chromium at desktop, 390 px, and 320 px widths, including
the complete mock flow, real checkout POSTs for s1–s8, and connected-API s2 replay.
See [ui/README.md](ui/README.md) for browser and UI test commands. The receipt print
layout fits one A4 page.

Live TinyFish execution, live OpenAI drafting, redeployment, physical-phone use,
and Python 3.11 execution have not been verified. Vercel publication is left to the
project owner. New s7/s8 cases run in the demo
fixture and mock UI; connected API support remains a backend integration task.
