const $ = selector => document.querySelector(selector);
const platforms = ["FoodHub", "QuickBite", "DineDash"];
const baseUrls = ["foodhub", "quickbite", "dinedash"].map(path => new URL(`/${path}/`, location.origin).href);
let comparison = null;

const esc = value => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[char]));
const money = value => `Rs ${Number(value ?? 0).toLocaleString("en-IN")}`;
const fallback = (value, text) => value === undefined || value === null || value === "" ? text : value;

async function errorText(response, fallbackText) {
  const body = await response.json().catch(() => ({}));
  if (Array.isArray(body.detail)) {
    return body.detail.map(issue => {
      const field = Array.isArray(issue.loc) ? issue.loc.filter(part => part !== "body").join(".") : "request";
      return `${field || "request"}: ${issue.msg || "Invalid value"}`;
    }).join("; ");
  }
  return typeof body.detail === "string" ? body.detail : fallbackText;
}

function walletRow(values = {}) {
  const row = document.createElement("div");
  row.className = "wallet-row";
  row.innerHTML = `<label>Platform<select class="wallet-platform"><option>FoodHub</option><option>QuickBite</option><option>DineDash</option></select></label><label>Type<select class="wallet-kind"><option value="gift_voucher">Gift voucher</option><option value="wallet_credit">Wallet credit</option></select></label><label>Amount<input class="wallet-amount" type="number" min="0" step="1" required></label><label>Min order<input class="wallet-min-order" type="number" min="0" step="1" required></label><label>Code<input class="wallet-code" maxlength="64" required></label><button class="button remove-wallet" type="button" aria-label="Remove voucher">Remove</button>`;
  row.querySelector(".wallet-platform").value = values.platform || "QuickBite";
  row.querySelector(".wallet-kind").value = values.kind || "gift_voucher";
  row.querySelector(".wallet-amount").value = values.amount ?? "";
  row.querySelector(".wallet-min-order").value = values.min_order ?? "";
  row.querySelector(".wallet-code").value = values.code || "";
  row.querySelector(".remove-wallet").addEventListener("click", () => row.remove());
  $("#wallet-rows").append(row);
}

function wallet() {
  return [...document.querySelectorAll(".wallet-row")].map(row => ({
    platform: row.querySelector(".wallet-platform").value,
    kind: row.querySelector(".wallet-kind").value,
    amount: Number(row.querySelector(".wallet-amount").value),
    min_order: Number(row.querySelector(".wallet-min-order").value),
    code: row.querySelector(".wallet-code").value.trim(),
  }));
}

function contract() {
  return {diet: $("#diet").value, quantity: 1, max_total: Number($("#max-total").value), min_rating: Number($("#min-rating").value), max_eta_minutes: Number($("#max-eta").value), allow_extras: $("#allow-extras").checked, priority: $("#priority").value};
}

function setPlatformStatus(failures = {}) {
  $("#compare-status").hidden = false;
  $("#compare-status").innerHTML = platforms.map(platform => failures[platform.toLowerCase()] || failures[platform] ? `<p class="platform-failed"><strong>${platform}</strong> failed: ${esc(failures[platform.toLowerCase()] || failures[platform])}</p>` : `<p class="platform-ready"><strong>${platform}</strong> compared</p>`).join("");
}

function breakdown(row) {
  const coupon = row.coupon || {};
  const voucher = row.voucher || {};
  const couponText = coupon.eligible ? `${coupon.code}: −${money(coupon.discount)}` : `Not eligible: ${fallback(coupon.reason, "no coupon")}`;
  const voucherText = voucher.eligible ? `${voucher.code}: −${money(voucher.discount)}` : fallback(voucher.reason, "No voucher supplied.");
  return `<details class="breakdown"><summary>See price breakdown</summary><dl><div><dt>Item</dt><dd>${money(row.item_price)}</dd></div><div><dt>Delivery</dt><dd>${money(row.delivery)}</dd></div><div><dt>Platform fee</dt><dd>${money(row.platform_fee)}</dd></div><div><dt>Packaging</dt><dd>${money(row.packaging)}</dd></div><div><dt>Coupon</dt><dd>${esc(couponText)}</dd></div><div><dt>Voucher</dt><dd>${esc(voucherText)}</dd></div><div><dt>Menu total</dt><dd>${money(row.menu_total)}</dd></div><div class="price-emphasis"><dt>Effective price</dt><dd>${money(row.effective_price)}</dd></div><div><dt>Savings</dt><dd>You save ${money(row.savings)} vs menu total</dd></div></dl></details>`;
}

function card(row) {
  const badges = (row.badges || []).map(badge => `<span class="compare-badge ${esc(badge)}">${esc(badge.replaceAll("_", " "))}</span>`).join("");
  const snippet = (row.review_snippets || [])[0] || "No review snippet was returned.";
  const keywords = (row.taste_keywords || []).map(word => `<span class="keyword">${esc(word)}</span>`).join("") || "No matching taste keywords";
  return `<article class="compare-card" data-platform="${esc(row.platform)}"><div class="compare-card-top"><div><p class="eyebrow">${esc(row.platform)}</p><h2>${esc(row.dish)}</h2><p class="restaurant">${esc(row.restaurant)}</p></div><strong class="compare-price">${money(row.effective_price)}</strong></div><div class="compare-badges">${badges}</div><div class="compare-facts"><span>★ ${esc(fallback(row.rating, "—"))} <small>(${esc(fallback(row.rating_count, "—"))})</small></span><span>◷ ${esc(fallback(row.eta_minutes, "—"))} min</span><span>Taste ${Number(row.taste_score ?? 0).toFixed(2)}</span></div><p class="review">“${esc(snippet)}”</p><div class="keywords">${keywords}</div>${breakdown(row)}</article>`;
}

function explanation(row) {
  const bits = [`${money(row.effective_price)} after ${money(row.savings)} savings`];
  if (row.coupon?.eligible) bits.push(`coupon ${row.coupon.code}`);
  if (row.voucher?.eligible) bits.push(`voucher ${row.voucher.code}`);
  bits.push(`${row.eta_minutes} min delivery`);
  return bits.join(", ") + ".";
}

function renderResults(data) {
  const rows = data.ranked || [];
  const recommended = data.recommended || rows[0];
  const dropped = data.dropped || [];
  const query = $("#dish-query").value.trim().toLowerCase();
  const visible = query ? rows.filter(row => `${row.dish} ${row.restaurant}`.toLowerCase().includes(query)) : rows;
  const list = visible.length ? visible.map(card).join("") : `<p class="empty-state">No returned survivor matches that dish query. Clear it to see the ranked options.</p>`;
  $("#compare-results").innerHTML = `<section class="recommendation"><p class="eyebrow">AGENTGUARD RECOMMENDATION</p><h2>Recommended: ${esc(recommended?.dish || "No option")} on ${esc(recommended?.platform || "—")} for ${money(recommended?.effective_price)}</h2><p>${recommended ? esc(explanation(recommended)) : "No option met the contract."}</p><div class="run-controls"><label class="toggle-row"><input id="guard-off" type="checkbox"><span>Guard off (demo only)</span><small>Clearly shows the before/after bill.</small></label><button id="order-button" class="button primary" type="button" ${recommended ? "" : "disabled"}>Order with AgentGuard</button></div></section><section><div class="section-title"><div><p class="eyebrow">RESULTS</p><h2>Offers that meet your contract</h2></div><span class="mode-badge">${esc((data.mode || "replay").replaceAll("_", " "))}</span></div><div class="compare-results-grid">${list}</div></section><details class="dropped-list"><summary>Dropped options (${dropped.length})</summary>${dropped.length ? `<ul>${dropped.map(entry => `<li><strong>${esc(entry.option?.dish)} · ${esc(entry.option?.platform)}</strong><span>${esc((entry.reasons || []).join("; "))}</span></li>`).join("")}</ul>` : "<p>None.</p>"}</details><section id="run-output" class="run-output" aria-live="polite"></section>`;
  $("#order-button")?.addEventListener("click", runOrder);
}

function renderTimeline(task) {
  const events = task.events || task.audit_events || [];
  const relevant = events.filter(event => String(event.type || "").startsWith("food_"));
  const rows = relevant.map(event => {
    const payload = event.payload || {};
    const decision = payload.food_decision || payload.decision;
    const cart = payload.cart || payload.food_cart;
    const extras = (cart?.items || []).filter(item => ["tip", "donation", "membership"].includes(item.type));
    return `<li><strong>${esc((event.type || "").replaceAll("_", " "))}</strong><span>${esc(event.detail || "")}</span>${cart ? `<small>Cart total: ${money(cart.total)}${extras.length ? ` · pre-ticked: ${esc(extras.map(item => `${item.type} ${money(item.price)}`).join(", "))}` : ""}</small>` : ""}${decision ? `<small>Decision: ${esc(decision.result)}${decision.reasons?.length ? ` · ${esc(decision.reasons.join("; "))}` : ""}</small>` : ""}</li>`;
  }).join("");
  const finalCart = task.food_cart;
  $("#run-output").innerHTML = `<h2>Guarded order flow</h2><ol class="timeline">${rows || "<li>No task events were returned.</li>"}</ol><p class="run-final"><strong>${esc(task.status || "unknown")}</strong>${finalCart?.total !== undefined ? ` · final bill ${money(finalCart.total)}` : ""}</p>${task.status === "failed" ? `<button id="retry-order" class="button" type="button">Retry</button>` : ""}`;
  $("#retry-order")?.addEventListener("click", runOrder);
}

async function runOrder() {
  if (!comparison?.task_id) return;
  const output = $("#run-output");
  output.innerHTML = "<p>Staging the cart before any simulated order…</p>";
  try {
    const response = await fetch("/food/run", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({task_id: comparison.task_id, guard_off: $("#guard-off")?.checked || false, scenario: "extras", replay: comparison.mode === "fixture_replay", wallet: wallet()})});
    if (!response.ok) throw new Error(await errorText(response, `Run failed (${response.status}).`));
    renderTimeline(await response.json());
  } catch (error) {
    output.innerHTML = `<div class="guard-failure-banner" role="alert"><strong>Order flow failed.</strong><p>${esc(error.message)}</p><button id="retry-order" class="button" type="button">Retry</button></div>`;
    $("#retry-order")?.addEventListener("click", runOrder);
  }
}

async function compareOffers() {
  const error = $("#form-error");
  if (!$("#compare-form").reportValidity()) return;
  $("#compare-button").disabled = true;
  error.hidden = true;
  setPlatformStatus();
  $("#compare-results").innerHTML = `<p class="loading">Comparing FoodHub, QuickBite, and DineDash…</p>`;
  try {
    const response = await fetch("/food/compare", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({contract: contract(), platform_urls: baseUrls, wallet: wallet(), replay: true})});
    if (!response.ok) throw new Error(await errorText(response, `Comparison failed (${response.status}).`));
    comparison = await response.json();
    $("#mode-badge").textContent = comparison.mode === "live_agent" ? "LIVE" : "REPLAY";
    setPlatformStatus(comparison.failed_platforms || {});
    renderResults(comparison);
  } catch (failure) {
    $("#compare-results").innerHTML = `<div class="guard-failure-banner" role="alert"><strong>Comparison failed.</strong><p>${esc(failure.message)}</p><button id="retry-compare" class="button" type="button">Retry</button></div>`;
    $("#retry-compare")?.addEventListener("click", compareOffers);
  } finally {
    $("#compare-button").disabled = false;
  }
}

$("#add-voucher").addEventListener("click", () => walletRow());
$("#voucher-example").addEventListener("click", () => { $("#wallet-rows").replaceChildren(); walletRow({platform: "QuickBite", kind: "gift_voucher", amount: 60, min_order: 250, code: "QB60"}); });
$("#compare-form").addEventListener("submit", event => { event.preventDefault(); compareOffers(); });
document.documentElement.dataset.foodReady = "true";
