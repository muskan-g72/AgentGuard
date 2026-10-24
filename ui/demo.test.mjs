import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { MockAPI } from './mock-api.mjs';
import { esc, rupees } from './format.mjs';
const require = createRequire(import.meta.url);
const demo = require('../app.js');

async function ready(scenario, { guard = true, refundable = "don't care" } = {}) {
  const api = new MockAPI({ pace: 0 });
  const draft = await api.create({ sentence: 'One ticket, max Rs 1000', scenario, guard_enabled: guard });
  assert.equal(draft.questions.length, 3);
  const answers = Object.fromEntries(draft.questions.map(question => [question.key, question.key === 'refundable' ? refundable : "don't care"]));
  const result = await api.answers(draft.task_id, answers);
  await api.confirm(draft.task_id, result.contract);
  return { api, id: draft.task_id };
}

test('all eight scenarios expose schema v2 attributes and integer item prices', () => {
  for (const scenario of Object.keys(demo.scenarios)) {
    const cart = demo.cartData(demo.scenarioState(scenario));
    assert.deepEqual(Object.keys(cart.attributes).sort(), ['baggage', 'refundable', 'seat_confirmed']);
    assert.equal(typeof cart.attributes.refundable, 'boolean');
    assert.ok(cart.items.every(item => Number.isSafeInteger(item.price)));
    assert.ok(cart.total === null || Number.isSafeInteger(cart.total));
  }
});

test('s7 screen is clean while click-time request adds both hidden charges', () => {
  const state = demo.scenarioState('s7', { insurance: true, meal: true, fee: true, ticket: demo.tickets.t2 });
  const cart = demo.cartData(state);
  assert.equal(cart.total, 1000); assert.equal(cart.items.length, 1);
  const request = demo.buildOrder(state);
  assert.equal(request.total, 1500);
  assert.deepEqual(request.items, [{ id: 't1', price: 1000 }, { id: 'x1', price: 250 }, { id: 'f1', price: 250 }]);
  assert.equal(cart.items.length, 1, 'building a request must not change the visible cart');
});

for (const [scenario, outcome, result] of [
  ['s1', 'done', 'allow'], ['s2', 'done', 'allow'], ['s3', 'blocked', 'block'],
  ['s4', 'blocked', 'block'], ['s5', 'blocked', 'ask'], ['s6', 'blocked', 'ask'],
  ['s7', 'blocked', 'block'], ['s8', 'done', 'allow']
]) test(`${scenario} mock loop produces the expected safe outcome`, async () => {
  const { api, id } = await ready(scenario);
  await api.run(id);
  const task = await api.get(id);
  assert.equal(task.status, outcome); assert.equal(task.running, false);
  assert.equal(task.decision_history.at(-1).result, result);
  if (scenario === 's2') {
    assert.equal(task.final.total, 1000);
    assert.deepEqual(task.decision_history.map(entry => entry.result), ['block', 'allow', 'allow']);
    assert.deepEqual(task.events.find(event => event.type === 'cart_fixed').payload.remove_item_ids, ['x1', 'm1']);
  }
  if (scenario === 's7') { assert.equal(task.decision_history.at(-1).phase, 'request'); assert.equal(task.final, null); }
  assert.deepEqual(await api.verify(id), { valid: true, broken_at: null });
  const receipt = await api.receipt(id);
  assert.deepEqual(Object.keys(receipt).sort(), ['contract', 'events', 'final', 'signature', 'task_id']);
});

test('non-refundable cart blocks a refundable requirement', async () => {
  const { api, id } = await ready('s8', { refundable: 'yes' });
  await api.run(id); const task = await api.get(id);
  assert.equal(task.status, 'blocked');
  assert.deepEqual(task.decision_history.at(-1).differing_fields, ['attributes.refundable']);
});

test('guard OFF disables repair while preserving the mandatory commit gate', async () => {
  const { api, id } = await ready('s2', { guard: false });
  await api.run(id); const task = await api.get(id);
  assert.equal(task.status, 'blocked'); assert.equal(task.final, null);
  assert.equal(task.events.filter(event => event.type === 'cart_fixed').length, 0);
});

test('mock receipt chain tampering is detected', async () => {
  const { api, id } = await ready('s1'); await api.run(id);
  api.task(id).events[1].payload.to = 'done';
  assert.deepEqual(await api.verify(id), { valid: false, broken_at: 2 });
});

test('origin search state and pricing helpers preserve passenger counts and flat extras', () => {
  assert.deepEqual(demo.searchState(), { from: 'Ludhiana', to: 'Delhi', date: '2026-10-25', passengers: 1 });
  const state = { ...demo.bookingState(), passengers: 3, insurance: true, meal: true, fee: true };
  assert.equal(demo.ticketPrice(state), 3000);
  assert.equal(demo.totalPrice(state), 3530);
  const params = demo.bookingParams(state);
  assert.equal(params.get('passengers'), '3');
  assert.equal(params.get('date'), '2026-10-25');
  assert.equal(params.get('from'), 'Ludhiana');
  assert.equal(params.get('to'), 'Delhi');
  assert.equal(demo.cartData(state).total, 3530);
  assert.equal(demo.tickets.t3.date, '2026-10-26');
});

test('the view escapes text and refuses decimal or string money', () => {
  assert.equal(esc('<script>'), '&lt;script&gt;');
  assert.equal(rupees(null), 'Unknown');
  for (const value of ['1000', 1.5, NaN, Infinity, true]) assert.throws(() => rupees(value));
});
