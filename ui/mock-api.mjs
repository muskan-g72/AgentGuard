// Schema v2 fixtures only. This adapter simulates endpoints and must never be
// presented as a real booking, backend HMAC, or live TinyFish execution.
import { canonical, clone, delay, sha256 } from './format.mjs';

const transitions = {
  awaiting_answers: ['awaiting_confirmation'], awaiting_confirmation: ['staging'],
  staging: ['checking', 'failed'], checking: ['allowed', 'blocked', 'failed'],
  blocked: ['fixing', 'failed'], fixing: ['checking', 'failed'],
  allowed: ['committing'], committing: ['done', 'failed'], done: [], failed: []
};
const questionText = { refundable: 'Do you need a refundable ticket?', seat_confirmed: 'Do you need a confirmed seat?', baggage: 'Do you need baggage included?' };
const decision = (result, reasons, extra = {}) => ({ result, reasons, remove_item_ids: [], flags: [], differing_fields: [], ...extra });

export function fixtureDecision(contract, cart) {
  const reasons = [], unknown = [], differing = [];
  const extras = !contract.allow_extras ? cart.items.filter(item => item.type !== 'ticket') : [];
  for (const item of extras) reasons.push(`${item.type === 'insurance' ? 'Travel insurance' : item.type === 'meal' ? 'Priority meal' : 'Convenience fee'} costs Rs ${item.price} and was not authorized.`);
  for (const ticket of cart.items.filter(item => item.type === 'ticket')) {
    if (!ticket.route || !ticket.date) unknown.push('The ticket route or date is unknown.');
    else if (canonical(ticket.route) !== canonical(contract.route) || ticket.date !== contract.date) { reasons.push('The ticket route or date differs from your contract.'); differing.push('date'); }
  }
  if (cart.total === null) unknown.push('The cart total is unknown.');
  else {
    if (cart.total > contract.max_total) reasons.push(`Total Rs ${cart.total} is over your Rs ${contract.max_total} budget.`);
    if (cart.total !== cart.items.reduce((sum, item) => sum + item.price, 0)) reasons.push('The cart total differs from its items.');
  }
  if (cart.passengers === null) unknown.push('The passenger count is unknown.');
  else if (cart.passengers !== contract.quantity) reasons.push('The passenger count differs from your contract.');
  for (const [key, required] of Object.entries(contract.requirements)) {
    if (required === null) continue;
    if (cart.attributes[key] === null) unknown.push(`${key} is unknown.`);
    else if (cart.attributes[key] !== required) { reasons.push(`This ticket does not match your ${key.replaceAll('_', ' ')} requirement.`); differing.push('attributes.' + key); }
  }
  if (cart.hidden_text.length) unknown.push('Hidden page instructions are trying to override your booking rules.');
  const extra = { remove_item_ids: extras.map(item => item.id), differing_fields: differing,
    flags: cart.hidden_text.length ? ['hidden_text'] : [] };
  if (reasons.length) return decision('block', reasons.concat(unknown), extra);
  if (unknown.length) return decision('ask', unknown, extra);
  return decision('allow', ['The cart matches the booking you authorized.']);
}

export class MockAPI {
  mode = 'mock';
  constructor({ pace = 750 } = {}) { this.tasks = new Map(); this.listeners = new Map(); this.pace = pace; }
  async health() { return { replay: true, tinyfish_configured: false, db_ok: true }; }
  async create(body) {
    const id = 'mock_' + crypto.randomUUID().replaceAll('-', '');
    const contract = { route: { from: 'Ludhiana', to: 'Delhi' }, date: '2026-10-25', quantity: 1,
      max_total: 1000, allow_extras: false, requirements: { refundable: null, seat_confirmed: null, baggage: null }, source: 'fallback' };
    const questions = Object.entries(questionText).map(([key, text]) => ({ key, text, options: ['yes', 'no', "don't care"] }));
    const task = { task_id: id, sentence: body.sentence, scenario: body.scenario, guard_enabled: body.guard_enabled,
      draft_contract: contract, contract: null, questions, status: 'awaiting_answers', decision_history: [],
      cart: null, events: [], final: null, signature: '0'.repeat(64), allowed_cart_hash: null, running: false };
    this.tasks.set(id, task);
    await this.event(task, 'task_created', { task_id: id, draft_contract: clone(contract) });
    await this.event(task, 'status', { from: null, to: task.status });
    return { task_id: id, draft_contract: clone(contract), questions: clone(questions) };
  }
  task(id) { const task = this.tasks.get(id); if (!task) throw new Error('This mock task no longer exists. Reset to begin again.'); return task; }
  async event(task, type, payload) {
    const event = { id: task.events.length + 1, ts: new Date().toISOString(), type, payload: clone(payload) };
    const previous = task.events.at(-1)?.hash || '0'.repeat(64);
    const hash = await sha256(previous + canonical(event));
    task.events.push({ ...event, prev_hash: previous, hash });
    if (type === 'status') for (const callback of this.listeners.get(task.task_id) || []) callback({ task_id: task.task_id, status: payload.to });
  }
  async move(task, target) {
    if (!transitions[task.status]?.includes(target)) { await this.event(task, 'transition_rejected', { from: task.status, to: target }); throw new Error('The mock task rejected an invalid transition.'); }
    const previous = task.status; task.status = target;
    await this.event(task, 'status', { from: previous, to: target });
  }
  async answers(id, answers) {
    const task = this.task(id);
    if (task.status !== 'awaiting_answers' || Object.keys(answers).length !== task.questions.length
      || task.questions.some(question => !question.options.includes(answers[question.key]))) throw new Error('Please answer each question.');
    for (const [key, value] of Object.entries(answers)) task.draft_contract.requirements[key] = value === "don't care" ? null : value === 'yes';
    await this.event(task, 'answers_recorded', { answers }); await this.move(task, 'awaiting_confirmation');
    return { contract: clone(task.draft_contract) };
  }
  async confirm(id, contract) {
    const task = this.task(id); if (task.status !== 'awaiting_confirmation') throw new Error('Review the contract first.');
    task.contract = clone(contract || task.draft_contract);
    await this.event(task, 'contract_confirmed', { contract: task.contract }); await this.move(task, 'staging');
    return { status: task.status };
  }
  async get(id) { return clone(this.task(id)); }
  subscribe(id, callback) {
    const listeners = this.listeners.get(id) || new Set(); listeners.add(callback); this.listeners.set(id, listeners);
    return () => { listeners.delete(callback); };
  }
  async recordDecision(task, value, phase) {
    const hash = await sha256(canonical(task.cart));
    task.decision_history.push({ ...value, phase, cart_hash: hash });
    task.allowed_cart_hash = value.result === 'allow' ? hash : null;
    await this.event(task, 'decision', task.decision_history.at(-1));
  }
  async run(id, { signal } = {}) {
    const task = this.task(id);
    if (task.status !== 'staging' || task.running) throw new Error('A task can run only once.');
    task.running = true;
    try {
      await delay(this.pace, signal);
      task.cart = clone(globalThis.AgentGuardDemo.cartData(globalThis.AgentGuardDemo.scenarioState(task.scenario)));
      await this.event(task, 'cart_staged', { cart: task.cart }); await this.move(task, 'checking');
      await delay(this.pace, signal);
      let result = fixtureDecision(task.contract, task.cart);
      await this.recordDecision(task, result, 'cart');
      if (result.result !== 'allow') {
        await this.move(task, 'blocked'); await delay(this.pace, signal);
        const optional = result.remove_item_ids.length && result.remove_item_ids.every(id => ['x1', 'm1'].includes(id));
        if (result.result === 'block' && task.guard_enabled && optional) {
          await this.move(task, 'fixing'); await delay(this.pace, signal);
          task.cart.items = task.cart.items.filter(item => !result.remove_item_ids.includes(item.id));
          task.cart.total = task.cart.items.reduce((sum, item) => sum + item.price, 0);
          await this.event(task, 'cart_fixed', { cart: task.cart, remove_item_ids: result.remove_item_ids });
          await this.move(task, 'checking'); await delay(this.pace, signal);
          result = fixtureDecision(task.contract, task.cart); await this.recordDecision(task, result, 'cart');
          if (result.result !== 'allow') { await this.move(task, 'blocked'); return clone(task); }
        } else return clone(task);
      }
      await delay(this.pace, signal);
      let request = { cart_id: task.cart.cart_id, items: task.cart.items.map(({ id, price }) => ({ id, price })), total: task.cart.total, fields: {} };
      if (task.scenario === 's7') request = globalThis.AgentGuardDemo.buildOrder(globalThis.AgentGuardDemo.scenarioState('s7'));
      task.order_request = clone(request);
      await this.event(task, 'request_captured', { order_request: request });
      if (request.total !== task.cart.total || canonical(request.items) !== canonical(task.cart.items.map(({ id, price }) => ({ id, price })))) {
        result = decision('block', ['The screen shows Rs 1000, but the outgoing order adds Rs 250 insurance and a Rs 250 fee.', 'The actual Rs 1500 request is over your Rs 1000 budget.'], { differing_fields: ['items', 'total'] });
        await this.recordDecision(task, result, 'request'); await this.move(task, 'blocked'); return clone(task);
      }
      result = decision('allow', ['The actual outgoing request matches your authorized cart.']);
      await this.recordDecision(task, result, 'request'); await this.move(task, 'allowed');
      await delay(this.pace, signal);
      if (task.status !== 'allowed' || task.decision_history.at(-1).result !== 'allow'
        || await sha256(canonical(task.cart)) !== task.allowed_cart_hash) throw new Error('The mock commit gate rejected the cart.');
      await this.move(task, 'committing'); await delay(this.pace, signal);
      task.final = { order_id: 'order_' + id, total: request.total };
      await this.event(task, 'order_committed', { final: task.final }); await this.move(task, 'done');
      return clone(task);
    } catch (error) {
      if (transitions[task.status]?.includes('failed')) await this.move(task, 'failed');
      throw error;
    } finally { task.running = false; }
  }
  async receipt(id) {
    const task = this.task(id);
    return { task_id: id, contract: clone(task.contract || task.draft_contract), events: clone(task.events),
      final: clone(task.final || {}), signature: task.signature };
  }
  async verify(id) {
    // This models GET /receipt/verify. There is deliberately no HMAC signing key
    // in frontend code. The badge explicitly calls this mock verification.
    let previous = '0'.repeat(64);
    for (const event of this.task(id).events) {
      const body = { id: event.id, ts: event.ts, type: event.type, payload: event.payload };
      if (event.prev_hash !== previous || event.hash !== await sha256(previous + canonical(body))) return { valid: false, broken_at: event.id };
      previous = event.hash;
    }
    return { valid: true, broken_at: null };
  }
}
