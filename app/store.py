"""SQLite authority for reviewed tasks, versioned carts, approvals and orders."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import hashlib
import json
import secrets
import sqlite3
from pathlib import Path
from uuid import uuid4

from guard.intent_gap import apply_answers, find_gaps
from guard.models import Cart, Contract, Decision, OrderRequest

from .catalog import BookingState, make_cart


class WorkflowError(RuntimeError):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def canonical(value) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS carts (
                    id TEXT PRIMARY KEY, version INTEGER NOT NULL,
                    state TEXT NOT NULL, cart TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS approvals (
                    token TEXT PRIMARY KEY, task_id TEXT NOT NULL, cart_id TEXT NOT NULL,
                    version INTEGER NOT NULL, contract_hash TEXT NOT NULL, cart_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY, approval TEXT UNIQUE NOT NULL, snapshot TEXT NOT NULL);
                CREATE TRIGGER IF NOT EXISTS orders_no_update BEFORE UPDATE ON orders
                    BEGIN SELECT RAISE(ABORT, 'Orders are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS orders_no_delete BEFORE DELETE ON orders
                    BEGIN SELECT RAISE(ABORT, 'Orders are immutable'); END;
            """)
            db.execute("INSERT OR IGNORE INTO metadata VALUES ('storage_id', ?)", (str(uuid4()),))

    def storage_id(self):
        with self.connection() as db:
            return db.execute("SELECT value FROM metadata WHERE key='storage_id'").fetchone()[0]

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _task(self, db, task_id):
        row = db.execute("SELECT body FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise WorkflowError("Task not found.", 404)
        return json.loads(row[0])

    def _save_task(self, db, task):
        db.execute("INSERT OR REPLACE INTO tasks VALUES (?,?)", (task["task_id"], canonical(task)))

    def _event(self, db, task, status, detail):
        task["status"] = status
        task["events"].append({"status": status, "at": now(), "detail": detail})
        self._save_task(db, task)

    def create_task(self, sentence: str, contract: Contract, scenario: str):
        # A fallback may have missed explicit preferences: ask about all nulls.
        questions = find_gaps(contract, "" if contract.source == "fallback" else sentence)
        # Never silently discard an explicit preference that a parser left null.
        known = {q["key"] for q in questions}
        questions += [q for q in find_gaps(contract, "") if q["key"] not in known]
        task = {"task_id": str(uuid4()), "sentence": sentence, "scenario": scenario,
                "draft_contract": contract.model_dump(mode="json"), "contract": contract.model_dump(mode="json"),
                "questions": questions, "answers": {}, "reviewed": False, "events": [],
                "status": "awaiting_answers" if questions else "awaiting_confirmation"}
        with self.connection() as db:
            self._save_task(db, task)
        return task

    def task(self, task_id):
        with self.connection() as db:
            return self._task(db, task_id)

    def answer(self, task_id, answers):
        with self.connection() as db:
            task = self._task(db, task_id)
            if task["reviewed"]:
                raise WorkflowError("Create a new task to change reviewed instructions.")
            if set(answers) - {q["key"] for q in task["questions"]}:
                raise WorkflowError("Unexpected clarification answer.", 422)
            try:
                contract = apply_answers(task["contract"], answers)
            except ValueError as error:
                raise WorkflowError(str(error), 422) from error
            task["contract"] = contract.model_dump(mode="json")
            task["answers"].update(answers)
            status = "awaiting_confirmation" if self._answered(task) else "awaiting_answers"
            self._event(db, task, status, "Clarification answers saved; review is still required.")
            return task

    @staticmethod
    def _answered(task):
        return all(q["key"] in task["answers"] for q in task["questions"])

    def review(self, task_id, contract: Contract | None = None):
        with self.connection() as db:
            task = self._task(db, task_id)
            if not self._answered(task):
                raise WorkflowError("Answer every clarification question before authorization.")
            if task["reviewed"]:
                if contract is not None and canonical(contract) != canonical(task["contract"]):
                    raise WorkflowError("Reviewed instructions are immutable; create a new task.")
                return task
            if contract is not None:
                task["contract"] = contract.model_dump(mode="json")
            task["reviewed"] = True
            self._event(db, task, "staging", "User explicitly reviewed and authorized this contract.")
            return task

    def event(self, task_id, status, detail, **fields):
        with self.connection() as db:
            task = self._task(db, task_id)
            task.update(fields)
            self._event(db, task, status, detail)
            return task

    def _cart(self, db, cart_id):
        row = db.execute("SELECT * FROM carts WHERE id=?", (cart_id,)).fetchone()
        if row is None:
            raise WorkflowError("Cart not found.", 404)
        return {"cart_id": row["id"], "version": row["version"],
                "state": json.loads(row["state"]), "cart": json.loads(row["cart"])}

    def cart(self, cart_id):
        with self.connection() as db:
            return self._cart(db, cart_id)

    def save_cart(self, state: BookingState, cart_id=None):
        with self.connection() as db:
            version = 1
            if cart_id is not None:
                existing = self._cart(db, cart_id)
                if canonical(existing["state"]) == canonical(state):
                    return existing
                version = existing["version"] + 1
            else:
                cart_id = "cart_" + uuid4().hex
            cart = make_cart(cart_id, state)
            db.execute("INSERT OR REPLACE INTO carts VALUES (?,?,?,?)",
                       (cart_id, version, canonical(state), canonical(cart)))
            return self._cart(db, cart_id)

    @staticmethod
    def _reviewed(task):
        if not task["reviewed"] or not Store._answered(task):
            raise WorkflowError("The contract and every clarification answer must be reviewed first.")
        return Contract.model_validate(task["contract"])

    def evaluate(self, task_id, cart_id, evidence: Cart, checker):
        if not callable(checker):
            raise WorkflowError("Checker unavailable; no approval was issued.", 503)
        with self.connection() as db:
            task = self._task(db, task_id)
            contract = self._reviewed(task)
            if task.get("order_id"):
                raise WorkflowError("This task already has a confirmed order; create a new task for another booking.")
            current = self._cart(db, cart_id)
            cart = Cart.model_validate(current["cart"])
            if canonical(evidence) != canonical(cart):
                raise WorkflowError("Browser extraction disagrees with the authoritative server cart; no approval issued.")
            decision = Decision.model_validate(checker(contract, cart))
            # Supersede earlier approvals even when a new check returns ASK/BLOCK.
            db.execute("DELETE FROM approvals WHERE task_id=? AND cart_id=? AND token NOT IN (SELECT approval FROM orders)",
                       (task_id, cart_id))
            approval = None
            if decision.result == "allow":
                approval = secrets.token_urlsafe(32)
                db.execute("INSERT INTO approvals VALUES (?,?,?,?,?,?)",
                           (approval, task_id, cart_id, current["version"], digest(contract), digest(cart)))
            task["cart_id"] = cart_id
            task["decision"] = decision.model_dump(mode="json")
            self._event(db, task, {"allow": "allowed", "block": "blocked", "ask": "awaiting_answers"}[decision.result],
                        "Authoritative cart checked against independent browser extraction.")
            return {"decision": decision.model_dump(mode="json"), "approval": approval,
                    "cart_id": cart_id, "version": current["version"]}

    def confirm(self, task_id, cart_id, approval, outgoing: OrderRequest, checker, request_checker, host):
        if not callable(checker) or not callable(request_checker):
            raise WorkflowError("Checker unavailable; order creation is disabled.", 503)
        with self.connection() as db:
            permit = db.execute("SELECT * FROM approvals WHERE token=?", (approval,)).fetchone()
            if permit is None or permit["task_id"] != task_id or permit["cart_id"] != cart_id:
                raise WorkflowError("A valid server-issued approval is required.")
            previous = db.execute("SELECT snapshot FROM orders WHERE approval=?", (approval,)).fetchone()
            if previous is not None:
                snapshot = json.loads(previous[0])
                if canonical(outgoing) != canonical(snapshot["order_request"]):
                    raise WorkflowError("A repeated confirmation must match the original operation.")
                return snapshot
            task = self._task(db, task_id)
            contract = self._reviewed(task)
            if task.get("order_id"):
                raise WorkflowError("This task already has a confirmed simulated order.")
            if task["status"] not in {"allowed", "committing"}:
                raise WorkflowError("This task is paused, blocked or failed; run a fresh check before confirmation.")
            current = self._cart(db, cart_id)
            cart = Cart.model_validate(current["cart"])
            if (current["version"] != permit["version"] or digest(cart) != permit["cart_hash"]
                    or digest(contract) != permit["contract_hash"]):
                raise WorkflowError("Cart or contract changed after approval; extract and check again.")
            if Decision.model_validate(checker(contract, cart)).result != "allow":
                raise WorkflowError("The current cart no longer has an ALLOW decision.")
            if Decision.model_validate(request_checker(contract, outgoing, host)).result != "allow":
                raise WorkflowError("The actual outgoing order request was rejected.")
            expected = {"cart_id": cart_id, "items": [{"id": item.id, "price": item.price} for item in cart.items],
                        "total": cart.total, "fields": {}}
            if canonical(outgoing) != canonical(expected):
                raise WorkflowError("The outgoing request differs from the approved cart.")
            snapshot = {"order_id": "order_" + uuid4().hex, "simulated": True, "confirmed_at": now(),
                        "task_id": task_id, "cart_version": current["version"], "cart": cart.model_dump(mode="json"),
                        "contract": contract.model_dump(mode="json"), "order_request": expected,
                        "cart_hash": digest(cart), "contract_hash": digest(contract)}
            db.execute("INSERT INTO orders VALUES (?,?,?)", (snapshot["order_id"], approval, canonical(snapshot)))
            task["order_id"] = snapshot["order_id"]
            self._event(db, task, "done", "One immutable simulated order created atomically.")
            return snapshot

    def order(self, order_id):
        with self.connection() as db:
            row = db.execute("SELECT snapshot FROM orders WHERE id=?", (order_id,)).fetchone()
            if row is None:
                raise WorkflowError("No confirmed server order exists.", 404)
            return json.loads(row[0])
