# AgentGuard Schema v2

Source of truth for all branches. Do not change without telling the team.

## Global rules

- All money values are whole rupees as JSON integers. Never Decimal, never strings.
- null means unknown. A null that matters makes the checker return ask, never allow.
- Every failure path resolves to block or failed, never allow.
- Item type values stay as the current code defines them (ticket, insurance, meal, fee).

## contract

```json
{"route": {"from": "Ludhiana", "to": "Delhi"}, "date": "2026-10-26", "quantity": 1, "max_total": 1000, "allow_extras": false, "requirements": {"refundable": null, "seat_confirmed": null, "baggage": null}, "source": "parsed"}
```

- source is "parsed" or "fallback" (fallback means the fixed demo contract was used).
- requirements: true = must have, false = must not have, null = don't care.

## cart

```json
{"cart_id": "c_001", "items": [{"id": "t1", "type": "ticket", "price": 1000, "route": null, "date": null}], "total": 1000, "passengers": 1, "attributes": {"refundable": true, "seat_confirmed": true, "baggage": false}, "hidden_text": []}
```

- route and date on items are optional.
- total and passengers may be null (checker returns ask).
- attributes: null means unknown (checker returns ask only if the contract requires it).

## order_request

The real outgoing request, used by request_check.

```json
{"cart_id": "c_001", "items": [{"id": "t1", "price": 1000}], "total": 1000, "fields": {}}
```

- Each item has an id (string) and a price (integer rupees).
- total is integer rupees.
- fields is an object of any extra form fields sent with the request.

## decision

```json
{"result": "block", "reasons": ["Total Rs 1350 is over your Rs 1000 budget"], "remove_item_ids": ["x1", "m1"], "flags": [], "differing_fields": []}
```

- result is one of: allow, block, ask
- reasons: plain-language text, one per issue.
- remove_item_ids: items the fix step must remove from the cart.
- flags: short tags such as hidden_text or page_unverified.
- differing_fields: fields where the order request differs from the contract.

## question

Maximum 3 per task.

```json
{"key": "refundable", "text": "Do you need a refundable ticket?", "options": ["yes", "no", "don't care"]}
```

- "don't care" maps to null in the contract.

## task status values

awaiting_answers, awaiting_confirmation, staging, checking, blocked, fixing, allowed, committing, done, failed

Allowed transitions. All others are rejected and logged:

- awaiting_answers -> awaiting_confirmation
- awaiting_confirmation -> staging
- staging -> checking or failed
- checking -> allowed or blocked or failed
- blocked -> fixing or failed
- fixing -> checking or failed
- allowed -> committing
- committing -> done or failed

## Endpoints

- POST /tasks: body {sentence, scenario, guard_enabled}. Returns {task_id, draft_contract, questions}.
- POST /tasks/{id}/answers: body {answers: {key: "yes" or "no" or "don't care"}}. Returns {contract}.
- POST /tasks/{id}/confirm: body {contract} (optional). Returns {status}.
- POST /tasks/{id}/run: no body. Runs stage, check, fix, commit. Returns the final task.
- GET /tasks/{id}: returns the full task including decision history.
- GET /tasks/{id}/events: SSE stream of status changes.
- GET /tasks/{id}/receipt: returns receipt JSON.
- GET /tasks/{id}/receipt/verify: returns {valid, broken_at}.
- GET /health: returns {replay, tinyfish_configured, db_ok}.
- POST /stage: existing endpoint. Keep it working. Do not break it.

If no questions are needed, POST /tasks returns questions as an empty list and the task goes straight to awaiting_confirmation.

## receipt

```json
{"task_id": "...", "contract": {}, "events": [{"id": 1, "ts": "...", "type": "...", "payload": {}, "prev_hash": "...", "hash": "..."}], "final": {"order_id": "...", "total": 1000}, "signature": "..."}
```

- hash = sha256(prev_hash + canonical JSON of the event). The first prev_hash is 64 zeros.
- signature = HMAC-SHA256 of the last hash, using the key from env RECEIPT_KEY.
- The signature is demo-grade, not production security. State this in the README.

## Commit gate (must be enforced in code and tested)

Commit starts only if all three are true:

1. status is allowed
2. the latest decision.result is allow
3. sha256 of the canonical cart JSON equals the hash stored when the check ran

Otherwise return 409, write an audit event, and never call TinyFish.
