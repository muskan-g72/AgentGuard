"""Serve the demo UI, simulated merchant, and same-origin task proxy.

Run: python -B -m uvicorn ui.server:app --host 127.0.0.1 --port 8000
This module deliberately does not import or modify app/ or guard/.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FILES = {"index.html", "checkout.html", "confirmation.html", "app.js", "checkout.js", "styles.css"}
UI_FILES = {"index.html", "styles.css", "icon.svg", "app.mjs", "api.mjs", "mock-api.mjs", "format.mjs"}
TASK_PATH = re.compile(r"^/(?:health|tasks(?:/[A-Za-z0-9_-]+(?:/(?:answers|confirm|run|events|receipt(?:/verify)?))?)?)$")
app = FastAPI(title="AgentGuard demo UI", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/")
def home():
    return RedirectResponse("/ui/")


def simulated_order(order: dict) -> dict:
    if not isinstance(order, dict):
        raise ValueError("Invalid order")
    if not isinstance(order.get("cart_id"), str) or not order["cart_id"]:
        raise ValueError("Invalid cart ID")
    if type(order.get("total")) is not int or not 0 <= order["total"] <= 2**53 - 1:
        raise ValueError("Invalid total")
    if not isinstance(order.get("fields"), dict) or not isinstance(order.get("items"), list) or not order["items"]:
        raise ValueError("Invalid items or fields")
    items, seen = [], set()
    for item in order["items"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"] or item["id"] in seen:
            raise ValueError("Invalid item ID")
        if type(item.get("price")) is not int or not 0 <= item["price"] <= 2**53 - 1:
            raise ValueError("Invalid item price")
        seen.add(item["id"])
        items.append({"id": item["id"], "price": item["price"]})
    if sum(item["price"] for item in items) != order["total"]:
        raise ValueError("Item total mismatch")
    return {"order_id": "order_" + uuid.uuid4().hex, "cart_id": order["cart_id"], "items": items,
            "total": order["total"], "simulated": True}


@app.post("/api/order")
async def order(request: Request):
    if int(request.headers.get("content-length", "0")) > 65536:
        raise HTTPException(413, "Request too large")
    try:
        body = await request.body()
        if len(body) > 65536:
            raise HTTPException(413, "Request too large")
        result = simulated_order(json.loads(body))
    except (ValueError, TypeError):
        raise HTTPException(400, "Invalid simulated order request")
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@app.api_route("/api/task-proxy", methods=["GET", "POST"])
async def proxy(request: Request, path: str):
    if not TASK_PATH.fullmatch(path):
        raise HTTPException(400, "Unsupported task endpoint")
    upstream = os.getenv("AGENTGUARD_API_URL", "http://127.0.0.1:8001").rstrip("/")
    if not upstream.startswith(("http://", "https://")):
        raise HTTPException(503, "Task API connection is not configured")
    headers = {"Accept": "text/event-stream" if path.endswith("/events") else "application/json"}
    if request.headers.get("last-event-id"):
        headers["Last-Event-ID"] = request.headers["last-event-id"]
    if request.method == "POST":
        headers["Content-Type"] = "application/json"
    token = os.getenv("AGENTGUARD_API_TOKEN", "")
    if token:
        headers["Authorization"] = "Bearer " + token
    client = httpx.AsyncClient(timeout=httpx.Timeout(600, connect=5), follow_redirects=False)
    try:
        outgoing = client.build_request(request.method, upstream + path, headers=headers, content=await request.body())
        response = await client.send(outgoing, stream=True)
    except httpx.HTTPError:
        await client.aclose()
        raise HTTPException(503, "Task API is not reachable. Select Mock replay to try the demo.")
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        async def events():
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()
                await client.aclose()
        return StreamingResponse(events(), status_code=response.status_code, media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    try:
        body = await response.aread()
        return Response(body, status_code=response.status_code,
                        media_type=response.headers.get("content-type", "application/json"), headers={"Cache-Control": "no-store"})
    finally:
        await response.aclose()
        await client.aclose()


@app.get("/{path:path}")
def static(path: str):
    if path in PUBLIC_FILES:
        return FileResponse(ROOT / path)
    if path in ("ui", "ui/"):
        return FileResponse(ROOT / "ui/index.html") if path.endswith("/") else RedirectResponse("/ui/")
    if path.startswith("ui/") and path[3:] in UI_FILES:
        return FileResponse(ROOT / path)
    raise HTTPException(404, "Page not found")
