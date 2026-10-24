# AgentGuard Schema v2

Source of truth for all branches. Do not change without telling the team.

## Global rules

- All money values are whole rupees as JSON integers. Never Decimal, never strings.
- `null` means unknown. A null that matters makes the checker return `ask`, never `allow`.
- Every failure path resolves to `block` or `failed`, never `allow`.
- Item type values stay as the current code defines them: `ticket`, `insurance`, `meal`, `fee`.

## contract

```json
{"route":{"from":"Ludhiana","to":"Delhi"},"date":"2026-10-26","quantity":1,"max_total":1000,"allow_extras":false,"requirements":{"refundable":null,"seat_confirmed":null,"baggage":null},"source":"parsed"}
```

- `source` is `parsed` or `fallback`.
- Requirements use `true` for must have, `false` for must not have, and `null` for don't care.

## cart

```json
{"cart_id":"c_001","items":[{"id":"t1","type":"ticket","price":1000,"route":null,"date":null}],"total":1000,"passengers":1,"attributes":{"refundable":true,"seat_confirmed":true,"baggage":false},"hidden_text":[]}
```

- Ticket item route and date are optional.
- Total and passengers may be null.
- Attribute null means unknown; the checker asks only when the contract requires that attribute.

## order_request

```json
{"cart_id":"c_001","items":[{"id":"t1","price":1000}],"total":1000,"fields":{}}
```

## decision

```json
{"result":"block","reasons":["Total Rs 1350 is over your Rs 1000 budget"],"remove_item_ids":["x1","m1"],"flags":[],"differing_fields":[]}
```

## question

At most three questions per task.

```json
{"key":"refundable","text":"Do you need a refundable ticket?","options":["yes","no","don't care"]}
```

## Task statuses and transitions

Statuses: `awaiting_answers`, `awaiting_confirmation`, `staging`, `checking`, `blocked`, `fixing`, `allowed`, `committing`, `done`, `failed`.

Allowed transitions:

- `awaiting_answers` → `awaiting_confirmation`
- `awaiting_confirmation` → `staging`
- Rejected origin or other pre-run refusal: `awaiting_confirmation` → `failed`.
- `staging` → `checking` or `failed`
- `checking` → `allowed`, `blocked`, or `failed`
- `blocked` → `fixing` or `failed`
- `fixing` → `checking` or `failed`
- `allowed` → `committing`
- `committing` → `done` or `failed`

## API endpoints

- `POST /tasks`
- `POST /tasks/{id}/answers`
- `POST /tasks/{id}/confirm`
- `POST /tasks/{id}/run`
- `GET /tasks/{id}`
- `GET /tasks/{id}/events`
- `GET /tasks/{id}/receipt`
- `GET /tasks/{id}/receipt/verify`
- `GET /health`
- `POST /stage`

## Receipt

```json
{"task_id":"...","contract":{},"events":[{"id":1,"ts":"...","type":"...","payload":{},"prev_hash":"...","hash":"..."}],"final":{"order_id":"...","total":1000},"signature":"..."}
```

Each event hash is `sha256(prev_hash + canonical JSON of the event)` and the first previous hash is 64 zeroes. The receipt signature is HMAC-SHA256 of the final hash using `RECEIPT_KEY`.

## Commit gate

Commit starts only if the task is `allowed`, the latest decision result is `allow`, and the canonical cart SHA-256 matches the hash stored at check time. Otherwise it returns 409, writes an audit event, and never calls TinyFish.
