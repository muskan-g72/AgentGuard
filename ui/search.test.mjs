import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
function page(search) {
  const context = vm.createContext({ URLSearchParams, location: { search } });
  vm.runInContext(source, context);
  return context.AgentGuardDemo;
}

test('searchState preserves edited route, travel date, and valid passenger counts', () => {
  const demo = page('?from=Mumbai&to=Pune&date=2026-11-01&passengers=4');
  const search = demo.searchState();
  assert.equal(search.from, 'Mumbai');
  assert.equal(search.to, 'Pune');
  assert.equal(search.date, '2026-11-01');
  assert.equal(search.passengers, 4);
  assert.equal(demo.bookingState().passengers, 4);
});

test('invalid passenger counts keep origin/main fallback validation', () => {
  for (const passengers of ['0', '-1', '101', '1.5', 'not-a-number']) {
    assert.equal(page('?passengers=' + passengers).searchState().passengers, 1);
  }
  assert.equal(page('?passengers=100').searchState().passengers, 100);
});

test('ticket URLs retain edited search fields and calculate group prices', () => {
  const demo = page('?scenario=s2&from=ludhiana&to=Delhi&date=2026-10-25&passengers=2');
  const selected = new URLSearchParams(demo.queryFor('t2'));
  assert.equal(selected.get('from'), 'ludhiana');
  assert.equal(selected.get('to'), 'Delhi');
  assert.equal(selected.get('date'), '2026-10-25');
  assert.equal(selected.get('passengers'), '2');
  assert.equal(selected.get('ticket'), 't2');
  assert.equal(selected.get('insurance'), '1');
  const state = { ...demo.bookingState(), ticket: demo.tickets.t2 };
  assert.equal(demo.ticketPrice(state), 2800);
  assert.equal(demo.totalPrice(state), 3150);
  assert.equal(demo.cartData(state).items[0].price, 2800);
});
