# Architecture

[Schema v2](schema.md) defines the shared wire messages, statuses, endpoints,
receipt chain, and mandatory commit gate. It must be coordinated across branches.

## Execution

`app.main:create_app` creates the FastAPI application. Startup loads the SQLite
store, receipt key, and replay or TinyFish driver; importing the module opens no
database and performs no network requests. Environment configuration is described
in the README.

1. Create a draft with `guard.contract_parser`. The optional LLM only drafts a
   contract. A failed or unavailable parser returns a labelled fixed fallback.
2. Ask up to three questions for unspecified preferences. All answers must be
   supplied before confirmation. False and null retain their different meanings.
3. User confirmation freezes the draft as the task contract and enters staging.
4. `/run` claims the task atomically and stages a cart. `guard.checker` checks all
   known violations, unknown facts, and hidden instructions with no I/O.
5. A blocked cart can be repaired once if all removable extras are optional meal
   or insurance items. Re-stage the repaired cart and check it again. Fees, wrong
   dates, missing facts, and hidden text cannot be auto-authorized.
6. Before entering allowed, prepare the outgoing payload and run
   `guard.request_check` against the saved allowed cart hash. It compares cart ID,
   item identities and prices, total, and extra form fields, and re-checks the
   contract. Live runs without trusted request capture are blocked.
7. Consume authorization in a SQLite transaction: status must be allowed, the
   latest decision must allow, and the current canonical cart hash must equal
   the saved hash. Contract and payload checks also apply. Rejection appends an
   audit event and returns 409 before any commit transport call.
8. Enter committing before calling the simulated merchant. A matching merchant
   confirmation completes the task; exceptions or invalid totals fail it.

Every status mutation uses the exact transition table in the schema. Invalid
transitions are rejected and logged. SQLite `BEGIN IMMEDIATE` serializes gate
consumption; a task cannot commit twice. A run interrupted during commit is not
automatically retried, because the order outcome may be unknown.

`guard_enabled=false` skips automatic repair; mandatory checking remains active.
An ask decision maps to a blocked task because the schema has no transition from
checking back to awaiting_answers.

## Storage and proofs

Tasks and events are separate SQLite tables. State changes and their audit events
are committed together. Audit events include drafts, answers, the confirmed
contract, staged/fixed carts, decisions, gate failures, status changes, the outgoing
payload, and the final order. Failure logs omit vendor response bodies and secrets.

For a complete validated cart, canonical JSON is compact, sorted-key UTF-8 with no
non-finite numbers. The cart hash is SHA256 of those bytes. Event bodies contain
only `id`, `ts`, `type`, and `payload`; the hash is SHA256 of the previous hex hash
concatenated with that canonical body. The first previous hash is 64 zeros.
The event's `prev_hash` and `hash` metadata are not recursively included.

HMAC-SHA256 signs the latest event hash at mutation time using `RECEIPT_KEY`.
Receipt reads do not re-sign database contents. Verification checks sequence,
hash links, signature, and the envelope's task ID, contract, and final order.
Receipt signatures are demo-grade, not production security.

## Boundaries

- `guard/models.py`: strict schema validation and integer rupees.
- `guard/checker.py`, `guard/request_check.py`: pure deterministic checks.
- `guard/contract_parser.py`: draft-only optional OpenAI API boundary.
- `app/drivers.py`: deterministic replay and TinyFish public-site staging/repair.
- `app/store.py`: SQLite transactions, transition table, chain and signature.
- `app/service.py`: question/confirmation lifecycle, bounded repair, commit gate.
- `app/main.py`: endpoint validation, SSE status streaming, receipts and health.
- Static HTML/JS: separate URL-based booking fixture with simulated confirmation.

The public TinyFish adapter cannot safely commit until trusted request interception
exists. It fails closed with `page_unverified`. The static pages do not enforce
the API gate. No existing `/stage` implementation was available to compare with
other branches; the new read-only route's request/response is documented in README.
