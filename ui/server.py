"""Serve the control room alongside the unchanged protected booking app.

Run: python -B -m uvicorn ui.server:app --host 127.0.0.1 --port 8000
The booking application owns cart validation, approvals, and confirmation.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse

ROOT = Path(__file__).resolve().parents[1]
UI_FILES = {"index.html", "styles.css", "icon.svg", "app.mjs", "api.mjs", "mock-api.mjs", "format.mjs"}
TASK_PATH = re.compile(r"^/(?:health|tasks(?:/[A-Za-z0-9_-]+(?:/(?:answers|confirm|run|events|receipt(?:/verify)?))?)?)$")
app = FastAPI(title="AgentGuard demo UI", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/")
def home():
    return RedirectResponse("/ui/")


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


@app.get("/ui")
def control_room():
    return RedirectResponse("/ui/")


@app.get("/ui/{path:path}")
def static(path: str):
    if not path:
        path = "index.html"
    if path in UI_FILES:
        return FileResponse(ROOT / "ui" / path)
    raise HTTPException(404, "Page not found")


# Preserve origin/main's server-owned carts and approval-protected checkout.
from app.main import app as booking_app

app.mount("/", booking_app)
