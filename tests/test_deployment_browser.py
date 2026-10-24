"""Real HTTP/Chromium through the generated proxy routes, with real process restart.

The proxy is a local simulation of Vercel routing, not evidence of a Vercel/Fly
deployment. Durable mount enforcement itself is tested separately; this Windows
test uses a stable local SQLite file and never pretends it is a Fly volume.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

import httpx
import pytest

from app.browser import extract_cart, wait_ready
from app.readiness import verify_readiness
from app.release import ROOT, release
from guard.contract_parser import DEMO_CONTRACT
from scripts.prepare_deployment import prepare
from test_deployment import artifact_root


pytestmark = pytest.mark.browser


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def public_proxy(artifact_root):
    prepare("agentguard-test-only", "bom", artifact_root)
    config = json.loads((artifact_root / ".vercel/output/config.json").read_text())
    port = free_port()
    backend = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.update(AGENTGUARD_DB=str(artifact_root / "state.db"), AGENTGUARD_DEPLOYMENT_MODE="local",
               AGENTGUARD_PUBLIC_ORIGIN="https://demo-booking-tau.vercel.app",
               AGENTGUARD_BACKEND_HOST="agentguard-test-only.fly.dev", AGENTGUARD_ENABLE_AGENT_RUNS="false",
               RECEIPT_KEY="test-only-public-proxy-receipt-key")
    env.pop("VERCEL", None)
    processes = []
    log = (artifact_root / "backend.log").open("w", encoding="utf-8")

    def start():
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT, env=env, stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        processes.append(process)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                if httpx.get(backend + "/health", trust_env=False).status_code == 200:
                    return
            except httpx.TransportError:
                pass
            if process.poll() is not None:
                raise RuntimeError("Backend exited; inspect " + str(artifact_root / "backend.log"))
            time.sleep(.1)
        raise RuntimeError("Backend failed to start")

    def restart():
        processes[-1].terminate()
        processes[-1].wait(timeout=10)
        start()

    class Proxy(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def forward(self):
            path, _, query = self.path.partition("?")
            route = next(route for route in config["routes"] if re.fullmatch(route["src"], path))
            match = re.fullmatch(route["src"], path)
            destination = route["dest"]
            for index, group in enumerate(match.groups(), 1):
                destination = destination.replace(f"${index}", group)
            if destination == "/deployment.json":
                status = 200
                body = (artifact_root / ".vercel/output/static/deployment.json").read_bytes()
                headers = {"Content-Type": "application/json"}
            else:
                upstream = urlparse(destination)
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                response = httpx.request(self.command, backend + upstream.path + ("?" + query if query else ""),
                    content=body, headers={"Host": upstream.hostname, "Content-Type": self.headers.get("Content-Type", "application/json")},
                    timeout=20, trust_env=False)
                status, body = response.status_code, response.content
                headers = {key: value for key, value in response.headers.items()
                           if key.lower() not in {"content-length", "transfer-encoding", "connection"}}
            headers = {key.lower(): value for key, value in (headers | route["headers"]).items()}
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = forward
        do_POST = forward
        do_PUT = forward

    start()
    proxy = ThreadingHTTPServer(("127.0.0.1", 0), Proxy)
    thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{proxy.server_port}", timeout=20, trust_env=False) as client:
            yield str(client.base_url).rstrip("/"), client, restart
    finally:
        proxy.shutdown()
        proxy.server_close()
        thread.join(timeout=5)
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
        log.close()


def reviewed(client):
    task = client.post("/tasks", json={"sentence": "Reviewed simulated demo", "draft_contract": DEMO_CONTRACT.model_dump()}).json()
    task_id = task["task_id"]
    client.post(f"/tasks/{task_id}/answers", json={"answers": {question["key"]: "don't care" for question in task["questions"]}}).raise_for_status()
    client.post(f"/tasks/{task_id}/confirm", json={}).raise_for_status()
    return task_id


def test_proxy_button_and_direct_navigation_use_protected_server(public_proxy):
    playwright = pytest.importorskip("playwright.sync_api")
    base, client, _ = public_proxy
    task_id = reviewed(client)
    assert verify_readiness(base, expected_release=release()["release_id"], require_durable=False, require_proxy=False)["ready"]
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        with browser.new_context() as context:
            page = context.new_page()
            page.goto(base + "/checkout.html?task_id=" + task_id)
            wait_ready(page)
            page.locator("#check-cart").click()
            page.wait_for_function("!document.querySelector('#confirm').disabled")
            page.locator("#confirm").click()
            page.wait_for_url("**/confirmation.html?order_id=*")
            page.wait_for_selector("#order[data-order-id]")
            order_id = page.locator("#order").get_attribute("data-order-id")
            assert client.get("/api/orders/" + order_id).json()["simulated"] is True
            assert "no-store" in client.get("/api/orders/" + order_id).headers["Cache-Control"]
        with browser.new_context() as other:
            direct = other.new_page()
            direct.goto(base + "/confirmation.html?ticket=t1&total=1000", wait_until="networkidle")
            assert direct.locator("h1").inner_text() == "No confirmed order"
        browser.close()


def test_approval_cart_order_persist_across_real_backend_restart_and_fresh_browsers(public_proxy):
    playwright = pytest.importorskip("playwright.sync_api")
    base, first_client, restart = public_proxy
    task_id = reviewed(first_client)
    before = first_client.get("/health").json()
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        with browser.new_context() as first:
            page = first.new_page()
            page.goto(base + "/checkout.html?task_id=" + task_id)
            wait_ready(page)
            cart = extract_cart(page).model_dump(mode="json")
            approval = page.evaluate("() => window.AgentGuardCheckout.check()")["approval"]
            staged_url = page.url
        restart()
        with httpx.Client(base_url=base, timeout=20, trust_env=False) as fresh_client:
            after = fresh_client.get("/health").json()
            assert before["storage"]["storage_id"] == after["storage"]["storage_id"]
            assert before["instance_id"] != after["instance_id"]
            with browser.new_context() as second:
                page = second.new_page()
                page.goto(staged_url)
                wait_ready(page)
                assert extract_cart(page).model_dump(mode="json") == cart
                outgoing = {"cart_id": cart["cart_id"], "items": [{"id": item["id"], "price": item["price"]} for item in cart["items"]], "total": cart["total"], "fields": {}}
                body = {"task_id": task_id, "approval": approval, "order_request": outgoing}
                url = "/api/carts/" + cart["cart_id"] + "/confirm"
                result = fresh_client.post(url, json=body)
                assert result.status_code == 200, result.text
                order = result.json()
                assert fresh_client.post(url, json=body).json() == order
                page.goto(base + "/confirmation.html?order_id=" + order["order_id"])
                page.wait_for_selector("#order[data-order-id]")
                assert page.locator("h1").inner_text() == "Booking confirmed"
            restart()
            assert fresh_client.get("/api/orders/" + order["order_id"]).json() == order
        browser.close()
