"""FastAPI endpoints specified by AgentGuard Schema v2."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import Field

from guard.checker import check
from guard.contract_parser import parse_contract
from guard.models import Contract, Message
from guard.request_check import canonical_json

from .drivers import ReplayDriver, TinyFishDriver
from .service import TaskService
from .store import Store, verify_receipt

Scenario = Literal["s1", "s2", "s3", "s4", "s5", "s6"]


class CreateTask(Message):
    sentence: str = Field(min_length=1, max_length=4000)
    scenario: Scenario = "s2"
    guard_enabled: bool = True


class Answers(Message):
    answers: dict[Literal["refundable", "seat_confirmed", "baggage"], Literal["yes", "no", "don't care"]]


class Confirm(Message):
    contract: Contract | None = None


class Stage(Message):
    sentence: str = Field(default="One Ludhiana to Delhi ticket on 2026-10-26 under Rs 1000, no extras.", max_length=4000)
    scenario: Scenario = "s2"
    contract: Contract | None = None


def create_app(*, db_path: str | None = None, receipt_key: str | None = None, driver=None) -> FastAPI:
    # No database side effects on import; configuration is loaded on startup.
    @asynccontextmanager
    async def lifespan(api):
        store = Store(db_path or os.getenv("AGENTGUARD_DB", "agentguard.sqlite3"),
                      receipt_key if receipt_key is not None else os.getenv("RECEIPT_KEY", ""))
        selected = driver if driver is not None else (
            ReplayDriver() if os.getenv("AGENTGUARD_REPLAY", "1") == "1" else TinyFishDriver()
        )
        api.state.store = store
        api.state.service = TaskService(store, selected)
        try:
            yield
        finally:
            store.close()

    api = FastAPI(title="AgentGuard", version="2", lifespan=lifespan)

    @api.exception_handler(KeyError)
    async def missing_task(request: Request, exc: KeyError):
        return JSONResponse(status_code=404, content={"detail": "Task not found"})

    @api.get("/health")
    def health():
        return {
            "replay": api.state.service.driver.replay,
            "tinyfish_configured": bool(os.getenv("TINYFISH_API_KEY")),
            "db_ok": api.state.store.healthy(),
        }

    @api.post("/tasks")
    def create_task(body: CreateTask):
        return api.state.service.create(body.sentence, body.scenario, body.guard_enabled)

    @api.post("/tasks/{task_id}/answers")
    def answer_task(task_id: str, body: Answers):
        return api.state.service.answers(task_id, body.answers)

    @api.post("/tasks/{task_id}/confirm")
    def confirm_task(task_id: str, body: Confirm | None = None):
        return api.state.service.confirm(task_id, body.contract if body else None)

    @api.post("/tasks/{task_id}/run")
    def run_task(task_id: str):
        return api.state.service.run(task_id)

    @api.get("/tasks/{task_id}")
    def get_task(task_id: str):
        return api.state.store.get(task_id)

    @api.get("/tasks/{task_id}/events")
    async def task_events(task_id: str, request: Request, last_event_id: str | None = Header(default=None)):
        api.state.store.get(task_id)
        try:
            cursor = int(last_event_id or "0")
            if cursor < 0:
                raise ValueError
        except ValueError:
            raise HTTPException(400, "Last-Event-ID must be a nonnegative integer")

        async def stream():
            nonlocal cursor
            while not await request.is_disconnected():
                task = api.state.store.get(task_id)
                for event in task["events"]:
                    if event["id"] > cursor:
                        cursor = event["id"]
                        if event["type"] == "status":
                            data = {"task_id": task_id, "status": event["payload"]["to"]}
                            yield f"id: {event['id']}\nevent: status\ndata: {canonical_json(data)}\n\n"
                if task["status"] in ("done", "failed") or (task["status"] == "blocked" and not task["running"]):
                    break
                yield ": keep-alive\n\n"
                await asyncio.sleep(0.5)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @api.get("/tasks/{task_id}/receipt")
    def receipt(task_id: str):
        value = api.state.store.receipt(task_id)
        if not api.state.store.key:
            raise HTTPException(503, "RECEIPT_KEY is required for signed receipts")
        return value

    @api.get("/tasks/{task_id}/receipt/verify")
    def verify(task_id: str):
        return verify_receipt(api.state.store.receipt(task_id), api.state.store.key)

    @api.post("/stage")
    def stage(body: Stage):
        contract = body.contract or parse_contract(body.sentence)
        try:
            cart = api.state.service.driver.stage(contract, body.scenario)
            decision = check(contract, cart)
            return {"contract": contract.model_dump(mode="json"), "cart": cart.model_dump(mode="json"), "decision": decision.model_dump(mode="json")}
        except Exception:
            raise HTTPException(502, "Staging failed; no order was committed")

    return api


app = create_app()
