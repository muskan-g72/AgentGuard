"""Stage, independently extract, check, remove controlled extras, recheck."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from guard.models import Cart

from .browser import browser_session, extract_cart, remove_items, wait_ready
from .staging import stage_cart_evidence
from .store import Store, WorkflowError, canonical
from .tinyfish_client import DEMO_URL, validate_demo_url


def content(cart: Cart):
    """A newly allocated local mirror has a different, explicitly recorded ID."""
    return cart.model_dump(mode="json", exclude={"cart_id"})


def _local_url(url):
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"} or parsed.path != "/checkout.html":
        raise WorkflowError("Local workflows require a loopback checkout URL.", 422)
    return url


def run_task(store: Store, task_id: str, mode="local", cart_url=None, confirm=False, *, headed=False):
    task = store.task(task_id)
    contract = Store._reviewed(task)
    local_base = os.getenv("DEMO_LOCAL_URL", "http://127.0.0.1:8001").rstrip("/")
    query = {"scenario": task["scenario"], "from": contract.route.from_, "to": contract.route.to,
             "date": contract.date, "passengers": contract.quantity}
    source = None
    store.event(task_id, "staging", f"Mode: {mode}. Playwright is an independent browser, not a TinyFish session.")
    try:
        if mode in {"live", "replay"}:
            target = cart_url or (os.getenv("DEMO_URL", DEMO_URL).rstrip("/") + "/index.html?" + urlencode(query))
            source = stage_cart_evidence(target, contract, scenario=task["scenario"], max_attempts=1,
                                         replay=(mode == "replay"))
            if mode == "live":
                if not source.staged_url:
                    raise WorkflowError("Live result omitted the exact staged checkout URL; no reconciliation is possible.")
                validate_demo_url(source.staged_url)
                with browser_session() as independent:
                    context = independent.new_context()
                    page = context.new_page()
                    page.goto(source.staged_url, wait_until="networkidle", timeout=20000)
                    wait_ready(page)
                    observed = extract_cart(page)
                    if canonical(observed) != canonical(source.cart):
                        raise WorkflowError("TinyFish and independent Playwright evidence disagree; no approval issued.")
                    context.close()
                query = {key: values[-1] for key, values in parse_qs(urlparse(source.staged_url).query).items()
                         if key not in {"cart_id", "task_id"}}
            elif cart_url:
                query.update({key: values[-1] for key, values in parse_qs(urlparse(cart_url).query).items()
                              if key not in {"cart_id", "task_id"}})
            target = local_base + "/checkout.html?" + urlencode(query)
        else:
            target = cart_url or local_base + "/checkout.html?" + urlencode(query)
        _local_url(target)
        separator = "&" if "?" in target else "?"
        target += separator + urlencode({"task_id": task_id})
        with browser_session(headed=headed) as browser:
            context = browser.new_context()
            page = context.new_page()
            page.goto(target, wait_until="networkidle", timeout=20000)
            wait_ready(page)
            observed = extract_cart(page)
            if source and canonical(content(observed)) != canonical(content(source.cart)):
                raise WorkflowError("Staged evidence differs from the local authoritative demo state; no approval issued.")
            trace = []

            def check_current():
                independent_cart = extract_cart(page)
                authoritative = store.cart(independent_cart.cart_id)
                if canonical(independent_cart) != canonical(authoritative["cart"]):
                    raise WorkflowError("Independent Playwright evidence and server cart disagree.")
                store.event(task_id, "checking", "Fresh independent DOM extraction reconciled with server cart.")
                result = page.evaluate("() => window.AgentGuardCheckout.check()")
                trace.append({"cart": independent_cart.model_dump(mode="json"), "decision": result["decision"]})
                return result

            result = check_current()
            decision = result["decision"]
            if decision["result"] == "block" and decision["remove_item_ids"]:
                store.event(task_id, "fixing", "One bounded removal pass using returned actual item IDs.")
                try:
                    remove_items(page, decision["remove_item_ids"])
                except WorkflowError as error:
                    return store.event(task_id, "blocked", str(error), trace=trace, mode=mode)
                result = check_current()
                decision = result["decision"]
            fields = {"trace": trace, "mode": mode, "staged_url": page.url}
            artifacts = Path(__file__).resolve().parents[1] / "test-results"
            artifacts.mkdir(exist_ok=True)
            checkout_image = artifacts / f"{task_id}-checkout.png"
            page.screenshot(path=str(checkout_image), full_page=True)
            fields["checkout_screenshot"] = str(checkout_image)
            if source:
                fields["source_cart_id"] = source.cart.cart_id
                fields["reconciliation"] = "Separate sessions; full cart content matched. Local mirror has its own server-issued cart ID."
            if decision["result"] == "allow" and confirm:
                store.event(task_id, "committing", "Confirm button will submit the actual outgoing order request.", **fields)
                page.locator("#confirm").click()
                page.wait_for_url("**/confirmation.html?order_id=*", timeout=15000)
                page.wait_for_selector("#order[data-order-id]", timeout=10000)
                order_image = artifacts / f"{task_id}-order.png"
                page.screenshot(path=str(order_image), full_page=True)
                return store.event(task_id, "done", "Confirmed order read back from the server.", order_screenshot=str(order_image))
            status = {"allow": "allowed", "block": "blocked", "ask": "blocked"}[decision["result"]]
            return store.event(task_id, status, "Confirmation paused unless explicitly requested and allowed.", **fields)
    except Exception as error:
        # Local safe error classes carry useful details; don't expose arbitrary SDK messages.
        from .tinyfish_client import TinyFishError
        detail = str(error) if isinstance(error, (WorkflowError, TinyFishError)) else f"Workflow failed ({type(error).__name__}); no order was authorized."
        return store.event(task_id, "failed", detail, mode=mode)
