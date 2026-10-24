(function () {
  'use strict';
  const demo = AgentGuardDemo;
  const state = demo.bookingState();
  const cartElement = document.getElementById('cart');
  document.getElementById('cart-id').textContent = state.cartId;
  const money = (value) => 'Rs ' + value.toLocaleString('en-IN');
  function row(item, label) {
    const element = document.createElement('div');
    element.className = 'row';
    Object.assign(element.dataset, { itemId: item.id, itemType: item.type, price: item.price });
    const text = document.createElement('span'); text.textContent = label;
    const price = document.createElement('strong'); price.textContent = money(item.price);
    element.append(text, price); return element;
  }
  function render() {
    const cart = demo.cartData(state);
    window.agentGuardCart = cart; // Schema v2 snapshot for DOM extraction.
    cartElement.replaceChildren();
    for (const item of cart.items) {
      const names = { ticket: `${state.ticket.name}: ${state.ticket.route}, ${state.ticket.date}`,
        insurance: 'Travel insurance', meal: 'Priority meal', fee: 'Convenience fee (applied at checkout)' };
      cartElement.append(row(item, names[item.type]));
    }
    if (state.scenario !== 's7') {
      const extras = document.createElement('fieldset'); extras.className = 'extras';
      const legend = document.createElement('legend'); legend.textContent = 'Optional extras'; extras.append(legend);
      for (const [key, label] of [['insurance', 'Travel insurance · Rs 250'], ['meal', 'Priority meal · Rs 100']]) {
        const option = document.createElement('label');
        const input = document.createElement('input'); input.type = 'checkbox'; input.id = key; input.checked = state[key];
        input.addEventListener('change', () => { state[key] = input.checked; updateUrl(); render(); });
        option.append(input, document.createTextNode(label)); extras.append(option);
      }
      cartElement.append(extras);
    }
    if (cart.hidden_text.length) {
      const hidden = document.createElement('div'); hidden.className = 'hidden-agent-note'; hidden.dataset.hidden = 'true';
      hidden.textContent = cart.hidden_text[0]; cartElement.append(hidden);
    }
    const requirements = document.getElementById('requirements'); requirements.replaceChildren();
    for (const [key, label] of [['refundable', 'Refundable'], ['seat_confirmed', 'Seat confirmed'], ['baggage', 'Baggage included']]) {
      const element = document.createElement('p'); element.className = 'requirement';
      element.dataset.attribute = key; element.dataset.value = String(cart.attributes[key]);
      element.textContent = `${label}: ${cart.attributes[key] ? 'Yes' : 'No'}`; requirements.append(element);
    }
    const total = document.getElementById('total');
    total.textContent = cart.total === null ? 'calculated at payment' : money(cart.total);
    total.dataset.total = cart.total === null ? 'unknown' : String(cart.total);
    document.getElementById('passengers').hidden = cart.passengers === null;
    document.getElementById('requirements').dataset.attributes = JSON.stringify(cart.attributes);
  }
  function updateUrl() {
    demo.params.set('insurance', state.insurance ? '1' : '0'); demo.params.set('meal', state.meal ? '1' : '0');
    history.replaceState(null, '', 'checkout.html?' + demo.params.toString());
  }
  render();
  document.getElementById('confirm').addEventListener('click', async () => {
    const button = document.getElementById('confirm'); const error = document.getElementById('order-error');
    button.disabled = true; button.textContent = 'Placing simulated order…'; error.hidden = true;
    try {
      // Construct the actual outgoing request here, never from displayed totals.
      const order = demo.buildOrder(state);
      const response = await fetch('/api/order', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(order), signal: AbortSignal.timeout(15000)
      });
      if (!response.ok) throw new Error('Order not placed. Please try again.');
      const confirmation = await response.json();
      if (typeof confirmation.order_id !== 'string' || !confirmation.order_id || !Number.isSafeInteger(confirmation.total)
        || confirmation.total < 0 || !Array.isArray(confirmation.items)
        || confirmation.items.some(item => typeof item.id !== 'string' || !Number.isSafeInteger(item.price) || item.price < 0)
        || confirmation.items.reduce((sum, item) => sum + item.price, 0) !== confirmation.total) {
        throw new Error('The order response could not be verified.');
      }
      // Confirmation is populated from the server response, not reconstructed
      // from the clean cart URL. Fall back to inline confirmation if storage fails.
      try {
        sessionStorage.setItem('agentguard:last-order', JSON.stringify(confirmation));
        location.href = 'confirmation.html?order_id=' + encodeURIComponent(confirmation.order_id);
      } catch {
        button.hidden = true; cartElement.replaceChildren();
        const message = document.createElement('p'); message.textContent = `Simulated order ${confirmation.order_id}: ${money(confirmation.total)}.`;
        cartElement.append(message); document.querySelector('h1').textContent = 'Booking confirmed';
        document.getElementById('total').textContent = money(confirmation.total);
      }
    } catch (failure) {
      error.textContent = failure.name === 'TimeoutError' ? 'The order timed out. No confirmation was received.' : failure.message;
      error.hidden = false; button.disabled = false; button.textContent = 'Retry Place Order';
    }
  });
}());
