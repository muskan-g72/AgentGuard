(function () {
  const params = new URLSearchParams(location.search);
  const scenario = params.get('scenario') || 's1';
  const tickets = {
    t1: { id: 't1', route: 'Ludhiana-Delhi', date: '2026-10-25', price: 1000, name: 'T1' },
    t2: { id: 't2', route: 'Ludhiana-Delhi', date: '2026-10-25', price: 1400, name: 'T2' },
    t3: { id: 't3', route: 'Ludhiana-Delhi', date: '2026-10-26', price: 900, name: 'T3' }
  };
  function bool(name, fallback) {
    return params.has(name) ? params.get(name) === '1' : fallback;
  }
  function searchState() {
    const passengers = Number(params.get('passengers') || 1);
    return {
      from: params.get('from') ?? 'Ludhiana',
      to: params.get('to') ?? 'Delhi',
      date: params.get('date') ?? '2026-10-25',
      passengers: Number.isInteger(passengers) && passengers >= 1 && passengers <= 100 ? passengers : 1
    };
  }
  function bookingState() {
    const ticket = tickets[params.get('ticket')] || tickets[scenario === 's4' ? 't3' : 't1'];
    return {
      scenario, cartId: params.get('cart_id') || 'c_001', ticket,
      insurance: bool('insurance', scenario === 's2'),
      meal: bool('meal', scenario === 's2'),
      fee: bool('fee', scenario === 's3'),
      ...searchState()
    };
  }
  // The ticket row covers the whole group. Extras are flat charges per booking.
  function ticketPrice(state) { return state.ticket.price * state.passengers; }
  function totalPrice(state) {
    return ticketPrice(state) + (state.insurance ? 250 : 0) +
      (state.meal ? 100 : 0) + (state.fee ? 180 : 0);
  }
  function bookingParams(state) {
    const p = new URLSearchParams(params);
    Object.entries({ scenario: state.scenario, cart_id: state.cartId, ticket: state.ticket.id,
      from: state.from, to: state.to, date: state.date, passengers: state.passengers,
      insurance: state.insurance ? '1' : '0', meal: state.meal ? '1' : '0',
      fee: state.fee ? '1' : '0' }).forEach(([key, value]) => p.set(key, value));
    return p;
  }
  function queryFor(ticketId) {
    return bookingParams({ ...bookingState(), ticket: tickets[ticketId] }).toString();
  }
  window.AgentGuardDemo = { params, scenario, tickets, searchState, bookingState,
    ticketPrice, totalPrice, bookingParams, queryFor };
}());
