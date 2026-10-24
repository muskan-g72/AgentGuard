'use strict';

const allowed = /^\/(?:health|tasks(?:\/[A-Za-z0-9_-]+(?:\/(?:answers|confirm|run|events|receipt(?:\/verify)?))?)?)$/;

module.exports = async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  if (!['GET', 'POST'].includes(req.method)) return res.status(405).json({ error: 'Unsupported method' });
  const path = new URL(req.url, 'https://demo.invalid').searchParams.get('path');
  if (!path || !allowed.test(path)) return res.status(400).json({ error: 'Unsupported task endpoint' });
  const base = process.env.AGENTGUARD_API_URL;
  if (!base) return res.status(503).json({ error: 'Task API not connected. Select Mock replay, or configure AGENTGUARD_API_URL on the server.' });
  let upstream;
  try { upstream = new URL(base.replace(/\/$/, '') + path); if (upstream.protocol !== 'https:') throw new Error(); }
  catch { return res.status(503).json({ error: 'Task API connection is not configured correctly.' }); }
  const controller = new AbortController();
  res.on('close', () => { if (!res.writableEnded) controller.abort(); });
  const headers = { Accept: path.endsWith('/events') ? 'text/event-stream' : 'application/json' };
  if (req.headers['last-event-id']) headers['Last-Event-ID'] = req.headers['last-event-id'];
  if (process.env.AGENTGUARD_API_TOKEN) headers.Authorization = 'Bearer ' + process.env.AGENTGUARD_API_TOKEN;
  const options = { method: req.method, headers, signal: controller.signal, redirect: 'manual' };
  if (req.method === 'POST') { headers['Content-Type'] = 'application/json'; options.body = typeof req.body === 'string' ? req.body : req.body === undefined ? undefined : JSON.stringify(req.body); }
  try {
    const response = await fetch(upstream, options);
    res.statusCode = response.status;
    res.setHeader('Content-Type', response.headers.get('content-type') || 'application/json');
    if (response.headers.get('content-type')?.startsWith('text/event-stream')) {
      res.setHeader('Cache-Control', 'no-cache'); res.setHeader('X-Accel-Buffering', 'no');
      const reader = response.body.getReader();
      while (true) { const { done, value } = await reader.read(); if (done) break; res.write(Buffer.from(value)); }
      return res.end();
    }
    return res.end(Buffer.from(await response.arrayBuffer()));
  } catch {
    if (res.headersSent) return res.end();
    return res.status(503).json({ error: 'The task API is unavailable. No successful order is being assumed.' });
  }
};
