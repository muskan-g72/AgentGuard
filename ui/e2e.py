"""Browser checks for the standalone demo; requires Playwright Chromium.

Run with the UI server running: python -B ui/e2e.py
Set UI_TEST_API=1 to also check the backend at the configured proxy origin.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright

BASE = os.getenv("UI_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
OUTPUT = Path(__file__).resolve().parent / "test-results"
OUTPUT.mkdir(exist_ok=True)


def no_overflow(page):
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Horizontal overflow"


def questions(page, refundable="Don’t care"):
    groups = page.locator(".answers")
    for index in range(groups.count()):
        groups.nth(index).get_by_role("radio", name=refundable if index == 0 else "Don’t care", exact=True).click()
    page.get_by_role("button", name="Review my contract").click()
    expect(page.get_by_role("heading", name="Your booking. Your boundaries.")).to_be_visible()


def manual_run(page, scenario, refundable="Don’t care", guard=True):
    page.goto(BASE + "/ui/")
    page.locator("#scenario").select_option(scenario)
    if not guard:
        page.get_by_role("switch").click()
    page.get_by_role("button", name="Set my boundaries").click()
    expect(page.get_by_role("button", name="Review my contract")).to_be_disabled()
    questions(page, refundable)
    page.get_by_role("button", name="Confirm contract & run").click()
    expect(page.locator("#view-receipt")).to_be_visible(timeout=25000)


with sync_playwright() as playwright:
    options = {"executable_path": os.environ["UI_BROWSER_PATH"]} if os.getenv("UI_BROWSER_PATH") else {}
    browser = playwright.chromium.launch(**options)
    context = browser.new_context(viewport={"width": 1440, "height": 1080}, device_scale_factor=1)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(BASE + "/ui/")
    expect(page.get_by_role("heading", name="What should your agent do?")).to_be_visible()
    no_overflow(page)
    page.screenshot(path=str(OUTPUT / "desktop-input.png"), full_page=True, animations="disabled")
    page.get_by_role("button", name="Run demo", exact=True).click()
    expect(page.get_by_role("heading", name="Your guard kept a record.")).to_be_visible(timeout=30000)
    expect(page.locator("#verified-badge")).to_have_text("✓ Verified · mock")
    expect(page.locator(".receipt-total strong")).to_have_text("Rs 1,000")
    expect(page.locator(".receipt-list .stopped")).to_have_count(2)
    expect(page.locator(".compare-card").first).to_contain_text("Rs 1,350")
    page.screenshot(path=str(OUTPUT / "desktop-receipt.png"), full_page=True, animations="disabled")
    page.pdf(path=str(OUTPUT / "receipt.pdf"), format="A4", print_background=True)
    assert len(re.findall(rb'/Type\s*/Page\b', (OUTPUT / "receipt.pdf").read_bytes())) == 1
    with page.expect_download() as download:
        page.get_by_role("button", name="Download JSON").click()
    assert download.value.suggested_filename.endswith(".json")
    page.get_by_role("button", name="Reset", exact=False).click()
    expect(page.get_by_role("heading", name="What should your agent do?")).to_be_visible()

    manual_run(page, "s7")
    expect(page.locator(".decision-label")).to_contain_text("BLOCK")
    expect(page.locator(".request-detail")).to_contain_text("Rs 1,500")
    assert page.locator(".cart-total strong").inner_text() == "Rs 1,000"
    page.screenshot(path=str(OUTPUT / "request-block.png"), full_page=True, animations="disabled")
    page.locator("#view-receipt").click()
    expect(page.locator(".receipt-total strong")).to_have_text("Rs 0")

    manual_run(page, "s8", refundable="Yes")
    expect(page.locator(".decision-label")).to_contain_text("BLOCK")
    expect(page.locator(".decision-card")).to_contain_text("refundable")

    manual_run(page, "s6")
    expect(page.locator(".decision-label")).to_contain_text("ASK")
    expect(page.locator(".cart-total strong")).to_have_text("Unknown")

    manual_run(page, "s2", guard=False)
    expect(page.locator(".decision-label")).to_contain_text("BLOCK")
    page.locator("#view-receipt").click()
    expect(page.locator(".compare-card").first).to_contain_text("Guard OFF · this run")
    expect(page.locator(".compare-card.on")).to_contain_text("Guard ON · illustration")

    # The merged search keeps main's filtering, validation, group fares and URL
    # state. Native checkout remains owned by the approval-protected backend.
    page.goto(BASE + "/index.html?passengers=2&scenario=s2")
    expect(page.locator("#from")).to_be_editable()
    expect(page.locator("#date")).to_have_value("2026-10-25")
    expect(page.locator("#results article")).to_have_count(2)
    expect(page.locator("#results")).to_contain_text("Rs 2,000 for 2 passenger(s)")
    selected = page.locator("#results a").first.get_attribute("href")
    assert parse_qs(urlsplit(selected).query)["passengers"] == ["2"]
    page.locator("#scenario-select").select_option("s3")
    expect(page.locator("#passengers")).to_have_value("2")
    assert parse_qs(urlsplit(page.url).query)["scenario"] == ["s3"]
    page.locator("#to").fill("Ludhiana")
    page.get_by_role("button", name="Search trains").click()
    assert not page.locator("#search").evaluate("form => form.checkValidity()")
    page.locator("#from").fill("Mumbai")
    page.locator("#to").fill("Pune")
    page.get_by_role("button", name="Search trains").click()
    expect(page.locator("#results")).to_have_text("No trains found")
    page.goto(BASE + "/index.html?date=2026-10-26")
    expect(page.locator("#results article")).to_have_count(1)
    expect(page.locator("#results")).to_contain_text("T3")
    page.locator("#scenario-select").select_option("s8")
    expect(page.locator("#scenario")).to_have_value("s8")
    page.goto(BASE + "/checkout.html?scenario=s1")
    page.wait_for_function("window.guardReady === true")
    expect(page.locator("#confirm")).to_be_disabled()
    assert page.request.post(BASE + "/api/order", data={}).status == 404

    # An unavailable API never silently becomes a successful mock run.
    page.route("**/api/task-proxy?*", lambda route: route.fulfill(status=503, json={"error": "Task API unavailable"}))
    page.goto(BASE + "/ui/?api=1")
    expect(page.locator("#error")).to_be_visible()
    expect(page.locator("#mode-text")).to_contain_text("unavailable")
    page.unroute("**/api/task-proxy?*")

    mobile = context.new_page()
    mobile.set_viewport_size({"width": 390, "height": 844})
    mobile.on("pageerror", lambda error: errors.append(str(error)))
    mobile.goto(BASE + "/ui/")
    no_overflow(mobile)
    mobile.screenshot(path=str(OUTPUT / "mobile-input.png"), full_page=True, animations="disabled")
    mobile.get_by_role("button", name="Run demo", exact=True).click()
    expect(mobile.get_by_role("heading", name="Your guard kept a record.")).to_be_visible(timeout=30000)
    no_overflow(mobile)
    mobile.screenshot(path=str(OUTPUT / "mobile-receipt.png"), full_page=True, animations="disabled")
    mobile.set_viewport_size({"width": 320, "height": 760})
    no_overflow(mobile)
    mobile.get_by_role("button", name="Reset", exact=False).click()
    no_overflow(mobile)

    if os.getenv("UI_TEST_API") == "1":
        page.goto(BASE + "/ui/?api=1")
        expect(page.locator("#mode-text")).to_contain_text("Replay mode")
        expect(page.locator("#mode-text")).not_to_contain_text("Mock")
        manual_url = BASE + "/ui/?api=1"
        page.goto(manual_url)
        page.get_by_role("button", name="Run demo", exact=True).click()
        expect(page.get_by_role("heading", name="Your guard kept a record.")).to_be_visible(timeout=30000)
        expect(page.locator("#verified-badge")).to_have_text("✓ Verified")
        expect(page.locator(".receipt-total strong")).to_have_text("Rs 1,000")
        def broken_verification(route):
            path = parse_qs(urlsplit(route.request.url).query).get("path", [""])[0]
            if path.endswith("/receipt/verify"):
                route.fulfill(status=200, json={"valid": False, "broken_at": 2})
            else:
                route.continue_()
        page.route("**/api/task-proxy?*", broken_verification)
        page.locator('[data-step="2"]').click()
        page.locator("#view-receipt").click()
        expect(page.locator("#verified-badge")).to_have_text("? Not verified")
        expect(page.locator(".proof-note")).to_contain_text("verification did not pass")
        page.unroute("**/api/task-proxy?*", broken_verification)

    assert not errors, json.dumps(errors, indent=2)
    browser.close()
    print("Browser checks passed: dashboard flows, mobile 390px/320px, editable search/validation/filtering/group prices, protected checkout, errors, receipt download, and reset.")
