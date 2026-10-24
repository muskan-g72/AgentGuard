import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { bestCoupon, couponDiscount, pageURL, quote, readState, validateCatalog } from './logic.mjs';

const data = validateCatalog(JSON.parse(readFileSync(new URL('../data/food.json', import.meta.url), 'utf8')));
const fh = data.platforms[0];
const bowl = data.options.find(row => row.id === fh.featured);
const state = (query = '') => readState(new URLSearchParams(query), fh, data);

test('seven explicitly synthetic options each have three reviews', () => {
  assert.equal(data.synthetic, true); assert.equal(data.options.length, 7);
  for (const option of data.options) assert.equal(option.review_snippets.length, 3);
});

test('all seven effective totals match the team fixture table', () => {
  const totals = data.options.map(option => {
    const platform = data.platforms.find(platform => platform.name === option.platform);
    return quote(option, platform, readState(new URLSearchParams('dish=' + option.id), platform, data)).total;
  });
  assert.deepEqual(totals, [280, 235, 175, 289, 239, 308, 245]);
});

test('FoodHub acceptance totals are 280 clean and 320 extras', () => {
  assert.equal(quote(bowl, fh, state()).total, 280);
  assert.equal(quote(bowl, fh, state('scenario=extras')).total, 320);
  assert.equal(quote(bowl, fh, state('scenario=extras&tip=0&donation=0')).total, 280);
});

test('QuickBite extras select only its flat Rs 149 membership', () => {
  const platform = data.platforms[1], option = data.options.find(row => row.id === platform.featured);
  const clean = readState(new URLSearchParams(), platform, data);
  const extra = readState(new URLSearchParams('scenario=extras'), platform, data);
  assert.equal(extra.tip, 0); assert.equal(extra.donation, 0); assert.equal(extra.gold, 1);
  assert.equal(quote(option, platform, extra).total - quote(option, platform, clean).total, 149);
});

test('quantities change item subtotal but fees/extras stay per order', () => {
  const doubled = state('scenario=qty2');
  assert.equal(doubled.qty, 2); assert.equal(quote(bowl, fh, doubled).total, 440);
  assert.equal(quote(bowl, fh, state('qty=2&scenario=extras')).total, 480);
});

test('URL state round trips without reselecting removed extras', () => {
  const selected = state('scenario=extras&tip=0&donation=10&qty=3&coupon=none');
  const url = new URL(pageURL(fh, 'checkout', selected), 'https://food.example');
  const reopened = readState(url.searchParams, fh, data);
  assert.deepEqual(reopened, selected);
  assert.equal(quote(bowl, fh, reopened).total, 810);
});

test('coupon eligibility uses item subtotal, not fees', () => {
  assert.equal(couponDiscount(bowl.coupons[0], 260), 0);
  assert.equal(bestCoupon(bowl), 'none');
  assert.equal(couponDiscount({ type: 'percent', value: 15, min_order: 200, max_discount: 100 }, 249), 37);
  assert.equal(couponDiscount(bowl.coupons[0], 600), 100);
});

test('every bill row sums to the live total, including a signed coupon row', () => {
  for (const platform of data.platforms) for (const option of data.options.filter(row => row.platform === platform.name)) {
    const selected = readState(new URLSearchParams('dish=' + option.id + '&scenario=extras'), platform, data);
    const bill = quote(option, platform, selected);
    assert.equal(bill.rows.reduce((sum, row) => sum + row.price, 0), bill.total);
    assert.ok(bill.rows.every(row => Number.isSafeInteger(row.price)));
  }
});

test('invalid URL quantities, coupons and cross-platform dishes fail closed', () => {
  for (const query of ['qty=0', 'qty=-1', 'qty=1.5', 'qty=101', 'coupon=FAKE', 'platform=quickbite', 'dish=qb-veg-thali', 'tip=999', 'gold=1', 'scenario=unknown']) {
    assert.throws(() => state(query));
  }
});

test('decimal/string money or missing reviews invalidates the catalog', () => {
  for (const value of ['300', 300.5, true]) {
    const invalid = structuredClone(data); invalid.options[0].item_price = value;
    assert.throws(() => validateCatalog(invalid));
  }
  const invalid = structuredClone(data); invalid.options[0].review_snippets.pop();
  assert.throws(() => validateCatalog(invalid));
});
