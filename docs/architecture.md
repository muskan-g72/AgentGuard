# Architecture

## Loop

1. **Stage:** An agent opens `index.html`, chooses a train, and opens `checkout.html`. The query string carries the cart state.
2. **Check:** `guard.checker.check()` compares a `Contract` and `Cart`. It checks missing fields, the ticket route and date, quantity, unauthorized extras, budget, item-total consistency, and hidden instruction-like text.
3. **Fix:** Planned. The checker returns `remove_item_ids` for unauthorized extras, but no browser or orchestration code removes them or restages a cart.
4. **Commit:** `checkout.html` sends the current query string to `confirmation.html` when the button with `id="confirm"` is pressed. The confirmation is simulated.

## Shared JSON messages

The following message shapes are the AgentGuard integration contract. `guard.models` validates these field names. The static browser site does not create or consume these JSON messages in code.

```json
{
  "contract": {"route": "Ludhiana-Delhi", "date": "2026-10-25", "quantity": 1, "max_total": 1000, "allow_extras": false},
  "cart": {"cart_id": "c_001", "items": [{"id": "t1", "type": "ticket", "price": 1000, "route": "Ludhiana-Delhi", "date": "2026-10-25"}, {"id": "x1", "type": "insurance", "price": 250}], "total": 1250, "passengers": 1},
  "decision": {"result": "allow|block|ask", "reasons": ["..."], "remove_item_ids": ["x1"], "flags": ["..."]}
}
```

Item types are `ticket`, `insurance`, `meal`, and `fee`.

## Files

- `index.html` implements search results and the scenario-four recommendation.
- `checkout.html` implements cart rows, extras, fee display, totals, the hidden scenario-five text, and confirmation navigation.
- `confirmation.html` implements the simulated confirmation view.
- `app.js` implements query-string state and ticket data.
- `styles.css` implements layout and the off-screen hidden element.
- `guard/models.py` defines `Contract`, `Item`, `Cart`, and `Decision` with Pydantic.
- `guard/checker.py` implements the network-free deterministic check.
- `guard/hidden_text.py` implements pattern matching for suspicious instruction text.
- `guard/contract_parser.py` sends the user text to the OpenAI Responses API with temperature zero and strict JSON when `OPENAI_API_KEY` is available. It returns the fixed demo contract after API or validation failures.
- `guard/demo.py` prints decisions for the local scenarios.
- `tests/test_scenarios.py` tests the scenario decisions and check timing.

## Simulated behavior

Orders are simulated. No payment is taken. There is no payment form and the site does not collect personal data. The cart is not persisted on a server; it is represented in the URL.

## Could not verify from the code

- A TinyFish Agent API integration.
- The run-one, run-two, run-three orchestration.
- A deployed public URL.
- Python 3.11 compatibility on this machine.
