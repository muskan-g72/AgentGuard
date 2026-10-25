"""Local simulated booking API and same-origin demo website."""

from __future__ import annotations

import logging
import os
import json
import time
from functools import partial
from pathlib import Path
from typing import Literal
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from guard.contract_parser import DEMO_CONTRACT, parse_contract
from guard.food_models import FoodContract, WalletEntry
from guard.models import Cart, Contract, Message, OrderRequest

from .catalog import BookingState
from .config import Settings
from .release import release
from .store import Store, WorkflowError

try:
    from guard.checker import check
    from guard.request_check import check_request
except ImportError:
    check = check_request = None

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
logger = logging.getLogger("agentguard")


class HealthcheckTrustedHostMiddleware(TrustedHostMiddleware):
    """Keep the strict host allowlist while permitting Render's health probe."""

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") == "/healthz":
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


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
    wallet: list[WalletEntry] = []
    scenario: str | None = None
    replay: bool | None = None


class FoodRunRequest(Message):
    task_id: str
    guard_off: bool = False
    scenario: str | None = None
    replay: bool | None = None
    wallet: list[WalletEntry] = []


def create_app(database: str | Path | None = None) -> FastAPI:
    settings = Settings.load(ROOT, database)
    version = release()
    instance_id = str(uuid4())
    api = FastAPI(title="AgentGuard simulated booking")
    api.add_middleware(HealthcheckTrustedHostMiddleware, allowed_hosts=sorted(settings.allowed_hosts))
    api.state.store = Store(settings.database)
    api.state.settings = settings
    from .food_workflow import TinyFishFoodBrowser
    api.state.food_browser_factory = TinyFishFoodBrowser

    @api.middleware("http")
    async def no_stale_authority(request, call_next):
        response = await call_next(request)
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

    def require_live_key():
        if os.getenv("REPLAY") != "1" and not os.getenv("TINYFISH_API_KEY"):
            raise WorkflowError("Live agent execution requires TINYFISH_API_KEY; replay remains available with REPLAY=1.", 503)

    @api.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @api.get("/health")
    def health():
        with store().connection() as db:
            db.execute("SELECT 1").fetchone()
        return {"replay": os.getenv("REPLAY") == "1", "tinyfish_configured": bool(os.getenv("TINYFISH_API_KEY")),
                "receipt_configured": bool(os.getenv("RECEIPT_KEY")),
                "db_ok": True, "checker_available": callable(check) and callable(check_request),
                "confirmation_protected": True, "release_id": version["release_id"], "instance_id": instance_id,
                "public_origin": settings.public_origin, "agent_runs_enabled": settings.agent_runs_enabled,
                "storage": {"kind": "sqlite", "durable": settings.durable, "storage_id": store().storage_id()}}

    @api.get("/version")
    def deployed_version():
        return version

    @api.post("/tasks")
    def create_task(body: TaskCreate):
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
        return store().create_task(body.sentence, draft, body.scenario)

    @api.get("/tasks/{task_id}")
    def task(task_id: str):
        return store().task(task_id)

    @api.post("/tasks/{task_id}/answers")
    def answers(task_id: str, body: Answers):
        return store().answer(task_id, body.answers)

    @api.post("/tasks/{task_id}/confirm")
    def review(task_id: str, body: Review):
        guard()
        store().review(task_id, body.contract)
        return store().task(task_id)

    @api.get("/tasks/{task_id}/events")
    def events(task_id: str, after_id: int = 0, follow: bool = False):
        store().task(task_id)

        def stream():
            cursor = after_id
            idle = 0
            while True:
                rows = [event for event in store().task(task_id)["events"] if event["id"] > cursor]
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
    def receipt(task_id: str):
        return store().receipt(task_id)

    @api.get("/tasks/{task_id}/receipt/verify")
    def verify_receipt(task_id: str):
        return store().verify_receipt(task_id)

    @api.post("/api/carts")
    def create_cart(body: BookingState):
        return store().save_cart(body)

    @api.get("/api/catalog")
    def catalog():
        from .catalog import TICKETS
        return {"tickets": TICKETS, "extras": [
            {"id": "x1", "type": "insurance", "price": 250},
            {"id": "m1", "type": "meal", "price": 100},
        ]}

    @api.get("/api/carts/{cart_id}")
    def cart(cart_id: str):
        return store().cart(cart_id)

    @api.put("/api/carts/{cart_id}")
    def update_cart(cart_id: str, body: BookingState):
        return store().save_cart(body, cart_id)

    @api.post("/api/carts/{cart_id}/check")
    def evaluate(cart_id: str, body: Evidence):
        return store().evaluate(body.task_id, cart_id, body.cart, guard())

    @api.post("/api/carts/{cart_id}/confirm")
    def confirm(cart_id: str, body: Confirmation, request: Request):
        guard()
        return store().confirm(body.task_id, cart_id, body.approval, body.order_request,
                               check, partial(check_request, allowed_hosts=settings.allowed_hosts), request.url.hostname)

    @api.get("/api/orders/{order_id}")
    def order(order_id: str):
        return store().order(order_id)

    @api.post("/stage")
    def stage(body: StageRequest):
        if not settings.agent_runs_enabled:
            raise WorkflowError("Agent execution is operator-local; the public server does not run paid agents.", 403)
        require_live_key()
        guard()
        current = store().task(body.task_id)
        contract = Store._reviewed(current)
        from .staging import StagingError, stage_cart_details
        try:
            cart, hidden = stage_cart_details(body.cart_url or os.getenv("DEMO_URL", "https://demo-booking-tau.vercel.app"),
                                               contract, scenario=body.scenario or current["scenario"])
            decision = check(contract, cart, hidden)
        except (StagingError, ValidationError, OSError, ValueError) as error:
            store().event(body.task_id, "failed", "Staging failed; no approval or order issued.")
            raise HTTPException(502, "Staging failed; inspect the local staging command for safe details.") from error
        return {"mode": "fixture_replay" if os.getenv("REPLAY") == "1" else "live_agent",
                "cart": cart.model_dump(mode="json"), "decision": decision.model_dump(mode="json"),
                "approval": None, "note": "Agent-supplied evidence alone never issues a confirmation approval."}

    @api.post("/tasks/{task_id}/run")
    def run(task_id: str, body: RunRequest):
        if not settings.agent_runs_enabled:
            raise WorkflowError("Agent execution is operator-local; use the public checkout for simulated bookings.", 403)
        if body.mode == "live":
            require_live_key()
        guard()
        Store._reviewed(store().task(task_id))
        from .workflow import run_task
        return run_task(store(), task_id, body.mode, body.cart_url, body.confirm)

    @api.post("/food/compare")
    def food_compare(body: FoodCompareRequest):
        from .food_compare import compare_all, rank_options

        comparison = compare_all(body.platform_urls, replay=body.replay)
        ranking = rank_options(comparison.options, body.contract, body.wallet)

        def render(option, detail):
            return {**option.model_dump(mode="json"), **detail}

        dropped = [
            {"option": render(entry.option, ranking.rejected_details["|".join((entry.option.platform, entry.option.restaurant, entry.option.dish, entry.option.url))]), "reasons": entry.reasons}
            for entry in ranking.rejected
        ]
        task = store().create_food_task(
            body.contract,
            ranking.ranked[0] if ranking.ranked else None,
            ranked=ranking.ranked,
            dropped=dropped,
            scenario=body.scenario,
            wallet=body.wallet,
        )
        mode = "fixture_replay" if (body.replay if body.replay is not None else os.getenv("REPLAY") == "1") else "live_agent"
        return {
            "task_id": task["task_id"],
            "ranked": [render(option, ranking.details["|".join((option.platform, option.restaurant, option.dish, option.url))]) for option in ranking.ranked],
            "dropped": dropped,
            "recommended": render(ranking.ranked[0], ranking.details["|".join((ranking.ranked[0].platform, ranking.ranked[0].restaurant, ranking.ranked[0].dish, ranking.ranked[0].url))]) if ranking.ranked else None,
            "failed_platforms": comparison.failures,
            "mode": mode,
            "replay_available": True,
            "value_formula": "taste_score / effective_price",
            "wallet_scope": "comparison_and_ranking_only",
            "wallet_applied_to_staging": False,
        }

    @api.post("/food/run")
    def food_run(body: FoodRunRequest):
        from .food_workflow import run_food_task

        task = store().food_task(body.task_id)
        if task.get("recommended") is None:
            raise WorkflowError("No food option survived comparison; staging cannot start.", 409)
        stored_wallet = task.get("wallet", [])
        requested_wallet = [entry.model_dump(mode="json") for entry in body.wallet]
        if requested_wallet and requested_wallet != stored_wallet:
            raise WorkflowError("Wallet differs from the comparison request; compare again before staging.", 409)
        if requested_wallet or stored_wallet:
            store().event(body.task_id, task["status"], "Wallet savings apply to comparison and ranking only in replay; staged cart evidence has no voucher line.", event_type="food_wallet_comparison_only", wallet=stored_wallet)
        if body.guard_off:
            store().event(
                body.task_id, task["status"], "Guard-off mode enabled for the before/after food demo.",
                event_type="food_guard_off_enabled", guard_off=True,
            )
        return run_food_task(store(), body.task_id, api.state.food_browser_factory(), scenario=body.scenario)

    assets = {"index.html", "checkout.html", "confirmation.html", "app.js", "checkout.js", "styles.css"}
    food_pages = {"index.html", "dish.html", "checkout.html", "confirmation.html"}
    food_platforms = {"foodhub", "quickbite", "dinedash"}

    @api.get("/")
    def index():
        return FileResponse(ROOT / "index.html")

    @api.get("/{asset}")
    def asset(asset: str):
        if asset not in assets:
            raise HTTPException(404)
        return FileResponse(ROOT / asset)

    @api.get("/data/food.json")
    def food_catalog_asset():
        return FileResponse(ROOT / "data" / "food.json", media_type="application/json")

    @api.get("/food-demo/images/{image}")
    def food_demo_image(image: str):
        image_path = ROOT / "food-demo" / "images" / image
        if not image_path.is_file():
            raise HTTPException(404)
        return FileResponse(image_path)

    @api.get("/food-demo/{asset}")
    def food_demo_asset(asset: str):
        allowed = {"index.html", "site.mjs", "logic.mjs", "styles.css", "plate.svg"}
        if asset not in allowed:
            raise HTTPException(404)
        return FileResponse(ROOT / "food-demo" / asset)

    @api.get("/food-demo/")
    def food_demo_index():
        return FileResponse(ROOT / "food-demo" / "index.html")

    @api.get("/food-demo")
    def food_demo_bare():
        return FileResponse(ROOT / "food-demo" / "index.html")

    @api.get("/compare/")
    def food_compare_page():
        return FileResponse(ROOT / "food-demo" / "compare" / "index.html")

    @api.get("/compare")
    def food_compare_page_bare():
        return FileResponse(ROOT / "food-demo" / "compare" / "index.html")

    @api.get("/compare/{asset}")
    def food_compare_asset(asset: str):
        if asset not in {"compare.mjs"}:
            raise HTTPException(404)
        return FileResponse(ROOT / "food-demo" / "compare" / asset)

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
