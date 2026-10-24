/* The server owns prices, cart versions, approvals and orders. */
(async () => {
  'use strict';
  const $ = id => document.getElementById(id);
  const params = new URLSearchParams(location.search);
  const initial = AgentGuardDemo.bookingState();
  let state = {scenario: initial.scenario, ticket: initial.ticket.id, from: initial.from,
    to: initial.to, date: initial.date, passengers: initial.passengers,
    insurance: initial.insurance, meal: initial.meal, fee: initial.fee};
  let record, catalog, task, approval = null, syncPromise = Promise.resolve();
  window.guardReady = false;
  async function api(path, body, method = 'POST') {
    const response = await fetch(path, {method, headers: {'Content-Type': 'application/json'},
      ...(body === undefined ? {} : {body: JSON.stringify(body)})});
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'The server rejected invalid booking data.');
    return result;
  }
  function status(message) { $('guard-status').textContent = message; }
  function invalidate() { approval = null; $('confirm').disabled = true; }
  function url() {
    const p = new URLSearchParams();
    Object.entries(state).forEach(([key, value]) => p.set(key, typeof value === 'boolean' ? (value ? '1' : '0') : value));
    p.set('cart_id', record.cart_id);
    if (task) p.set('task_id', task.task_id);
    history.replaceState(null, '', 'checkout.html?' + p);
  }
  const labels = {ticket: 'Ticket', insurance: 'Travel insurance', meal: 'Priority meal', fee: 'Convenience fee (cannot be removed)'};
  function render() {
    const cart = record.cart;
    $('cart-id').textContent = record.cart_id;
    const section = $('cart');
    section.replaceChildren();
    section.dataset.cartId = record.cart_id;
    section.dataset.version = record.version;
    Object.entries(cart.attributes).forEach(([key, value]) => section.setAttribute('data-' + key.replaceAll('_', '-'), value === null ? 'unknown' : String(value)));
    const rows = [...cart.items.filter(item => item.type === 'ticket'), ...catalog.extras,
      ...cart.items.filter(item => item.type === 'fee')];
    rows.forEach(item => {
      const row = document.createElement('div'); row.className = 'row';
      Object.entries({itemId: item.id, itemType: item.type, price: item.price,
        route: item.route || '', date: item.date || ''}).forEach(([key, value]) => row.dataset[key] = value);
      const description = document.createElement('span');
      description.textContent = item.type === 'ticket' ? `${item.id.toUpperCase()}: ${item.route}, ${item.date}` : labels[item.type];
      const price = document.createElement('span'); price.textContent = 'Rs ' + item.price.toLocaleString('en-IN');
      if (item.type === 'insurance' || item.type === 'meal') {
        const label = document.createElement('label'), checkbox = document.createElement('input');
        checkbox.type = 'checkbox'; checkbox.id = item.type; checkbox.checked = Boolean(state[item.type]);
        checkbox.addEventListener('change', () => {
          state[item.type] = checkbox.checked; invalidate(); window.guardReady = false;
          const update = {...state};
          syncPromise = syncPromise.then(async () => {
            record = await api('/api/carts/' + record.cart_id, update, 'PUT');
            render(); url(); status('Cart updated. Check the current cart again.'); window.guardReady = true;
          }).catch(error => { status(error.message); window.guardReady = false; });
        });
        label.append(checkbox, document.createTextNode(' Add')); price.append(label);
      }
      row.append(description, price); section.append(row);
    });
    cart.hidden_text.forEach(text => { const note = document.createElement('div');
      note.className = 'hidden-agent-note'; note.dataset.hidden = 'true'; note.textContent = text; section.append(note); });
    $('total').dataset.total = cart.total === null ? 'unknown' : String(cart.total);
    $('total').textContent = cart.total === null ? 'calculated at payment' : 'Rs ' + cart.total.toLocaleString('en-IN');
    const passengers = $('passengers');
    passengers.textContent = cart.passengers === null ? '' : 'Passengers: ' + cart.passengers;
    passengers.dataset.passengers = cart.passengers === null ? 'unknown' : String(cart.passengers);
    passengers.hidden = cart.passengers === null;
  }
  function extract() {
    const section = $('cart');
    const integer = value => /^\d+$/.test(value) ? Number(value) : null;
    const attributes = {};
    ['refundable', 'seat_confirmed', 'baggage'].forEach(key => {
      const value = section.getAttribute('data-' + key.replaceAll('_', '-'));
      attributes[key] = value === 'true' ? true : value === 'false' ? false : null;
    });
    return {cart_id: section.dataset.cartId,
      items: [...section.querySelectorAll('[data-item-id]')].filter(row => !row.querySelector('input[type=checkbox]') || row.querySelector('input[type=checkbox]').checked).map(row => ({
        id: row.dataset.itemId, type: row.dataset.itemType, price: integer(row.dataset.price),
        route: row.dataset.route || null, date: row.dataset.date || null})),
      total: integer($('total').dataset.total), passengers: $('passengers').hidden ? null : integer($('passengers').dataset.passengers),
      attributes, hidden_text: [...new Set([...section.querySelectorAll('*')].filter(node => {
        const style = getComputedStyle(node), rect = node.getBoundingClientRect();
        return node.dataset.hidden === 'true' || node.getAttribute('aria-hidden') === 'true' ||
          style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0 ||
          parseFloat(style.fontSize) === 0 || rect.right < 0 || rect.bottom < 0;
      }).map(node => node.textContent.trim()).filter(Boolean))]};
  }
  async function checkCart() {
    await syncPromise; invalidate();
    if (!window.guardReady || !task?.reviewed) throw new Error('Review and authorize the instructions before checking.');
    const result = await api('/api/carts/' + record.cart_id + '/check', {task_id: task.task_id, cart: extract()});
    approval = result.approval; $('confirm').disabled = !approval;
    status(result.decision.result.toUpperCase() + ': ' + result.decision.reasons.join(' '));
    return result;
  }
  async function fix() {
    let result = await checkCart();
    if (result.decision.result !== 'block' || !result.decision.remove_item_ids.length) return result;
    for (const id of result.decision.remove_item_ids) {
      const row = [...$('cart').querySelectorAll('[data-item-id]')].find(node => node.dataset.itemId === id);
      const checkbox = row?.querySelector('input[type=checkbox]');
      if (!checkbox || checkbox.disabled) { status('BLOCK: Item ' + id + ' cannot be removed. No order was created.'); return result; }
      if (checkbox.checked) { checkbox.click(); await syncPromise; }
    }
    return checkCart();
  }
  function onError(error) { invalidate(); status(error.message); }
  $('check-cart').onclick = () => checkCart().catch(onError);
  $('check-fix').onclick = () => fix().catch(onError);
  $('prepare-contract').onclick = async () => {
    try {
      invalidate();
      const maxTotal = Number($('budget').value);
      if (!$('budget').reportValidity() || !Number.isInteger(maxTotal)) return;
      const draft = {route: {from: state.from, to: state.to}, date: state.date, quantity: state.passengers,
        max_total: maxTotal, allow_extras: false, requirements: {refundable: null, seat_confirmed: null, baggage: null}, source: 'parsed'};
      task = await api('/tasks', {sentence: `Book ${state.passengers} ticket(s) from ${state.from} to ${state.to} on ${state.date}, maximum Rs ${maxTotal}, no extras.`,
        scenario: state.scenario, draft_contract: draft});
      $('contract-preview').textContent = JSON.stringify(task.draft_contract, null, 2);
      $('questions').replaceChildren(); $('authorize-contract').checked = false;
      task.questions.forEach(question => {
        const label = document.createElement('label'), select = document.createElement('select');
        select.name = question.key; select.required = true; select.add(new Option('Choose an answer', ''));
        question.options.forEach(value => select.add(new Option(value, value)));
        label.append(document.createTextNode(question.text + ' '), select); $('questions').append(label);
      });
      $('review-form').hidden = false; url();
    } catch (error) { onError(error); }
  };
  $('review-form').onsubmit = async event => {
    event.preventDefault();
    try {
      if (!$('review-form').reportValidity()) return;
      const answers = Object.fromEntries([...$('questions').querySelectorAll('select')].map(select => [select.name, select.value]));
      await api('/tasks/' + task.task_id + '/answers', {answers});
      task = await api('/tasks/' + task.task_id + '/confirm', {});
      $('review-form').hidden = true; $('review-status').textContent = 'Instructions reviewed and authorized.';
      $('check-cart').disabled = $('check-fix').disabled = false; url(); status('Ready to check the current cart.');
    } catch (error) { onError(error); }
  };
  $('confirm').onclick = async () => {
    try {
      await syncPromise;
      if (!approval) throw new Error('A current server approval is required.');
      const cart = extract();
      const order = await api('/api/carts/' + record.cart_id + '/confirm', {task_id: task.task_id, approval,
        order_request: {cart_id: cart.cart_id, items: cart.items.map(({id, price}) => ({id, price})), total: cart.total, fields: {}}});
      location.href = 'confirmation.html?order_id=' + encodeURIComponent(order.order_id);
    } catch (error) { onError(error); }
  };
  window.AgentGuardCheckout = {extract, check: checkCart, fix, synced: () => syncPromise};
  try {
    catalog = await api('/api/catalog', undefined, 'GET');
    if (params.has('ticket') && !Object.hasOwn(catalog.tickets, params.get('ticket'))) {
      throw new Error('Unknown ticket ID in the URL; select a real ticket from search results.');
    }
    const existing = params.get('cart_id');
    record = existing?.startsWith('cart_') ? await api('/api/carts/' + existing, state, 'PUT') : await api('/api/carts', state);
    state = record.state; render();
    if (params.get('task_id')) {
      task = await api('/tasks/' + params.get('task_id'), undefined, 'GET');
      if (task.reviewed) { $('authorization').hidden = true; $('check-cart').disabled = $('check-fix').disabled = false; }
    }
    url(); $('prepare-contract').disabled = false; window.guardReady = true;
    status(task?.reviewed ? 'Ready to check the current cart.' : 'Review and authorize your instructions to continue.');
  } catch (error) { onError(error); status('Booking server unavailable or invalid data: ' + error.message); }
})();
