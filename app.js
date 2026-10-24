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
  function bookingState() {
    const ticket = tickets[params.get('ticket')] || tickets[scenario === 's4' ? 't3' : 't1'];
    return {
      scenario, cartId: params.get('cart_id') || 'c_001', ticket,
      insurance: bool('insurance', scenario === 's2'),
      meal: bool('meal', scenario === 's2'),
      fee: bool('fee', scenario === 's3'),
      passengers: 1
    };
  }
  function queryFor(ticketId) {
    const s = scenario;
    return new URLSearchParams({ cart_id: 'c_001', scenario: s, ticket: ticketId,
      insurance: s === 's2' ? '1' : '0', meal: s === 's2' ? '1' : '0', fee: s === 's3' ? '1' : '0' }).toString();
  }
  window.AgentGuardDemo = { params, scenario, tickets, bookingState, queryFor };
}());
