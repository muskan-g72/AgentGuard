import { SCENARIOS, HIDDEN_TEXT, bestCoupon, couponTerms, escapeHTML as esc, money, pageURL, paramsFor, quote, readState, validateCatalog } from './logic.mjs';

const root = document.getElementById('food-app');
const page = document.body.dataset.page;
const slug = document.body.dataset.platform;
let catalog, platform, state, option;
const charge = value => value < 0 ? '− ' + money(-value) : money(value);
const vegBadge = row => `<span class="diet ${row.veg ? 'veg' : 'nonveg'}"><i></i>${row.veg ? 'Vegetarian' : 'Non-vegetarian'}</span>`;
const plate = (row, large = false) => `<div class="dish-art ${large ? 'large' : ''}" aria-hidden="true"><span class="art-label">${esc(row.restaurant)}</span><img src="/food-demo/plate.svg" alt=""><span class="art-stamp">${row.veg ? 'PLANT-LED COMFORT' : 'FROM THE KITCHEN'}</span></div>`;

function nav() {
  return `<div class="fixture-bar">FICTIONAL FOOD DEMO <span>All dishes, ratings and reviews are synthetic. No real orders or payments.</span></div><header class="site-header"><a class="brand" href="/${platform.id}/?scenario=${state.scenario}"><span class="brand-icon">${esc(platform.icon)}</span>${esc(platform.name)}<small>THE FICTIONAL FOOD EDITION</small></a><nav aria-label="Platforms">${catalog.platforms.map(row => `<a class="${row.id === platform.id ? 'active' : ''}" href="/${row.id}/?scenario=${state.scenario}" ${row.id === platform.id ? 'aria-current="page"' : ''}>${esc(row.name)}</a>`).join('')}</nav><a class="sandbox-link" href="/food-demo/">Demo guide ↗</a></header><div class="context-strip"><span>◉ Serving the demo neighbourhood</span><label for="scenario">Scenario <select id="scenario">${SCENARIOS.map(value => `<option ${value === state.scenario ? 'selected' : ''}>${value}</option>`).join('')}</select></label></div>`;
}
function footer() {
  return `<footer><a class="footer-brand" href="/${platform.id}/">${esc(platform.name)}</a><span>Fictional food. Transparent numbers.</span><a href="/data/food.json">Inspect the synthetic data ↗</a></footer>`;
}
function linksFor(row) {
  return { ...state, dish: row.id, coupon: bestCoupon(row, state.qty) };
}
function listing() {
  const rows = catalog.options.filter(row => row.platform === platform.name);
  return `<section class="hero"><div><p class="eyebrow">THE ${esc(platform.name.toUpperCase())} MENU</p><h1>${esc(platform.tagline)}</h1><p>Something warming, something satisfying.<br>See the dish. Read the reviews. Check the whole bill.</p><span class="hero-count">${rows.length} dishes · all available for simulated checkout</span></div><div class="hero-plate">${plate(rows[0], true)}</div></section><aside class="promo"><span class="promo-icon">%</span><div><strong>${esc(platform.banner)}</strong><p>${esc(platform.banner_note)}</p></div><span class="demo-label">FICTIONAL OFFER</span></aside><div class="section-heading"><div><p class="eyebrow">A LITTLE INSPIRATION</p><h2>On the menu today</h2></div><span class="muted">Item prices shown. Fees and coupons at checkout.</span></div><section class="dish-grid" aria-label="Available dishes">${rows.map(row => {
    const candidate = linksFor(row); const bill = quote(row, platform, candidate);
    return `<article class="dish-card" data-dish-id="${esc(row.id)}"><a class="art-link" href="${pageURL(platform, 'dish', candidate)}" aria-label="View ${esc(row.dish)}">${plate(row)}</a><div class="card-body"><div class="card-badges">${vegBadge(row)}${row.fees.delivery === 0 ? '<span class="free-delivery">FREE delivery</span>' : ''}</div><h2><a href="${pageURL(platform, 'dish', candidate)}">${esc(row.dish)}</a></h2><p class="restaurant">${esc(row.restaurant)}</p><div class="facts"><span class="rating">★ ${row.rating.toFixed(1)} <small>(${row.rating_count})</small></span><span>◷ ${row.eta_minutes} min</span></div><div class="card-price"><strong>${money(row.item_price)}</strong><span>per dish</span><a class="text-link" href="${pageURL(platform, 'dish', candidate)}">View dish →</a></div><p class="effective-note">${money(bill.total - state.tip - state.donation - (state.gold ? platform.membership : 0))} incl. fees & eligible coupon for ${state.qty}</p></div></article>`;
  }).join('')}</section>`;
}
function detail() {
  const bill = quote(option, platform, state);
  return `<a class="back-link" href="${pageURL(platform, 'listing', state)}">← Back to the menu</a><div class="detail-grid"><section>${plate(option, true)}<div class="detail-copy">${vegBadge(option)}<h1>${esc(option.dish)}</h1><p class="restaurant">${esc(option.restaurant)}</p><div class="facts"><span class="rating">★ ${option.rating.toFixed(1)} <small>(${option.rating_count} synthetic ratings)</small></span><span>◷ ${option.eta_minutes} min</span></div><p class="description">A fictional dish for testing how an agent compares offers and inspects checkout. Every number and review comes from the same public fixture file.</p><section class="reviews"><p class="eyebrow">A TASTE OF THE CONVERSATION</p><h2>Three short reviews</h2><p class="muted">Synthetic reviews, written for this demo.</p>${option.review_snippets.map((text, index) => `<blockquote><span class="review-avatar" aria-hidden="true">${index + 1}</span><div><span class="review-label">FICTIONAL REVIEW ${index + 1}</span><p>${esc(text)}</p></div></blockquote>`).join('')}</section></div></section><aside class="bill-box"><p class="eyebrow">KNOW THE WHOLE NUMBER</p><h2>Bill details</h2>${bill.rows.filter(row => !['tip', 'donation', 'membership'].includes(row.type)).map(row => billRow(row)).join('')}<div class="bill-total"><span>Before optional extras</span><strong>${money(bill.total - state.tip - state.donation - (state.gold ? platform.membership : 0))}</strong></div><div class="coupon-list"><h3>Coupons & small print</h3>${option.coupons.map(coupon => `<p>${esc(couponTerms(coupon))}</p>`).join('') || '<p>No coupons for this dish.</p>'}</div><a class="button primary full" href="${pageURL(platform, 'checkout', state)}">Continue to checkout →</a><p class="fine-print">Simulated checkout only. No payment details needed.</p></aside></div>`;
}
function billRow(row, control = '') {
  return `<div class="bill-row ${row.type === 'coupon' ? 'discount' : ''}" data-item-id="${esc(row.id)}" data-item-type="${row.type}" data-price="${row.price}"><span>${esc(row.label)}${control}</span><strong>${row.id === 'delivery' && row.price === 0 ? 'FREE' : charge(row.price)}</strong></div>`;
}
function checkout() {
  const bill = quote(option, platform, state);
  return `<a class="back-link" href="${pageURL(platform, 'dish', state)}">← Back to the dish</a><div class="checkout-heading"><p class="eyebrow">THE LAST LOOK</p><h1>Your meal, in detail.</h1><p>Review every row before placing a simulated order.</p></div><div class="checkout-grid"><section class="checkout-story"><div class="mini-dish">${plate(option)}<div>${vegBadge(option)}<h2>${esc(option.dish)}</h2><p>${esc(option.restaurant)}</p><span class="rating">★ ${option.rating.toFixed(1)} · ${option.eta_minutes} min</span></div></div><div class="checkout-note"><span aria-hidden="true">✓</span><div><strong>A fictional checkout with real arithmetic.</strong><p>No personal details, payment form, or real delivery. This page is a test fixture, not AgentGuard authorization.</p></div></div><div class="scenario-note"><span class="eyebrow">CURRENT SCENARIO</span><h3>${esc(state.scenario)}</h3><p>Cart selections are saved in the URL, so a fresh run can reopen the same state.</p></div></section><section class="bill-box checkout-bill" aria-label="Checkout bill"><p class="eyebrow">${esc(option.restaurant.toUpperCase())}</p><h2>Order summary</h2><form id="checkout-form"><label class="quantity-label" for="qty">Quantity <input id="qty" name="qty" type="number" min="1" max="100" step="1" value="${state.qty}" required></label><div id="bill-rows">${checkoutRows(bill)}</div><label class="coupon-label" for="coupon">Apply a coupon<select id="coupon" name="coupon"><option value="none">No coupon</option>${option.coupons.map(coupon => `<option value="${esc(coupon.code)}" ${state.coupon === coupon.code ? 'selected' : ''}>${esc(coupon.code)}</option>`).join('')}</select></label><p id="coupon-condition" class="coupon-condition">${couponDescription(bill)}</p><div class="bill-total"><span>Total</span><strong id="total" data-total="${state.scenario === 'nototal' ? 'unknown' : bill.total}">${state.scenario === 'nototal' ? 'calculated at payment' : money(bill.total)}</strong></div><p id="form-error" class="form-error" role="alert" hidden></p><button id="place-order" class="button primary full" type="submit">Place order →</button><p class="fine-print">SIMULATED ORDER - no payment taken</p></form></section></div>${state.scenario === 'hidden' ? `<div class="hidden-agent-note" data-hidden="true">${HIDDEN_TEXT}</div>` : ''}`;
}
function checkoutRows(bill) {
  return bill.rows.map(row => {
    if (!['tip', 'donation', 'membership'].includes(row.type)) return billRow(row);
    const field = row.type === 'membership' ? 'gold' : row.type;
    const cost = field === 'gold' ? platform.membership : platform[field];
    return `<div class="bill-row extra-row" data-item-id="${row.id}" data-item-type="${row.type}" data-price="${row.price}" data-selected="${row.price > 0}"><label for="${field}"><input type="checkbox" id="${field}" name="${field}" ${row.price ? 'checked' : ''}><span>${esc(row.label)}${field === 'gold' ? '<small>Optional membership · one-time demo charge</small>' : '<small>Optional add-on</small>'}</span></label><strong>${money(cost)}</strong></div>`;
  }).join('');
}
function couponDescription(bill) {
  const selected = option.coupons.find(coupon => coupon.code === state.coupon);
  if (!selected) return 'No coupon selected. Fees remain part of your total.';
  return esc(couponTerms(selected)) + (bill.couponEligible ? '' : ` <strong>Not eligible: your item subtotal is ${money(bill.itemSubtotal)}.</strong>`);
}
function confirmation(params) {
  const id = params.get('order_id');
  if (!id || !/^sim_[a-zA-Z0-9_-]+$/.test(id)) return '<section class="error-card"><h1>No simulated order found.</h1><p>Return to checkout to place a simulated order.</p><a class="button primary" href="' + pageURL(platform, 'checkout', state) + '">Back to checkout</a></section>';
  const bill = quote(option, platform, state);
  return `<section class="confirmation"><div class="confirmation-check" aria-hidden="true">✓</div><p class="eyebrow">A FICTIONAL MEAL, ALL SORTED</p><h1>Order placed. In the demo.</h1><p class="simulation-banner">SIMULATED ORDER - no payment taken</p><p class="order-id">Order ID: ${esc(id)}</p><div class="bill-box">${bill.rows.filter(row => row.type === 'dish' || row.price !== 0).map(row => billRow(row)).join('')}<div class="bill-total"><span>Total</span><strong id="confirmation-total" data-total="${bill.total}">${money(bill.total)}</strong></div></div><p class="muted">This is a browser-only fixture. No restaurant was contacted.</p><a class="button primary" href="${pageURL(platform, 'listing', state)}">Back to the menu →</a></section>`;
}
function wireCheckout() {
  const form = document.getElementById('checkout-form');
  if (!form) return;
  const update = () => {
    const error = document.getElementById('form-error');
    if (!form.checkValidity()) {
      document.getElementById('place-order').disabled = true; error.textContent = 'Choose a whole quantity from 1 to 100.'; error.hidden = false;
      document.getElementById('total').dataset.total = 'unknown'; document.getElementById('total').textContent = 'Check quantity'; return;
    }
    state = { ...state, qty: Number(document.getElementById('qty').value), coupon: document.getElementById('coupon').value,
      tip: document.getElementById('tip').checked ? platform.tip : 0,
      donation: document.getElementById('donation').checked ? platform.donation : 0,
      gold: document.getElementById('gold')?.checked ? 1 : 0 };
    const bill = quote(option, platform, state);
    const rows = document.getElementById('bill-rows');
    for (const row of bill.rows) {
      const element = [...rows.children].find(element => element.dataset.itemType === row.type && (row.type === 'coupon' || element.dataset.itemId === row.id));
      element.dataset.price = String(row.price); element.dataset.itemId = row.id;
      if (['tip', 'donation', 'membership'].includes(row.type)) element.dataset.selected = String(row.price > 0);
      else { element.querySelector('span').textContent = row.label; element.querySelector('strong').textContent = row.id === 'delivery' && !row.price ? 'FREE' : charge(row.price); }
    }
    const total = document.getElementById('total');
    total.dataset.total = state.scenario === 'nototal' ? 'unknown' : String(bill.total);
    total.textContent = state.scenario === 'nototal' ? 'calculated at payment' : money(bill.total);
    document.getElementById('coupon-condition').innerHTML = couponDescription(bill);
    document.getElementById('place-order').disabled = false; error.hidden = true;
    history.replaceState(null, '', pageURL(platform, 'checkout', state));
  };
  form.addEventListener('input', update); form.addEventListener('change', update);
  form.addEventListener('submit', event => {
    event.preventDefault(); update(); if (!form.reportValidity() || document.getElementById('place-order').disabled) return;
    document.getElementById('place-order').disabled = true;
    const id = 'sim_' + (crypto.randomUUID ? crypto.randomUUID().replaceAll('-', '') : Date.now().toString(36));
    const params = paramsFor(state); params.set('order_id', id);
    location.href = `/${platform.id}/confirmation.html?${params}`;
  });
}
async function init() {
  try {
    const response = await fetch('/data/food.json', { cache: 'no-store' });
    if (!response.ok) throw new Error('The synthetic menu could not be loaded.');
    catalog = validateCatalog(await response.json()); platform = catalog.platforms.find(row => row.id === slug);
    if (!platform) throw new Error('Unknown platform.');
    const params = new URLSearchParams(location.search); state = readState(params, platform, catalog);
    option = catalog.options.find(row => row.id === state.dish);
    document.documentElement.style.setProperty('--accent', platform.color);
    document.documentElement.style.setProperty('--soft', platform.soft);
    root.innerHTML = nav() + `<main>${page === 'listing' ? listing() : page === 'dish' ? detail() : page === 'checkout' ? checkout() : confirmation(params)}</main>` + footer();
    if (page !== 'confirmation') history.replaceState(null, '', pageURL(platform, page, state));
    document.getElementById('scenario').addEventListener('change', event => {
      // New scenarios deliberately reset selections; reopening a saved URL does not.
      location.href = `/${platform.id}/${page === 'listing' ? '' : page + '.html'}?platform=${platform.id}&dish=${state.dish}&scenario=${event.target.value}`;
    });
    wireCheckout(); document.documentElement.dataset.foodReady = 'true';
  } catch (error) {
    root.innerHTML = `<main><section class="error-card" role="alert"><p class="eyebrow">DEMO PAUSED</p><h1>We couldn’t open this meal.</h1><p>${esc(error.message)}</p><a class="button primary" href="/${esc(slug)}/">Reset to the menu</a></section></main>`;
    document.documentElement.dataset.foodError = 'true';
  }
}
init();
