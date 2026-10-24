"""HTTP API for staging and checking a demo cart."""

from __future__ import annotations

import json
import os
import time
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, HttpUrl

from .log import log_event
from .staging import StagingError, stage_cart_details
from .tasks import (
    InvalidTransitionError,
    TaskNotFoundError,
    audit,
    connection,
    create_task,
    get_task,
    task_events,
    transition,
    update_contract,
)

try:
    from guard.checker import check
    from guard.contract_parser import DEMO_CONTRACT, parse_contract
    from guard.models import Contract

    _GUARD_AVAILABLE = True
except ImportError:
    check = None
    DEMO_CONTRACT = None
    _GUARD_AVAILABLE = False


class TaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentence: str
    scenario: str
    guard_enabled: bool = True


class AnswersRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: dict[str, str]


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract: dict | None = None


class StageRequest(BaseModel):
    cart_url: HttpUrl
    scenario: str


app = FastAPI(title="AgentGuard staging API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _task_or_404(task_id: str) -> dict:
    try:
        return get_task(task_id)
    except TaskNotFoundError as error:
        raise HTTPException(status_code=404, detail="Task not found.") from error


def _questions(contract: dict) -> list[dict]:
    try:
        from guard.intent_gap import find_gaps
    except ImportError:
        return []
    questions = find_gaps(contract)
    return list(questions)[:3]


@app.post("/tasks")
def create_task_endpoint(request: TaskCreateRequest) -> dict:
    try:
        contract = parse_contract(request.sentence).model_dump(mode="json", by_alias=True)
    except Exception:
        if DEMO_CONTRACT is None:
            raise HTTPException(status_code=503, detail="Contract parser is unavailable.")
        contract = DEMO_CONTRACT.model_dump(mode="json", by_alias=True)
        contract["source"] = "fallback"
    questions = _questions(contract)
    status = "awaiting_answers" if questions else "awaiting_confirmation"
    task_id = create_task(request.sentence, request.scenario, contract, request.guard_enabled, status)
    audit(task_id, "contract_drafted", {"contract": contract, "questions": questions})
    return {"task_id": task_id, "draft_contract": contract, "questions": questions}


@app.post("/tasks/{task_id}/answers")
def answers(task_id: str, request: AnswersRequest) -> dict:
    task = _task_or_404(task_id)
    if task["status"] != "awaiting_answers":
        raise HTTPException(status_code=409, detail="Task is not awaiting answers.")
    contract = task["contract"]
    try:
        from guard.intent_gap import apply_answers
    except ImportError:
        updated = contract
    else:
        updated = apply_answers(contract, request.answers)
    update_contract(task_id, updated)
    audit(task_id, "answers_recorded", {"answers": request.answers})
    try:
        transition(task_id, "awaiting_confirmation")
    except InvalidTransitionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"contract": updated}


@app.post("/tasks/{task_id}/confirm")
def confirm(task_id: str, request: ConfirmRequest) -> dict:
    task = _task_or_404(task_id)
    if task["status"] != "awaiting_confirmation":
        raise HTTPException(status_code=409, detail="Task is not awaiting confirmation.")
    contract_data = request.contract or task["contract"]
    try:
        contract = Contract.model_validate(contract_data)
        if contract.max_total <= 0:
            raise ValueError("max_total must be greater than zero.")
    except Exception as error:
        audit(task_id, "contract_rejected", {"error": str(error)})
        raise HTTPException(status_code=422, detail=f"Invalid contract: {error}") from error
    normalized = contract.model_dump(mode="json", by_alias=True)
    changed_after_confirmation = task["contract_confirmed"] and task["contract"] != normalized
    update_contract(task_id, normalized, confirmed=True)
    if changed_after_confirmation:
        return {"status": "awaiting_confirmation"}
    audit(task_id, "contract_confirmed", {"contract": normalized})
    return {"status": task["status"]}


@app.get("/tasks/{task_id}")
def task(task_id: str) -> dict:
    value = _task_or_404(task_id)
    value["decision_history"] = [event for event in task_events(task_id) if event["type"] == "decision"]
    value["audit_events"] = task_events(task_id)
    return value


@app.get("/tasks/{task_id}/events")
def events(task_id: str) -> StreamingResponse:
    _task_or_404(task_id)

    def stream():
        last_id = 0
        last_heartbeat = time.monotonic()
        while True:
            rows = task_events(task_id, last_id)
            for row in rows:
                last_id = row["id"]
                yield f"id: {row['id']}\nevent: {row['type']}\ndata: {json.dumps(row)}\n\n"
            if time.monotonic() - last_heartbeat >= 15:
                yield ": heartbeat\n\n"
                last_heartbeat = time.monotonic()
            time.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/health")
def health() -> dict:
    try:
        with connection() as db:
            db.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    return {"replay": os.getenv("REPLAY") == "1", "tinyfish_configured": bool(os.getenv("TINYFISH_API_KEY")), "db_ok": db_ok}


@app.post("/stage")
def stage(request: StageRequest) -> dict:
    """Stage a cart, apply the local guard when available, and return both."""

    task_id = str(uuid4())
    cart_url = str(request.cart_url)
    log_event(task_id, "stage_requested", {"cart_url": cart_url, "scenario": request.scenario})
    if not _GUARD_AVAILABLE or DEMO_CONTRACT is None or check is None:
        decision = {"result": "block", "reasons": ["Guard package is unavailable."], "remove_item_ids": [], "flags": [], "differing_fields": []}
        log_event(task_id, "guard_stubbed", decision)
        raise HTTPException(status_code=503, detail=decision)
    try:
        cart, hidden_text = stage_cart_details(cart_url, DEMO_CONTRACT, scenario=request.scenario)
    except StagingError as error:
        log_event(task_id, "stage_failed", {"error": str(error)})
        raise HTTPException(status_code=502, detail=str(error)) from error
    log_event(task_id, "cart_staged", cart.model_dump(mode="json"))
    decision = check(DEMO_CONTRACT, cart, hidden_text)
    log_event(task_id, "cart_checked", decision.model_dump(mode="json"))
    return {"cart": cart.model_dump(mode="json"), "decision": decision.model_dump(mode="json")}
