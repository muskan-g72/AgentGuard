# Architecture

> **Historical prototype snapshot.** The current implementation is documented in [current-status.md](current-status.md). It replaces the unconditional confirmation and missing approval/order flow described below. Existing notes are preserved for comparison.

## Intended loop and current implementation

1. **Confirm instructions — Planned.** The user would review a contract before an agent starts. `guard/contract_parser.py` can attempt external LLM parsing with a fixed demo fallback. No UI confirms its output. The API and CLI use `DEMO_CONTRACT` directly.
2. **Run 1: stage — partly implemented.** The static pages let a user search, select a ticket, and open checkout. `app/staging.py` builds a TinyFish goal to stage a cart and stop before Confirm, Pay, Place order, Submit, or equivalent actions. `app/tinyfish_client.py` contains the live request code. Live execution and obedience to the goal are unverified. `REPLAY=1` reads the s2 fixture without a browser or network call.
3. **Check — implemented for supplied messages.** `guard/checker.py` compares a Contract and Cart, with hidden text supplied separately. `POST /stage` stages once, checks against the fixed demo contract, and returns cart and decision. Browser pages never call it.
4. **Run 2: fix and recheck — Planned.** The guard returns removal IDs for unauthorized extras. No orchestrator uses them to remove extras or restage. A person can uncheck insurance and meal manually. The repaired-s2 Python fixture is separately constructed; it does not prove an agent repair run.
5. **Run 3: commit after allow — Planned.** No backend commit run or decision-to-cart binding exists. The existing `#confirm` button always navigates to `confirmation.html`. It does not call or enforce the Python checker and does not stop on block or ask. The order is simulated.

## Browser state and pricing

`app.js` holds T1 (25 October, Rs 1,000), T2 (25 October, Rs 1,400), and T3 (26 October, Rs 900), all on Ludhiana-Delhi. `index.html` matches route without case sensitivity and date exactly. Unmatched searches show "No trains found". s4 deliberately includes and promotes T3 for the matching route even if the requested date differs. The ticket's true date remains unchanged and displayed.

Submitted searches store `from`, `to`, `date`, and `passengers` in the index URL. Links carry those values, `scenario`, `cart_id`, `ticket`, `insurance`, `meal`, and `fee` through checkout and confirmation. `date` is the requested date; the selected ticket date comes from inventory. This preserves the s4 mismatch. Original direct scenario URLs default to one passenger.

Fares are per passenger. `ticketPrice()` multiplies fare by passengers for one group ticket row. `totalPrice()` adds insurance (250), meal (100), and fee (180) once per booking. Checkout's ticket `data-price` and confirmation use the group amount. `bookingParams()` carries current state through navigation and checkbox URL updates.

Checkout preserves `data-item-id`, `data-item-type`, and `data-price`, `#total` with `data-total`, and `#confirm`. Unchecked options still have rows; extraction must exclude them. s5 adds an off-screen `data-hidden="true"` note. s6 removes the passenger display, omits passenger count from the ticket label, and sets `data-total="unknown"`. Internal URL state remains present. Its confirmation displays computed values.

## Shared JSON messages

These are the shared field names. `guard/models.py` validates each nested model and forbids extra fields. The site does not serialize these messages or consume decisions. Python uses Decimal for prices and totals; Pydantic JSON output may represent them as strings.

```json
{
  "contract": {
    "route": "Ludhiana-Delhi",
    "date": "2026-10-25",
    "quantity": 1,
    "max_total": 1000,
    "allow_extras": false
  },
  "cart": {
    "cart_id": "c_001",
    "items": [
      {
        "id": "t1",
        "type": "ticket",
        "price": 1000,
        "route": "Ludhiana-Delhi",
        "date": "2026-10-25"
      }
    ],
    "total": 1000,
    "passengers": 1
  },
  "decision": {
    "result": "allow|block|ask",
    "reasons": ["..."],
    "remove_item_ids": [],
    "flags": []
  }
}
```

`result` is one of allow, block, or ask. Item types are ticket, insurance, meal, and fee. Quantity is intended to mean authorized passengers. `max_total` is inclusive, so the demo allows exactly Rs 1,000.

The live staging response uses `{"cart": {...}, "hidden_text": [], "checkout_html": "<section id=...>...</section>", "extraction_error": null}`. `checkout_html` must contain the literal checkout cart HTML, including each row's `data-item-id` and `data-item-type` attributes. Staging compares every returned item ID and type with those rows and rejects missing, duplicate, or mismatched IDs. If the attributes cannot be read, the agent must return `cart: null` and an explanation in `extraction_error` instead of inventing IDs. Staging retries one invalid extraction, then reports an error without returning a cart for removal. This validates agent-supplied HTML; it is not independent proof of the remote DOM. The shared Contract, Cart, and Decision models are unchanged. The curated replay fixture retains its existing cart/hidden_text envelope without HTML evidence.

Hidden text is supplied separately to `check()`, not stored in Cart. Missing information uses `"total": null` and `"passengers": null`. The staging prompt requests those fields but does not explicitly explain s6's unknown-to-null mapping. Replay reads saved data rather than extracting the site.

## Checker behavior and mismatches

The checker applies these rules in order: missing total/ticket/passengers → ask; route/date mismatch → block; ticket-row count differs from quantity → block; forbidden extras → block with removal IDs; total above cap → block; item sum differs from total → block; suspicious supplied hidden text → ask with flags; otherwise allow. Hidden text cannot weaken a previous block. `guard/hidden_text.py` only scans supplied strings using a small set of regular expressions.

The quantity rule does not implement passenger authorization. It counts ticket rows and never compares a present `cart.passengers` with `contract.quantity`. The preceding route/date rule requires exactly one matching row. One correctly priced group row for two authorized passengers is blocked as only one item; two matching rows are also blocked. With sufficient budget, a one-row cart with an unauthorized passenger count can pass. The Python schema and rules are unchanged in this site task.

Other gaps: extraction must exclude unchecked extras, supply s5's hidden text separately, and map s6's unknown values to null. No deterministic extractor implements these translations. The backend always uses the fixed one-passenger contract. Python fixtures use different cart IDs for s2-s6, while original browser URLs use c_001; the checker does not authorize by cart ID.

## Files and backend flow

| Files | Responsibility |
| --- | --- |
| `index.html` | Editable form, validation, filtered results, s4 promotion |
| `app.js` | Inventory, URL defaults/state, group pricing |
| `checkout.html` | Cart rows, extras, fee, s5/s6, URL updates, unconditional confirmation navigation |
| `confirmation.html`, `styles.css` | Simulated order view and styling, including off-screen note |
| `guard/models.py`, `guard/checker.py`, `guard/hidden_text.py` | Message validation, rules, supplied hidden-text scan |
| `guard/contract_parser.py` | Demo contract and optional LLM parser with fallback |
| `guard/scenarios.py`, `guard/demo.py` | Six fixtures, repaired s2, printed local decisions |
| `app/tinyfish_client.py` | Synchronous TinyFish POST with url, goal, X-API-Key; validates COMPLETED status and result |
| `app/staging.py` | Goal, result parsing, one parse retry, scenario recording read/write, replay |
| `app/main.py` | POST /stage with cart_url and scenario; stages/checks once; returns cart/decision; maps StagingError to HTTP 502 |
| `app/log.py` | SQLite events at data/events.db: request, cart, decision, or failure |
| `scripts/stage_once.py`, `recordings/s2.json` | CLI stage/check and offline fixture |
| `tests/test_scenarios.py`, `tests/test_staging_replay.py` | Guard expectations, timing assertion, s2 replay |
| `pyproject.toml`, `.env.example`, `.gitignore` | Dependencies, test setup, key placeholder, ignored local files |

Live staging saves each raw result to a unique `recordings/live/<scenario>_<uuid>.json` file, including failed extractions and retries. It never writes to `recordings/s2.json`, the stable replay fixture. Replay selects by scenario without verifying the URL against the cart. Only the API uses SQLite logging. Its allow stub for a missing guard is not a reliable guard-free mode because staging imports guard models before the fallback.

## What is simulated

Inventory, extras, fees, cart IDs, and order IDs are demo data. There is no payment, seat reservation, personal-data form, or server order record. Browser state is entirely in the URL. Opening confirmation directly produces a simulated order view. SQLite stores backend events rather than bookings.

The s2 recording is a replay fixture. Its presence does not prove an external agent run occurred. Existing tests exercise Python fixtures and replay, not browser navigation or the complete loop. Deployment, live agent behavior, and benchmark claims are not established by this repository.

## Could not verify from the code

- Successful live TinyFish requests, stop-before-confirm behavior, or extraction of all six browser scenarios.
- Successful live contract parsing and user confirmation of its output or fallback.
- A deployed site reachable by an external agent.
- Automated Run 2 repair, recheck, Run 3 commit, or guard-enforced confirmation; these are Planned.
- External evaluation results or benchmark metrics.
- Completed browser verification; Computer Use was stopped by the user.
