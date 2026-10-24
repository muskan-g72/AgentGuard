"""Independent Playwright extraction of rendered checkout evidence."""

from __future__ import annotations

from contextlib import contextmanager
import re

from guard.models import Cart
from guard.page_scan import scan_html

from .store import WorkflowError


@contextmanager
def browser_session(*, headed=False):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise WorkflowError("Install .[dev,browser] and run python -m playwright install chromium.", 503) from error
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed, slow_mo=250 if headed else 0)
        try:
            yield browser
        finally:
            browser.close()


def wait_ready(page):
    page.wait_for_function("window.guardReady === true", timeout=15000)


def extract_cart(page) -> Cart:
    """Read DOM attributes and actual checkbox state; never use a fixture/catalog.

    This deliberately does not call the frontend's extractor. Missing total or
    passenger evidence remains null, including on s6.
    """
    raw = page.evaluate("""() => {
        const cart = document.querySelector('#cart');
        if (!cart) throw new Error('Rendered cart element is missing');
        const rows = [...cart.querySelectorAll('[data-item-id]')];
        const included = rows.filter(row => {
            const box = row.querySelector('input[type=checkbox]');
            return !box || box.checked;
        });
        const attrs = {};
        ['refundable','seat_confirmed','baggage'].forEach(key => {
            const value = cart.getAttribute('data-' + key.replaceAll('_','-'));
            attrs[key] = value === 'true' ? true : value === 'false' ? false : null;
        });
        const hidden = [...cart.querySelectorAll('*')].filter(node => {
            const style = getComputedStyle(node), rect = node.getBoundingClientRect();
            return node.dataset.hidden === 'true' || node.getAttribute('aria-hidden') === 'true' ||
              style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0 ||
              parseFloat(style.fontSize) === 0 || rect.right < 0 || rect.bottom < 0;
        }).filter(node => node.textContent.trim()).map(node => node.textContent.trim());
        const passengers = document.querySelector('#passengers');
        return {cart_id: cart.dataset.cartId, items: included.map(row => ({
            id: row.getAttribute('data-item-id'), type: row.getAttribute('data-item-type'),
            price: row.getAttribute('data-price'), route: row.getAttribute('data-route') || null,
            date: row.getAttribute('data-date') || null
        })), total: document.querySelector('#total')?.getAttribute('data-total') ?? null,
            passengers: !passengers || passengers.hidden ? null : passengers.getAttribute('data-passengers'),
            attributes: attrs, hidden_text: [...new Set(hidden)]};
    }""")

    def integer(value, *, unknown=False):
        if unknown and value in (None, "unknown"):
            return None
        if not isinstance(value, str) or not re.fullmatch(r"\d+", value):
            raise WorkflowError("Rendered cart contains missing or invalid integer evidence.")
        return int(value)

    for item in raw["items"]:
        item["price"] = integer(item["price"])
    raw["total"] = integer(raw["total"], unknown=True)
    raw["passengers"] = integer(raw["passengers"], unknown=True)
    ids = [item["id"] for item in raw["items"]]
    if len(ids) != len(set(ids)):
        raise WorkflowError("Rendered cart has duplicate item IDs.")
    return Cart.model_validate(raw)


def inspect_page(page):
    return {"cart": extract_cart(page), "page_scan": scan_html(page.content()), "url": page.url}


def remove_items(page, item_ids):
    """Remove actual returned IDs via their controls; never edit away a fee URL."""
    for item_id in item_ids:
        rows = page.locator("[data-item-id]").all()
        matching = [row for row in rows if row.get_attribute("data-item-id") == item_id]
        if len(matching) != 1:
            raise WorkflowError(f"BLOCK: Item {item_id} cannot be uniquely targeted.")
        checkbox = matching[0].locator('input[type="checkbox"]')
        if checkbox.count() != 1 or not checkbox.is_enabled():
            raise WorkflowError(f"BLOCK: Item {item_id} has no removable control; no order created.")
        checkbox.uncheck()
        page.evaluate("() => window.AgentGuardCheckout.synced()")
        wait_ready(page)
