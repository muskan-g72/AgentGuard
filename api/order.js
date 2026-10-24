'use strict';

// Simulated merchant only. This intentionally accepts the s7 extras so that a
// guard can demonstrate inspecting the real outgoing request before submission.
function simulateOrder(order) {
  const invalid = (message) => { const error = new Error(message); error.status = 400; throw error; };
  if (!order || typeof order.cart_id !== 'string' || !order.cart_id || !Array.isArray(order.items) || !order.items.length) invalid('Invalid cart');
  if (!Number.isSafeInteger(order.total) || order.total < 0 || !order.fields || Array.isArray(order.fields) || typeof order.fields !== 'object') invalid('Invalid total or fields');
  const ids = new Set(); let sum = 0;
  for (const item of order.items) {
    if (typeof item.id !== 'string' || !item.id || ids.has(item.id) || !Number.isSafeInteger(item.price) || item.price < 0) invalid('Invalid item');
    ids.add(item.id); sum += item.price;
  }
  if (!Number.isSafeInteger(sum) || sum !== order.total) invalid('Item total mismatch');
  return { order_id: 'order_' + require('node:crypto').randomUUID(), cart_id: order.cart_id,
    items: order.items.map(({ id, price }) => ({ id, price })), total: order.total, simulated: true };
}

module.exports = async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  if (req.method !== 'POST') { res.setHeader('Allow', 'POST'); return res.status(405).json({ error: 'Use POST' }); }
  try {
    const body = typeof req.body === 'string' ? JSON.parse(req.body) : req.body;
    return res.status(200).json(simulateOrder(body));
  } catch (error) { return res.status(error.status || 400).json({ error: 'Invalid simulated order request' }); }
};
module.exports.simulateOrder = simulateOrder;
