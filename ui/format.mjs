export const esc = (value) => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
export function rupees(value) {
  if (value === null || value === undefined) return 'Unknown';
  if (!Number.isSafeInteger(value) || value < 0) throw new Error('The server returned an invalid rupee amount. The run has stopped.');
  return 'Rs ' + value.toLocaleString('en-IN');
}
export const clone = value => structuredClone(value);
export const canonical = value => JSON.stringify(sort(value));
function sort(value) {
  if (Array.isArray(value)) return value.map(sort);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(key => [key, sort(value[key])]));
  return value;
}
export async function sha256(value) {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
}
export function assertTaskMoney(task) {
  for (const contract of [task.contract, task.draft_contract].filter(Boolean)) rupees(contract.max_total);
  if (task.cart) { rupees(task.cart.total); for (const item of task.cart.items || []) rupees(item.price); }
  if (task.final?.total !== undefined) rupees(task.final.total);
  for (const decision of task.decision_history || []) {
    if (!['allow', 'block', 'ask'].includes(decision.result)
      || !Array.isArray(decision.reasons) || decision.reasons.some(reason => typeof reason !== 'string')) {
      throw new Error('The API returned an invalid guard decision. No authorization is being assumed.');
    }
  }
  return task;
}
export const itemName = item => ({ ticket: 'Train ticket', insurance: 'Travel insurance', meal: 'Priority meal', fee: 'Convenience fee' }[item.type] || { t1: 'Train ticket', t2: 'Train ticket', t3: 'Train ticket', x1: 'Travel insurance', m1: 'Priority meal', f1: 'Convenience fee' }[item.id] || item.id);
export const prefName = key => ({ refundable: 'Refundable', seat_confirmed: 'Seat confirmed', baggage: 'Baggage included' }[key] || key);
export const prefValue = value => value === null || value === undefined ? 'Don’t care' : value ? 'Yes' : 'No';
export const historyOf = task => task?.decision_history || [];
export const latestDecision = task => historyOf(task).at(-1) || null;
export const delay = (ms, signal) => new Promise((resolve, reject) => {
  if (signal?.aborted) { reject(new DOMException('Cancelled', 'AbortError')); return; }
  const cancel = () => { clearTimeout(timer); reject(new DOMException('Cancelled', 'AbortError')); };
  const timer = setTimeout(() => { signal?.removeEventListener('abort', cancel); resolve(); }, ms);
  signal?.addEventListener('abort', cancel, { once: true });
});
