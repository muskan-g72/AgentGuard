"""Local simulated booking API and same-origin demo website."""

from __future__ import annotations

import logging
import os
import json
import time
from functools import partial
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from guard.contract_parser import DEMO_CONTRACT, parse_contract
from guard.food_models import FoodContract
from guard.models import Cart, Contract, Message, OrderRequest

from .catalog import BookingState
from .config import Settings
from .release import release
from .session import SessionSigner
from .store import Store, WorkflowError

try:
    from guard.checker import check
    from guard.request_check import check_request
except ImportError:
    check = check_request = None

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
logger = logging.getLogger("agentguard")


class TaskCreate(Message):
    sentence: str
    scenario: Literal["s1", "s2", "s3", "s4", "s5", "s6"] = "s1"
    guard_enabled: bool = True
    draft_contract: Contract | None = None


class Answers(Message):
    answers: dict[str, str]


class Review(Message):
    contract: Contract | None = None


class Evidence(Message):
    task_id: str
    cart: Cart


class Confirmation(Message):
    task_id: str
    approval: str
    order_request: OrderRequest


class StageRequest(Message):
    task_id: str
    cart_url: str | None = None
    scenario: str | None = None


class RunRequest(Message):
    mode: Literal["local", "replay", "live"] = "local"
    cart_url: str | None = None
    confirm: bool = False


class FoodCompareRequest(Message):
    contract: FoodContract
    platform_urls: list[str]
    scenario: str | None = None


class FoodRunRequest(Message):
    task_id: str
    scenario: str | None = None


class FoodConfirmRequest(Message):
    contract: FoodContract | None = None


def create_app(database: str | Path | None = None) -> FastAPI:
    settings = Settings.load(ROOT, database)
    version = release()
    instance_id = str(uuid4())
    api = FastAPI(title="AgentGuard simulated booking")
    api.add_middleware(TrustedHostMiddleware, allowed_hosts=sorted(settings.allowed_hosts))
    api.state.store = Store(settings.database)
    api.state.settings = settings
    signer = SessionSigner(settings.session_secret)
    from .food_workflow import TinyFishFoodBrowser
    api.state.food_browser_factory = TinyFishFoodBrowser

    @api.middleware("http")
    async def no_stale_authority(request, call_next):
        session_id = signer.verify(request.cookies.get("agentguard_session"))
        new_session = session_id is None
        if new_session:
            session_id, session_cookie = signer.issue()
        request.state.session_id = session_id
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin:
                request_origin = f"{request.url.scheme}://{request.headers.get('host', '')}".rstrip("/")
                if origin.rstrip("/") not in {settings.public_origin, request_origin}:
                    return JSONResponse(status_code=403, content={"detail": "Cross-origin state change rejected."})
        response = await call_next(request)
        if new_session:
            response.set_cookie("agentguard_session", session_cookie, httponly=True,
                                samesite="lax", secure=settings.durable, path="/")
        response.headers["Cache-Control"] = "no-store"
        response.headers["CDN-Cache-Control"] = "no-store"
        response.headers["Vercel-CDN-Cache-Control"] = "no-store"
        response.headers["X-AgentGuard-Release"] = version["release_id"]
        return response

    @api.exception_handler(WorkflowError)
    async def workflow_error(request, error):
        return JSONResponse(status_code=error.status, content={"detail": str(error)})

    @api.exception_handler(Exception)
    async def unexpected_error(request, error):
        logger.error("Booking operation failed (%s)", type(error).__name__)
        return JSONResponse(status_code=503, content={"detail": "Booking operation failed; no new approval or order was issued."})

    def store() -> Store:
        return api.state.store

    def guard():
        if not callable(check) or not callable(check_request):
            raise WorkflowError("Checker unavailable; approvals and orders are disabled.", 503)
        return check

    @api.get("/health")
    def health():
        with store().connection() as db:
            db.execute("SELECT 1").fetchone()
        return {"replay": os.getenv("REPLAY") == "1", "tinyfish_configured": bool(os.getenv("TINYFISH_API_KEY")),
                "receipt_configured": bool(os.getenv("RECEIPT_KEY")),
                "session_configured": (bool(os.getenv("AGENTGUARD_SESSION_SECRET")) if settings.durable else True),
                "db_ok": True, "checker_available": callable(check) and callable(check_request),
                "confirmation_protected": True, "release_id": version["release_id"], "instance_id": instance_id,
                "public_origin": settings.public_origin, "agent_runs_enabled": settings.agent_runs_enabled,
                "storage": {"kind": "sqlite", "durable": settings.durable, "storage_id": store().storage_id()}}

    @api.get("/version")
    def deployed_version():
        return version

    @api.post("/tasks")
    def create_task(body: TaskCreate, request: Request):
        guard()
        if not body.guard_enabled:
            raise WorkflowError("The confirmation guard cannot be disabled.", 422)
        if body.draft_contract is None:
            try:
                draft = parse_contract(body.sentence)
            except Exception:
                draft = DEMO_CONTRACT.model_copy(deep=True)
        else:
            draft = body.draft_contract
        return store().create_task(body.sentence, draft, body.scenario, request.state.session_id)

    @api.get("/tasks/{task_id}")
    def task(task_id: str, request: Request):
        return store().task(task_id, request.state.session_id)

    @api.post("/tasks/{task_id}/answers")
    def answers(task_id: str, body: Answers, request: Request):
        return store().answer(task_id, body.answers, request.state.session_id)

    @api.post("/tasks/{task_id}/confirm")
    def review(task_id: str, body: Review, request: Request):
        guard()
        store().review(task_id, body.contract, request.state.session_id)
        return store().task(task_id, request.state.session_id)

    @api.get("/tasks/{task_id}/events")
    def events(task_id: str, request: Request, after_id: int = 0, follow: bool = False):
        store().task(task_id, request.state.session_id)

        def stream():
            cursor = after_id
            idle = 0
            while True:
                rows = [event for event in store().task(task_id, request.state.session_id)["events"] if event["id"] > cursor]
                for event in rows:
                    cursor = event["id"]
                    yield ("id: " + str(cursor) + "\n" + "event: " + event["type"] + "\n"
                           + "data: " + json.dumps(event, separators=(",", ":")) + "\n\n")
                if not follow:
                    return
                if rows:
                    idle = 0
                else:
                    idle += 1
                    yield ": keepalive\n\n"
                if idle >= 60:
                    return
                time.sleep(1)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @api.get("/tasks/{task_id}/receipt")
    def receipt(task_id: str, request: Request):
        return store().receipt(task_id, request.state.session_id)

    @api.get("/tasks/{task_id}/receipt/verify")
    def verify_receipt(task_id: str, request: Request):
        return store().verify_receipt(task_id, request.state.session_id)

    @api.post("/api/carts")
    def create_cart(body: BookingState, request: Request):
        return store().save_cart(body, owner_session_id=request.state.session_id)

    @api.get("/api/catalog")
    def catalog():
        from .catalog import TICKETS
        return {"tickets": TICKETS, "extras": [
            {"id": "x1", "type": "insurance", "price": 250},
            {"id": "m1", "type": "meal", "price": 100},
        ]}

    @api.get("/api/carts/{cart_id}")
    def cart(cart_id: str, request: Request):
        return store().cart(cart_id, request.state.session_id)

    @api.put("/api/carts/{cart_id}")
    def update_cart(cart_id: str, body: BookingState, request: Request):
        return store().save_cart(body, cart_id, request.state.session_id)

    @api.post("/api/carts/{cart_id}/check")
    def evaluate(cart_id: str, body: Evidence, request: Request):
        return store().evaluate(body.task_id, cart_id, body.cart, guard(), request.state.session_id)

    @api.post("/api/carts/{cart_id}/confirm")
    def confirm(cart_id: str, body: Confirmation, request: Request):
        guard()
        return store().confirm(body.task_id, cart_id, body.approval, body.order_request,
                               check, partial(check_request, allowed_hosts=settings.allowed_hosts), request.url.hostname,
                               request.state.session_id)

    @api.get("/api/orders/{order_id}")
    def order(order_id: str, request: Request):
        return store().order(order_id, request.state.session_id)

    @api.post("/stage")
    def stage(body: StageRequest, request: Request):
        if not settings.agent_runs_enabled:
            raise WorkflowError("Agent execution is operator-local; the public server does not run paid agents.", 403)
        guard()
        current = store().task(body.task_id, request.state.session_id)
        contract = Store._reviewed(current)
        from .staging import StagingError, stage_cart_details
        try:
            cart, hidden = stage_cart_details(body.cart_url or os.getenv("DEMO_URL", "https://demo-booking-tau.vercel.app"),
                                               contract, scenario=body.scenario or current["scenario"])
            decision = check(contract, cart, hidden)
        except (StagingError, ValidationError, OSError, ValueError) as error:
            store().event(body.task_id, "failed", "Staging failed; no approval or order issued.",
                          owner_session_id=request.state.session_id)
            raise HTTPException(502, "Staging failed; inspect the local staging command for safe details.") from error
        return {"mode": "fixture_replay" if os.getenv("REPLAY") == "1" else "live_agent",
                "cart": cart.model_dump(mode="json"), "decision": decision.model_dump(mode="json"),
                "approval": None, "note": "Agent-supplied evidence alone never issues a confirmation approval."}

    @api.post("/tasks/{task_id}/run")
    def run(task_id: str, body: RunRequest, request: Request):
        if not settings.agent_runs_enabled:
            raise WorkflowError("Agent execution is operator-local; use the public checkout for simulated bookings.", 403)
        guard()
        Store._reviewed(store().task(task_id, request.state.session_id))
        from .workflow import run_task
        # Keep compatibility with operator-local integrations that monkeypatch
        # the historical five-argument orchestrator while passing ownership to
        # the real implementation.
        import inspect
        parameters = inspect.signature(run_task).parameters
        if "owner_session_id" in parameters:
            return run_task(store(), task_id, body.mode, body.cart_url, body.confirm,
                            owner_session_id=request.state.session_id)
        return run_task(store(), task_id, body.mode, body.cart_url, body.confirm)

    @api.post("/food/compare")
    def food_compare(body: FoodCompareRequest, request: Request):
        from .food_compare import compare_all, rank_options

        if os.getenv("REPLAY") != "1" and not settings.agent_runs_enabled:
            raise WorkflowError("Live food agent runs are disabled on this deployment.", 403)
        if os.getenv("REPLAY") != "1":
            operator = os.getenv("AGENTGUARD_OPERATOR_TOKEN")
            if not operator or request.headers.get("X-AgentGuard-Operator") != operator:
                raise WorkflowError("Live food runs require operator authorization.", 403)
        for url in body.platform_urls:
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.hostname != "demo-booking-tau.vercel.app" or parsed.path.strip("/") not in {"foodhub", "quickbite", "dinedash"}:
                raise WorkflowError("Food platform URL is not an allowed simulated HTTPS page.", 422)

        comparison = compare_all(body.platform_urls)
        ranking = rank_options(comparison.options, body.contract)
        dropped = [
            {"option": entry.option.model_dump(mode="json"), "reasons": entry.reasons}
            for entry in ranking.rejected
        ]
        task = store().create_food_task(
            body.contract,
            ranking.ranked[0] if ranking.ranked else None,
            ranked=ranking.ranked,
            dropped=dropped,
            scenario=body.scenario, owner_session_id=request.state.session_id,
        )
        return {
            "task_id": task["task_id"],
            "ranked": [option.model_dump(mode="json") for option in ranking.ranked],
            "dropped": dropped,
            "recommended": ranking.ranked[0].model_dump(mode="json") if ranking.ranked else None,
            "failed_platforms": comparison.failures,
        }

    @api.post("/food/{task_id}/confirm")
    def food_confirm(task_id: str, body: FoodConfirmRequest, request: Request):
        task = store().food_task(task_id, request.state.session_id)
        return store().confirm_food(task_id, body.contract, request.state.session_id)

    @api.post("/food/run")
    def food_run(body: FoodRunRequest, request: Request):
        from .food_workflow import run_food_task

        if os.getenv("REPLAY") != "1" and not settings.agent_runs_enabled:
            raise WorkflowError("Live food agent runs are disabled on this deployment.", 403)
        if os.getenv("REPLAY") != "1":
            operator = os.getenv("AGENTGUARD_OPERATOR_TOKEN")
            if not operator or request.headers.get("X-AgentGuard-Operator") != operator:
                raise WorkflowError("Live food runs require operator authorization.", 403)

        task = store().food_task(body.task_id, request.state.session_id)
        if task.get("recommended") is None:
            raise WorkflowError("No food option survived comparison; staging cannot start.", 409)
        if not task.get("reviewed"):
            raise WorkflowError("Confirm the food contract before starting the guarded run.", 409)
        return run_food_task(store(), body.task_id, api.state.food_browser_factory(), scenario=body.scenario,
                             owner_session_id=request.state.session_id)

    assets = {"index.html", "checkout.html", "confirmation.html", "app.js", "checkout.js", "styles.css"}
    ui_assets = {"index.html", "styles.css", "icon.svg", "app.mjs", "api.mjs", "mock-api.mjs", "format.mjs"}
    food_pages = {"index.html", "dish.html", "checkout.html", "confirmation.html"}
    food_platforms = {"foodhub", "quickbite", "dinedash"}

    @api.get("/")
    def index():
        return FileResponse(ROOT / "ui" / "index.html")

    @api.get("/ui/")
    def dashboard():
        return FileResponse(ROOT / "ui" / "index.html")

    @api.get("/ui")
    def dashboard_bare():
        return FileResponse(ROOT / "ui" / "index.html")

    @api.get("/ui/{asset}")
    def dashboard_asset(asset: str):
        if asset not in ui_assets:
            raise HTTPException(404)
        return FileResponse(ROOT / "ui" / asset)

    @api.get("/train/")
    def train_index():
        return FileResponse(ROOT / "index.html")

    @api.get("/food/")
    def food_entry():
        return FileResponse(ROOT / "ui" / "index.html")

    @api.get("/train/{asset}")
    def train_asset(asset: str):
        if asset not in assets:
            raise HTTPException(404)
        return FileResponse(ROOT / asset)

    @api.get("/{asset}")
    def asset(asset: str):
        if asset not in assets:
            raise HTTPException(404)
        return FileResponse(ROOT / asset)

    @api.get("/data/food.json")
    def food_catalog_asset():
        return FileResponse(ROOT / "data" / "food.json", media_type="application/json")

    @api.get("/food-demo/{asset}")
    def food_demo_asset(asset: str):
        allowed = {"index.html", "site.mjs", "logic.mjs", "styles.css", "plate.svg"}
        if asset not in allowed:
            raise HTTPException(404)
        return FileResponse(ROOT / "food-demo" / asset)

    @api.get("/food-demo/images/{asset}")
    def food_demo_image(asset: str):
        if asset not in {"paneer-butter-masala.webp", "chicken-biryani.webp", "paneer-kathi-roll.webp", "veg-biryani.webp", "veg-thali.webp"}:
            raise HTTPException(404)
        return FileResponse(ROOT / "food-demo" / "images" / asset)

    @api.get("/food-demo/")
    def food_demo_index():
        return FileResponse(ROOT / "food-demo" / "index.html")

    @api.get("/food-demo")
    def food_demo_bare():
        return FileResponse(ROOT / "food-demo" / "index.html")

    @api.get("/{platform}/")
    def food_platform_index(platform: str):
        if platform not in food_platforms:
            raise HTTPException(404)
        return FileResponse(ROOT / platform / "index.html")

    @api.get("/{platform}")
    def food_platform_bare(platform: str):
        if platform not in food_platforms:
            raise HTTPException(404)
        return FileResponse(ROOT / platform / "index.html")

    @api.get("/{platform}/{asset}")
    def food_platform_asset(platform: str, asset: str):
        if platform not in food_platforms or asset not in food_pages:
            raise HTTPException(404)
        return FileResponse(ROOT / platform / asset)

    return api


app = create_app()
