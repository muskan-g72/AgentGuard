import { assertTaskMoney } from './format.mjs';

export class TaskAPI {
  mode = 'api';
  url(path) { return '/api/task-proxy?path=' + encodeURIComponent(path); }
  async request(path, { method = 'GET', body, signal, timeout = 20000 } = {}) {
    const options = { method, headers: { Accept: 'application/json' }, signal: signal || AbortSignal.timeout(timeout), cache: 'no-store' };
    if (body !== undefined) { options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(body); }
    let response;
    try { response = await fetch(this.url(path), options); }
    catch (error) { if (error.name === 'AbortError') throw error; throw new Error('The task API could not be reached. Check its connection, or select Mock replay to try the demo.'); }
    let result;
    try { result = await response.json(); } catch { throw new Error('The task API returned an unreadable response. No order is being assumed successful.'); }
    if (!response.ok) {
      const message = typeof result.detail === 'string' ? result.detail : typeof result.error === 'string' ? result.error
        : response.status === 422 ? 'The connected API rejected this scenario or contract. Try Mock replay; S7 and S8 need backend support before they can run through the API.' : `The API returned ${response.status}.`;
      throw new Error(message);
    }
    return result;
  }
  health() { return this.request('/health'); }
  create(body) { return this.request('/tasks', { method: 'POST', body }); }
  answers(id, answers) { return this.request(`/tasks/${encodeURIComponent(id)}/answers`, { method: 'POST', body: { answers } }); }
  confirm(id, contract) { return this.request(`/tasks/${encodeURIComponent(id)}/confirm`, { method: 'POST', body: { contract } }); }
  async get(id) { return assertTaskMoney(await this.request(`/tasks/${encodeURIComponent(id)}`)); }
  async run(id, { signal } = {}) { return assertTaskMoney(await this.request(`/tasks/${encodeURIComponent(id)}/run`, { method: 'POST', signal, timeout: 300000 })); }
  receipt(id) { return this.request(`/tasks/${encodeURIComponent(id)}/receipt`); }
  verify(id) { return this.request(`/tasks/${encodeURIComponent(id)}/receipt/verify`); }
  subscribe(id, callback, onError) {
    const source = new EventSource(this.url(`/tasks/${encodeURIComponent(id)}/events`));
    const receive = event => {
      try { callback(JSON.parse(event.data)); }
      catch { onError?.(new Error('An unreadable status event was received. Refreshing the task instead.')); }
    };
    source.addEventListener('status', receive); source.addEventListener('message', receive);
    source.onerror = () => onError?.(new Error('The live stream paused. Task updates will keep polling.'));
    return () => source.close();
  }
}
