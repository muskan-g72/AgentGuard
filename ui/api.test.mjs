import test from 'node:test';
import assert from 'node:assert/strict';
import { TaskAPI } from './api.mjs';

test('task API sends the schema payload to the unified same-origin runtime', async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return Response.json({ task_id: 'task_1', draft_contract: {}, questions: [] });
  };
  try {
    await new TaskAPI().create({ sentence: 'Book a ticket', scenario: 's2', guard_enabled: true });
    assert.equal(calls[0].url, '/tasks');
    assert.deepEqual(JSON.parse(calls[0].options.body), { sentence: 'Book a ticket', scenario: 's2', guard_enabled: true });
    assert.equal(calls[0].options.headers.Authorization, undefined);
  } finally { globalThis.fetch = original; }
});

test('API failures stay failures and explain unsupported scenarios', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => Response.json({ detail: [{ msg: 'unsupported scenario' }] }, { status: 422 });
  try { await assert.rejects(new TaskAPI().create({}), /Mock replay/); }
  finally { globalThis.fetch = original; }
});

test('invalid JSON and invalid money never become successful task data', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response('<html>error</html>');
    await assert.rejects(new TaskAPI().get('a'), /unreadable/);
    globalThis.fetch = async () => Response.json({ cart: { total: '1000', items: [] } });
    await assert.rejects(new TaskAPI().get('a'), /rupee amount/);
  } finally { globalThis.fetch = original; }
});

test('the API forwards false receipt verification unchanged', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => Response.json({ valid: false, broken_at: 2 });
  try { assert.deepEqual(await new TaskAPI().verify('a'), { valid: false, broken_at: 2 }); }
  finally { globalThis.fetch = original; }
});

test('EventSource receives status events and can be closed on reset', () => {
  const original = globalThis.EventSource;
  let source;
  globalThis.EventSource = class {
    constructor(url) { this.url = url; this.callbacks = {}; source = this; }
    addEventListener(name, callback) { this.callbacks[name] = callback; }
    close() { this.closed = true; }
  };
  try {
    const received = [];
    const close = new TaskAPI().subscribe('task_1', value => received.push(value));
    assert.equal(source.url, '/tasks/task_1/events');
    source.callbacks.status({ data: '{"task_id":"task_1","status":"checking"}' });
    assert.deepEqual(received, [{ task_id: 'task_1', status: 'checking' }]);
    close(); assert.equal(source.closed, true);
  } finally { globalThis.EventSource = original; }
});
