"""HTTP API for staging and checking a demo cart."""

from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl

from .log import log_event
from .staging import StagingError, stage_cart_details

try:
    from guard.checker import check
    from guard.contract_parser import DEMO_CONTRACT

    _GUARD_AVAILABLE = True
except ImportError:
    check = None
    DEMO_CONTRACT = None
    _GUARD_AVAILABLE = False


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


@app.post("/stage")
def stage(request: StageRequest) -> dict:
    """Stage a cart, apply the local guard when available, and return both."""

    task_id = str(uuid4())
    cart_url = str(request.cart_url)
    log_event(task_id, "stage_requested", {"cart_url": cart_url, "scenario": request.scenario})
    if not _GUARD_AVAILABLE or DEMO_CONTRACT is None or check is None:
        decision = {"result": "allow", "reasons": ["Guard package is unavailable."], "remove_item_ids": [], "flags": []}
        log_event(task_id, "guard_stubbed", decision)
        return {"cart": None, "decision": decision}
    try:
        cart, hidden_text = stage_cart_details(cart_url, DEMO_CONTRACT, scenario=request.scenario)
    except StagingError as error:
        log_event(task_id, "stage_failed", {"error": str(error)})
        raise HTTPException(status_code=502, detail=str(error)) from error
    log_event(task_id, "cart_staged", cart.model_dump(mode="json"))
    decision = check(DEMO_CONTRACT, cart, hidden_text)
    log_event(task_id, "cart_checked", decision.model_dump(mode="json"))
    return {"cart": cart.model_dump(mode="json"), "decision": decision.model_dump(mode="json")}
