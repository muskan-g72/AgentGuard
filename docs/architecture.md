# Architecture

## Loop

1. **Stage:** An agent opens `index.html`, chooses a train, and opens `checkout.html`. The query string carries the cart state.
2. **Check:** Planned. The repository does not contain a checker that compares the cart with an authorization contract.
3. **Fix:** Planned. The repository does not contain code that removes blocked extras or restages a cart.
4. **Commit:** `checkout.html` sends the current query string to `confirmation.html` when the button with `id="confirm"` is pressed. The confirmation is simulated.

## Shared JSON messages

The following message shapes are the AgentGuard integration contract. This static site does not create or consume these JSON messages in code.

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

## Simulated behavior

Orders are simulated. No payment is taken. There is no payment form and the site does not collect personal data. The cart is not persisted on a server; it is represented in the URL.

## Could not verify from the code

- A TinyFish Agent API integration.
- The separate checker service and its allow, block, ask decisions.
- The run-one, run-two, run-three orchestration.
- A deployed public URL.
