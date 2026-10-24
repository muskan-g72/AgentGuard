import { TaskAPI } from './api.mjs';
import { MockAPI } from './mock-api.mjs';
import { assertTaskMoney, canonical, clone, delay, esc, historyOf, itemName, latestDecision, prefName, prefValue, rupees } from './format.mjs';

const demo = globalThis.AgentGuardDemo;
const defaultSentence = 'Book one Ludhiana to Delhi train ticket for 25 October 2026, under Rs 1,000. No extras.';
const requestedScenario = new URLSearchParams(location.search).get('scenario');
const workspace = document.getElementById('workspace');
const state = { step: 0, maxStep: 0, mode: new URLSearchParams(location.search).get('api') === '1' ? 'api' : 'mock',
  api: null, health: null, busy: false, running: false, guided: false, generation: 0,
  form: { sentence: defaultSentence, scenario: Object.hasOwn(demo.scenarios, requestedScenario) ? requestedScenario : 's2', guard_enabled: true },
  draft: null, taskId: null, questions: [], answers: {}, reviewed: false, confirmed: false,
  task: null, receipt: null, verification: null, receiptError: null, retry: null,
  unsubscribe: null, timer: null, controller: null, refreshing: false };

const statusNames = {
  awaiting_answers: ['Questions ready', 'Your preferences set the boundaries.'],
  awaiting_confirmation: ['Contract ready', 'Nothing runs until you confirm.'],
  staging: ['Staging the cart', 'The agent is preparing your booking.'],
  checking: ['Checking the booking', 'Compare the cart and outgoing request.'],
  blocked: ['Order paused', 'A violation or unknown fact stopped progress.'],
  fixing: ['Removing the extras', 'Repair the cart, then check again.'],
  allowed: ['Order authorized', 'The checked cart matches your rules.'],
  committing: ['Placing the order', 'Only the authorized request may proceed.'],
  done: ['Booking complete', 'The simulated order is recorded.'],
  failed: ['Run stopped', 'No successful order is being assumed.']
};
const terminal = task => task && (['done', 'failed'].includes(task.status) || (task.status === 'blocked' && !task.running));
const sourceBadge = () => `<span class="badge ${state.draft?.source === 'parsed' ? 'parsed' : ''}">${esc(state.draft?.source || 'fallback')}</span>`;

function notice(message = '') { const box = document.getElementById('notice'); box.textContent = message; box.hidden = !message; }
function clearError() { document.getElementById('error').hidden = true; state.retry = null; }
function showError(error, retry) {
  const message = error instanceof Error ? error.message : String(error);
  document.getElementById('error-text').textContent = message;
  document.getElementById('error').hidden = false; state.retry = retry || null;
  document.getElementById('retry').hidden = !retry;
}
function controls() {
  workspace.setAttribute('aria-busy', String(state.busy));
  document.getElementById('run-demo').disabled = state.busy || state.running;
  document.getElementById('data-source').disabled = state.busy || state.running;
  document.getElementById('reset').disabled = state.mode === 'api' && state.running;
  document.querySelectorAll('[data-step]').forEach(button => {
    const step = Number(button.dataset.step);
    button.disabled = step > state.maxStep || state.busy || state.running || (step < 2 && state.confirmed);
    button.classList.toggle('active', step === state.step); button.classList.toggle('complete', step < state.step);
    if (step === state.step) button.setAttribute('aria-current', 'step'); else button.removeAttribute('aria-current');
  });
}
function showStep(step, focus = true) {
  state.step = step; state.maxStep = Math.max(state.maxStep, step); render();
  if (focus) {
    const heading = workspace.querySelector('h2');
    if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
    workspace.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' });
  }
}
function sideBrief() {
  return `<aside class="side-card"><p class="section-index">THE BRIEF, AT A GLANCE</p><span class="number">${rupees(state.draft?.max_total ?? 1000).replace('Rs ', '₹')}</span>
    <h3>Your maximum. Not a suggestion.</h3><p>One ticket. The right date.<br>No extras you didn’t ask for.</p><hr class="side-divider">
    <div class="side-point"><span>01</span><span>Make the missing preferences explicit.</span></div>
    <div class="side-point"><span>02</span><span>Check the actual outgoing order.</span></div>
    <div class="side-point"><span>03</span><span>Keep a receipt with a verifiable trail.</span></div>
    <hr class="side-divider"><p style="font-size:11px">${state.mode === 'mock' ? 'This is a mock replay. It does not contact a booking agent or make a purchase.' : 'This view uses the connected task API. Every payment is simulated.'}</p></aside>`;
}
function inputView() {
  return `<div class="work-grid"><section class="panel"><div class="panel-heading"><div><p class="section-index">01 / SET THE BRIEF</p><h2>What should your agent do?</h2><p class="subtitle">You set the task. AgentGuard protects the boundaries.</p></div><span class="scenario-chip">START HERE</span></div>
    <form id="brief-form"><label class="field-label" for="sentence">Your booking request</label><textarea id="sentence" name="sentence" maxlength="4000" required>${esc(state.form.sentence)}</textarea>
    <p class="field-note">The demo starts with a Rs 1,000 train booking. You’ll review the draft before anything runs.</p>
    <div class="two-col"><div><label class="field-label" for="scenario">Try a scenario</label><select id="scenario" name="scenario">${Object.entries(demo.scenarios).map(([id, value]) => `<option value="${id}" ${id === state.form.scenario ? 'selected' : ''}>${id.toUpperCase()} · ${esc(value.name)}</option>`).join('')}</select><p id="scenario-note" class="scenario-note">${esc(demo.scenarios[state.form.scenario].description)}</p></div>
    <div><label class="field-label" for="guard-toggle">The bodyguard</label><div class="guard-box"><strong id="guard-label">Guard ${state.form.guard_enabled ? 'ON' : 'OFF'}</strong><button id="guard-toggle" class="switch" type="button" role="switch" aria-checked="${state.form.guard_enabled}" aria-label="Enable automatic guard repairs"></button></div><p id="guard-note" class="scenario-note">${state.form.guard_enabled ? 'Catch unauthorized extras, remove them, and check again.' : 'Automatic repairs are off. The final commit gate still applies.'}</p></div></div>
    <div class="form-bottom"><p class="micro">Simulated booking · No payment details needed<br>Want the full story? Press <strong>Run demo</strong> above.</p><button id="create-task" class="button dark" type="submit" ${state.busy ? 'disabled' : ''}>${state.busy ? '<span class="spinner"></span>Preparing…' : 'Set my boundaries <span aria-hidden="true">→</span>'}</button></div></form>
    </section>${sideBrief()}</div>`;
}
function contractDetails() {
  const contract = state.draft;
  return `<dl class="contract-grid"><div><dt>Journey</dt><dd>${esc(contract.route.from)} → ${esc(contract.route.to)}</dd></div><div><dt>Travel date</dt><dd>${esc(contract.date)}</dd></div><div><dt>Passengers</dt><dd>${esc(contract.quantity)} adult${contract.quantity === 1 ? '' : 's'}</dd></div><div><dt>Maximum total</dt><dd>${rupees(contract.max_total)}</dd></div><div><dt>Extras</dt><dd>${contract.allow_extras ? 'Allowed' : 'Not authorized'}</dd></div><div><dt>Guard repairs</dt><dd>${state.form.guard_enabled ? 'Enabled' : 'Disabled'}</dd></div></dl><div class="contract-pref">${Object.entries(contract.requirements).map(([key, value]) => `<span class="pref"><b>${prefName(key)}</b> · ${prefValue(value)}</span>`).join('')}</div>`;
}
function questionView() {
  const ready = state.questions.every(question => Object.hasOwn(state.answers, question.key));
  if (state.reviewed) return `<div class="work-grid"><section class="panel"><div class="panel-heading"><div><p class="section-index">02 / YOUR AUTHORIZATION</p><h2>Your booking. Your boundaries.</h2><p class="subtitle">Review this contract. Nothing runs until you confirm it.</p></div>${sourceBadge()}</div>
    ${contractDetails()}<p class="field-note" style="margin-top:20px">${state.draft.source === 'fallback' ? 'A fixed demo draft was used. Check that its route, date, and budget match what you want.' : 'This draft was parsed from your request. Check its details before you confirm.'}</p>
    <div class="form-bottom"><button id="edit-answers" class="button subtle" type="button" ${state.busy ? 'disabled' : ''}>← Change the brief</button><button id="confirm-contract" class="button dark" type="button" ${state.busy ? 'disabled' : ''}>${state.busy ? '<span class="spinner"></span>Confirming…' : 'Confirm contract & run →'}</button></div></section>${sideBrief()}</div>`;
  return `<div class="work-grid"><section class="panel"><div class="panel-heading"><div><p class="section-index">02 / MAKE IT CLEAR</p><h2>A few things you left unsaid.</h2><p class="subtitle">Your agent shouldn’t have to guess what matters.</p></div>${sourceBadge()}</div>
    <div id="questions">${state.questions.map((question, index) => `<section class="question"><h3 id="question-${index}">${esc(question.text)}</h3><div class="answers" role="radiogroup" aria-labelledby="question-${index}">${question.options.map(option => `<button class="answer" type="button" role="radio" aria-checked="${state.answers[question.key] === option}" data-key="${esc(question.key)}" data-value="${esc(option)}" ${state.busy ? 'disabled' : ''}>${esc(option === "don't care" ? 'Don’t care' : option.charAt(0).toUpperCase() + option.slice(1))}</button>`).join('')}</div></section>`).join('')}</div>
    <div class="form-bottom"><p class="micro"><strong id="answered-count">${Object.keys(state.answers).length} of ${state.questions.length}</strong> answered<br>“Don’t care” leaves that preference unrestricted.</p><button id="review-contract" class="button dark" type="button" ${!ready || state.busy ? 'disabled' : ''}>${state.busy ? '<span class="spinner"></span>Saving…' : 'Review my contract →'}</button></div></section>${sideBrief()}</div>`;
}
function firstCart(task = state.task) { return task?.events?.find(event => event.type === 'cart_staged')?.payload?.cart || task?.cart || null; }
function removedItems(task = state.task) {
  const removed = new Set((task?.events || []).filter(event => event.type === 'cart_fixed').flatMap(event => event.payload.remove_item_ids || []));
  return (firstCart(task)?.items || []).filter(item => removed.has(item.id));
}
function cartView() {
  const cart = state.task?.cart || firstCart();
  const contents = cart ? `<div>${cart.items.map(item => cartRow(item, false)).join('')}${removedItems().map(item => cartRow(item, true)).join('')}</div><div class="cart-total"><span>${state.task?.status === 'done' ? 'Final cart total' : 'Staged cart total'}</span><strong>${rupees(cart.total)}</strong></div><div class="cart-attributes">${Object.entries(cart.attributes || {}).map(([key, value]) => `<span>${prefName(key)}: ${value === null ? 'Unknown' : value ? 'Yes' : 'No'}</span>`).join('')}<span>Passengers: ${cart.passengers ?? 'Unknown'}</span></div>` : '<div class="empty-state"><span class="spinner"></span>Waiting for the agent’s cart.<br>Nothing has been purchased.</div>';
  return `<section class="panel"><div class="panel-heading"><div><p class="section-index">WHAT THE AGENT STAGED</p><h2>The booking, under review.</h2></div><span class="scenario-chip">${esc(state.form.scenario.toUpperCase())}</span></div>${contents}</section>`;
}
function cartRow(item, removed) {
  return `<div class="cart-row ${removed ? 'removed' : ''}" data-item-id="${esc(item.id)}"><span class="cart-icon" aria-hidden="true">${removed ? '−' : item.type === 'ticket' ? '↗' : '+'}</span><div><strong>${esc(itemName(item))}${removed ? '<span class="removed-tag">Removed</span>' : ''}</strong><small>${item.type === 'ticket' ? `${esc(item.route?.from || 'Unknown')} → ${esc(item.route?.to || 'Unknown')} · ${esc(item.date || 'Date unknown')}` : removed ? 'Not authorized by your contract' : 'Added at checkout'}</small></div><span class="cart-price">${rupees(item.price)}</span></div>`;
}
function decisionView() {
  const value = latestDecision(state.task);
  if (state.task?.status === 'failed') return `<section class="decision-card block" role="status"><div class="decision-top"><div class="decision-label">× RUN FAILED</div><span class="decision-meta">NO CONFIRMED PURCHASE</span></div><p class="subtitle">The run stopped before a successful order was recorded. Earlier passed checks do not mean a purchase completed.</p></section>`;
  return `<section class="decision-card ${value?.result || 'pending'}" aria-live="polite" aria-atomic="true"><div class="decision-top"><div class="decision-label">${value ? ({ allow: '✓ ALLOW', block: '× BLOCK', ask: '? ASK' }[value.result]) : '<span class="spinner"></span>Guard is watching'}</div><span class="decision-meta">${value?.phase === 'request' ? 'OUTGOING REQUEST' : 'CART CHECK'}</span></div>
    ${value ? `<ul>${value.reasons.map(reason => `<li>${esc(reason)}</li>`).join('')}</ul>` : '<p class="subtitle">The cart must be checked before the agent can place an order.</p>'}
    ${historyOf(state.task).length > 1 ? `<div class="decision-history">${historyOf(state.task).map((entry, index) => `<span class="history-chip ${entry.result}">${index + 1}. ${entry.result.toUpperCase()} · ${entry.phase === 'request' ? 'request' : 'cart'}</span>`).join('')}</div>` : ''}</section>`;
}
function timelineView() {
  const events = (state.task?.events || []).filter(event => event.type === 'status' && !['awaiting_answers', 'awaiting_confirmation'].includes(event.payload.to));
  if (!events.length) events.push({ ts: new Date().toISOString(), payload: { to: 'staging' } });
  return `<aside class="side-card"><p class="section-index">LIVE STATUS</p><h3 id="live-status" aria-live="polite">${esc(statusNames[state.task?.status || 'staging']?.[0] || 'Run in progress')}</h3><ol class="timeline">${events.map((event, index) => {
    const [name, detail] = statusNames[event.payload.to] || ['Updating', 'Reading the next status.'];
    return `<li class="${index === events.length - 1 ? 'current' : ''}"><span class="timeline-marker">${index === events.length - 1 && state.running ? '•' : '✓'}</span><div><strong>${esc(name)}</strong><small>${esc(detail)}</small><span class="time">${new Date(event.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span></div></li>`;
  }).join('')}</ol>${state.mode === 'mock' ? '<hr class="side-divider"><p style="font-size:10px">Mock replay · these statuses simulate the task API. No real order is sent.</p>' : ''}</aside>`;
}
function requestView() {
  if (!state.task?.order_request || latestDecision(state.task)?.phase !== 'request' || latestDecision(state.task)?.result === 'allow') return '';
  return `<div class="request-detail"><strong>A clean screen hid a different order.</strong>Screen total: ${rupees(state.task.cart.total)}. Captured request: ${rupees(state.task.order_request.total)}.<code>${esc(JSON.stringify(state.task.order_request, null, 2))}</code></div>`;
}
function runView() {
  const finished = !state.running && state.task && ['done', 'blocked', 'failed'].includes(state.task.status);
  return `<div class="run-grid"><div class="run-stack">${decisionView()}${cartView()}${requestView()}${finished ? `<div class="form-bottom" style="margin-top:0;padding-top:8px;border:0"><p class="micro">${state.task.status === 'done' ? 'The simulated purchase is complete.' : 'The run stopped. No purchase was completed.'}<br>See exactly what happened in the receipt.</p><button id="view-receipt" type="button" class="button dark">See the proof receipt →</button></div>` : '<p class="micro">You’re watching the booking as it happens. No real payment will be taken.</p>'}</div>${timelineView()}</div>`;
}
function receiptView() {
  if (!state.receipt) return `<section class="panel"><h2>Preparing your proof receipt.</h2><div class="empty-state"><span class="spinner"></span>Reading the audit trail and verification result.</div></section>`;
  const receipt = state.receipt;
  const attempted = firstCart();
  const stopped = removedItems();
  const issues = historyOf(state.task).filter(entry => entry.result !== 'allow');
  const verified = state.verification?.valid === true;
  const final = receipt.final;
  const complete = final && typeof final.order_id === 'string' && Number.isSafeInteger(final.total);
  const attemptedRequest = state.task.order_request;
  const attemptItems = state.form.scenario === 's7' && attemptedRequest ? attemptedRequest.items : attempted?.items || [];
  const guardOffAmount = state.form.scenario === 's7' ? 1500 : attempted?.total;
  return `<div class="work-grid"><div><article class="receipt-paper" aria-label="Proof receipt"><header class="receipt-header"><div><p class="section-index">04 / THE PROOF IS YOURS</p><h2>Your guard kept a record.</h2><p class="receipt-number">${esc(receipt.task_id.slice(0, 22))}</p></div><span id="verified-badge" class="verify-badge ${verified ? '' : 'unverified'}">${verified ? '✓ ' + (state.mode === 'mock' ? 'Verified · mock' : 'Verified') : '? Not verified'}</span></header>
    <section class="receipt-section"><h3>What you asked</h3><p>${esc(state.form.sentence)}</p><p class="micro" style="margin-top:10px">Confirmed: ${esc(receipt.contract.route.from)} → ${esc(receipt.contract.route.to)} · ${esc(receipt.contract.date)} · max ${rupees(receipt.contract.max_total)} · ${receipt.contract.allow_extras ? 'extras allowed' : 'no extras'}</p></section>
    <section class="receipt-section"><h3>What the agent tried</h3><ul class="receipt-list">${attemptItems.map(item => `<li><span>${esc(itemName(item))}</span><strong>${rupees(item.price)}</strong></li>`).join('') || '<li>The agent did not reach a readable cart.</li>'}</ul></section>
    <section class="receipt-section"><h3>What we stopped</h3>${stopped.length ? `<ul class="receipt-list">${stopped.map(item => `<li class="stopped"><span>− ${esc(itemName(item))} removed</span><strong>${rupees(item.price)}</strong></li>`).join('')}</ul>` : `<p>${esc(issues.length ? issues.at(-1).reasons.join(' ') : 'No violations. The booking matched your authorization.')}</p>`}${state.form.scenario === 's7' ? '<p class="micro" style="margin-top:10px">The request changed at click time. The outgoing order was blocked before submission.</p>' : ''}</section>
    <section class="receipt-section"><h3>What was bought</h3><p>${complete ? `${esc(state.task.cart.items.filter(item => item.type === 'ticket').length)} train ticket${state.task.cart.items.filter(item => item.type === 'ticket').length === 1 ? '' : 's'} · ${esc(receipt.contract.route.from)} → ${esc(receipt.contract.route.to)}` : 'Nothing. The order was stopped.'}</p>${complete ? `<p class="receipt-number" style="margin-top:9px">${esc(final.order_id)}</p>` : ''}</section>
    <div class="receipt-total"><div><span>${complete ? 'Final authorized purchase' : 'No completed purchase'}</span><p>${state.mode === 'mock' ? 'Mock order · no real payment' : 'Simulated payment only'}</p></div><strong>${complete ? rupees(final.total) : 'Rs 0'}</strong></div>
    <div class="receipt-footnote">${state.mode === 'mock' ? 'Mock verification checks this replay’s event chain. Its signature is a fixture, not a backend HMAC.' : verified ? 'Verification returned valid from /receipt/verify. HMAC signatures are demo-grade, not production security.' : 'Receipt verification did not return valid. This receipt is not being presented as verified.'}</div></article>
    <section class="comparison"><h3>Same scenario. Different boundaries.</h3><p class="subtitle">${esc(demo.scenarios[state.form.scenario].name)} · Guard OFF vs ON</p><div class="comparison-grid"><div class="compare-card"><h4>Guard OFF · ${state.form.guard_enabled ? 'illustration' : 'this run'}</h4><p class="compare-amount">${rupees(guardOffAmount)}</p><p>${state.form.guard_enabled ? 'What the agent would request without intervention. This is a counterfactual, not a second purchase.' : complete ? 'The mandatory checks passed. No automatic repairs were made.' : 'Attempted amount. Repairs were disabled; the final gate still blocked the order.'}</p></div><div class="compare-card on"><h4>Guard ON · ${state.form.guard_enabled ? 'this run' : 'illustration'}</h4><p class="compare-amount">${state.form.guard_enabled ? complete ? rupees(final.total) : 'Stopped' : 'Re-check'}</p><p>${state.form.guard_enabled ? complete ? stopped.length ? `${stopped.length} unauthorized extras removed before the order.` : 'Only the authorized booking went through.' : 'No purchase: a violation or unknown fact still needs attention.' : 'Guard ON would attempt permitted repairs and re-check the result. No second run was made.'}</p></div></div></section>
    <div class="receipt-actions"><button id="print-receipt" class="button outline" type="button">Print receipt ↗</button><button id="download-receipt" class="button outline" type="button">Download JSON ↓</button><button id="new-run" class="button dark" type="button">Try another scenario →</button></div>
    ${state.receiptError ? `<p class="proof-note">${esc(state.receiptError)} <button id="verify-again" type="button" class="button small outline">Verify again</button></p>` : ''}</div>${sideBrief()}</div>`;
}
function render() {
  workspace.innerHTML = [inputView, questionView, runView, receiptView][state.step]();
  controls(); bindView();
}
function bindView() {
  const on = (id, name, callback) => document.getElementById(id)?.addEventListener(name, callback);
  on('sentence', 'input', event => { state.form.sentence = event.target.value; });
  on('scenario', 'change', event => { state.form.scenario = event.target.value; document.getElementById('scenario-note').textContent = demo.scenarios[state.form.scenario].description; });
  on('guard-toggle', 'click', event => {
    state.form.guard_enabled = !state.form.guard_enabled;
    event.currentTarget.setAttribute('aria-checked', String(state.form.guard_enabled));
    document.getElementById('guard-label').textContent = 'Guard ' + (state.form.guard_enabled ? 'ON' : 'OFF');
    document.getElementById('guard-note').textContent = state.form.guard_enabled ? 'Catch unauthorized extras, remove them, and check again.' : 'Automatic repairs are off. The final commit gate still applies.';
  });
  on('brief-form', 'submit', event => { event.preventDefault(); createTask(); });
  document.querySelectorAll('.answer').forEach(button => button.addEventListener('click', () => {
    state.answers[button.dataset.key] = button.dataset.value;
    const group = button.closest('.answers'); group.querySelectorAll('button').forEach(option => option.setAttribute('aria-checked', String(option === button)));
    document.getElementById('answered-count').textContent = `${Object.keys(state.answers).length} of ${state.questions.length}`;
    document.getElementById('review-contract').disabled = !state.questions.every(question => Object.hasOwn(state.answers, question.key));
  }));
  document.querySelectorAll('.answers').forEach(group => group.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    const buttons = Array.from(group.querySelectorAll('button:not(:disabled)'));
    if (!buttons.length) return;
    event.preventDefault();
    const index = buttons.indexOf(document.activeElement);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1
      : (index + (event.key === 'ArrowLeft' ? -1 : 1) + buttons.length) % buttons.length;
    buttons[next].click(); buttons[next].focus();
  }));
  on('review-contract', 'click', () => reviewContract());
  on('edit-answers', 'click', () => {
    // Submitted answers cannot be resubmitted after awaiting_confirmation. Start
    // a fresh draft to revise them instead of issuing an invalid transition.
    notice('Start a fresh brief to change submitted answers. No booking has run yet.'); reset(false);
  });
  on('confirm-contract', 'click', () => startRun());
  on('view-receipt', 'click', () => loadReceipt());
  on('print-receipt', 'click', () => window.print());
  on('download-receipt', 'click', () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(state.receipt, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = `agentguard-${state.taskId}.json`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  on('new-run', 'click', () => reset());
  on('verify-again', 'click', () => loadReceipt());
}
async function createTask(guided = false) {
  if (state.busy || !state.form.sentence.trim()) return;
  const generation = state.generation; clearError(); state.busy = true; state.guided = guided; render();
  try {
    const response = await state.api.create(clone(state.form));
    if (generation !== state.generation) return;
    if (!response.task_id || !response.draft_contract || !Array.isArray(response.questions) || response.questions.length > 3) throw new Error('The API returned an invalid draft. No run was started.');
    rupees(response.draft_contract.max_total);
    state.taskId = response.task_id; state.draft = response.draft_contract; state.questions = response.questions;
    state.answers = {}; state.reviewed = !response.questions.length; state.busy = false; showStep(1);
    if (guided) {
      notice('Guided s2 demo: leave preferences unrestricted, review the Rs 1,000 contract, then watch the guard.');
      for (const question of state.questions) { await delay(300, state.controller.signal); if (generation !== state.generation) return; state.answers[question.key] = "don't care"; render(); }
      await delay(400, state.controller.signal);
      if (state.questions.length) await reviewContract(true);
      const expected = state.draft.route.from === 'Ludhiana' && state.draft.route.to === 'Delhi' && state.draft.date === '2026-10-25' && state.draft.quantity === 1 && state.draft.max_total === 1000 && state.draft.allow_extras === false;
      if (!expected) { notice('The returned draft differs from the guided demo. Review it and confirm only if it is correct.'); return; }
      await delay(900, state.controller.signal);
      if (generation === state.generation) await startRun();
    }
  } catch (error) { if (generation === state.generation && error.name !== 'AbortError') showError(error, () => createTask(guided)); }
  finally { if (generation === state.generation) { state.busy = false; controls(); if (state.step === 0) render(); } }
}
async function reviewContract(guided = false) {
  if (state.busy) return;
  state.busy = true; clearError(); render(); const generation = state.generation;
  try {
    const response = await state.api.answers(state.taskId, clone(state.answers));
    if (generation !== state.generation) return;
    state.draft = response.contract; rupees(state.draft.max_total); state.reviewed = true;
  } catch (error) { if (generation === state.generation) { showError(error, () => reviewContract(guided)); if (guided) throw error; } }
  finally { if (generation === state.generation) { state.busy = false; render(); } }
}
async function refreshTask() {
  if (state.refreshing || !state.taskId) return;
  const generation = state.generation, id = state.taskId; state.refreshing = true;
  try {
    const task = await state.api.get(id);
    if (generation !== state.generation) return;
    assertTaskMoney(task);
    if ((task.events?.at(-1)?.id || 0) < (state.task?.events?.at(-1)?.id || 0)) return;
    const changed = canonical(task) !== canonical(state.task); state.task = task;
    if (changed && state.step === 2) render();
  } catch (error) { if (generation === state.generation) notice(error.message); }
  finally { if (generation === state.generation) state.refreshing = false; }
}
function stopWatching() { state.unsubscribe?.(); state.unsubscribe = null; clearInterval(state.timer); state.timer = null; }
async function startRun() {
  if (state.busy || state.running) return;
  const generation = state.generation; clearError(); state.busy = true; render();
  try {
    await state.api.confirm(state.taskId, clone(state.draft));
    if (generation !== state.generation) return;
    state.confirmed = true; state.running = true; state.busy = false; state.task = await state.api.get(state.taskId); showStep(2);
    notice(state.mode === 'mock' ? 'Mock replay is running. Watch the first block, the repair, and the final request check.' : 'Task API connected. Status changes arrive through EventSource; polling keeps the view current.');
    state.unsubscribe = state.api.subscribe(state.taskId, () => refreshTask(), error => { if (state.running) notice(error.message); });
    state.timer = setInterval(refreshTask, 1000);
    await state.api.run(state.taskId, { signal: state.controller.signal });
    if (generation !== state.generation) return;
    const completedTask = assertTaskMoney(await state.api.get(state.taskId));
    if (generation !== state.generation) return;
    state.task = completedTask;
    state.running = false; stopWatching(); notice(); render();
    if (state.guided) { await delay(800, state.controller.signal); if (generation === state.generation) await loadReceipt(); }
  } catch (error) {
    if (generation !== state.generation || error.name === 'AbortError') return;
    state.running = false; stopWatching();
    if (state.confirmed) {
      await refreshTask(); state.step = 2;
      showError(new Error(error.message + ' Refresh the task to check its outcome; the order will not be submitted again.'), recoverTask);
    } else showError(error, recoverTask);
    render();
  } finally { if (generation === state.generation) { state.busy = false; controls(); if (state.step === 1) render(); } }
}
async function recoverTask() {
  clearError(); await refreshTask();
  if (!state.task) { showError(new Error('The task outcome is unknown. Check the API connection before starting another booking.'), recoverTask); return; }
  if (terminal(state.task)) { state.running = false; state.step = 2; render(); return; }
  notice(`Current status: ${statusNames[state.task.status]?.[0] || state.task.status}. The original task is still being tracked. It will not be submitted again.`);
  if (!state.timer) state.timer = setInterval(async () => { await refreshTask(); if (terminal(state.task)) { stopWatching(); state.running = false; render(); } }, 1200);
}
async function loadReceipt() {
  const generation = state.generation; clearError(); state.receiptError = null; showStep(3); state.busy = true; controls();
  try {
    const receipt = await state.api.receipt(state.taskId);
    if (generation !== state.generation) return;
    state.receipt = receipt;
    rupees(state.receipt.contract.max_total);
    if (state.receipt.final?.total !== undefined) rupees(state.receipt.final.total);
    try {
      state.verification = await state.api.verify(state.taskId);
      if (state.verification?.valid !== true) state.receiptError = 'Receipt verification did not pass' + (state.verification?.broken_at ? ` (at ${state.verification.broken_at})` : '') + '. This receipt stays marked unverified.';
    }
    catch (error) { state.verification = { valid: false }; state.receiptError = error.message; }
    if (generation === state.generation) render();
  } catch (error) { if (generation === state.generation) { showError(error, loadReceipt); state.step = 2; render(); } }
  finally { if (generation === state.generation) { state.busy = false; controls(); } }
}
function reset(clearNotice = true) {
  state.generation++; state.controller?.abort(); stopWatching();
  Object.assign(state, { step: 0, maxStep: 0, busy: false, running: false, guided: false, draft: null, taskId: null,
    questions: [], answers: {}, reviewed: false, confirmed: false, task: null, receipt: null, verification: null, receiptError: null, refreshing: false });
  state.controller = new AbortController(); clearError(); if (clearNotice) notice(); render();
}
async function connect(mode) {
  reset(); state.mode = mode; state.api = mode === 'api' ? new TaskAPI() : new MockAPI();
  document.getElementById('data-source').value = mode;
  document.getElementById('source-pill').innerHTML = '<span class="dot"></span>' + (mode === 'mock' ? 'Mock replay' : 'Task API');
  const generation = state.generation;
  try {
    const health = await state.api.health(); if (generation !== state.generation) return;
    state.health = health;
    if (typeof state.health.replay !== 'boolean' || state.health.db_ok !== true) throw new Error('The API health check did not pass. No run has started.');
    document.getElementById('mode-text').textContent = state.health.replay
      ? (mode === 'mock' ? 'Mock replay mode — ready to try. No agent calls or real payments.' : 'Replay mode — the API is using recorded carts and simulated payments.')
      : 'Connected to live staging. Every payment in this demo is simulated.';
    render();
  } catch (error) {
    if (generation !== state.generation) return;
    document.getElementById('mode-text').textContent = 'Task API unavailable. Select Mock replay to try the complete demo.';
    showError(error, () => connect(mode));
  }
}
document.getElementById('reset').addEventListener('click', () => reset());
document.getElementById('retry').addEventListener('click', () => state.retry?.());
document.getElementById('data-source').addEventListener('change', event => { document.getElementById('connection').open = false; connect(event.target.value); });
document.getElementById('run-demo').addEventListener('click', () => {
  reset(); state.form = { sentence: defaultSentence, scenario: 's2', guard_enabled: true }; createTask(true);
});
document.querySelectorAll('[data-step]').forEach(button => button.addEventListener('click', () => showStep(Number(button.dataset.step))));
connect(state.mode);
