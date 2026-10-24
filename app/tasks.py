"""SQLite-backed task state and fail-closed status transitions."""

from __future__ import annotations

import json
import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "events.db"
ALLOWED_TRANSITIONS = {
    "awaiting_answers": {"awaiting_confirmation"},
    "awaiting_confirmation": {"staging", "failed"},
    "staging": {"checking", "failed"},
    "checking": {"allowed", "blocked", "failed"},
    "blocked": {"fixing", "failed"},
    "fixing": {"checking", "failed"},
    "allowed": {"committing"},
    "committing": {"done", "failed"},
    "done": set(),
    "failed": set(),
}


class TaskNotFoundError(KeyError):
    pass


class InvalidTransitionError(ValueError):
    pass


class ConfirmationGateError(ValueError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def connection() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(exist_ok=True)
    db = sqlite3.connect(DATABASE_PATH)
    db.row_factory = sqlite3.Row
    db.execute(
        """CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY, sentence TEXT NOT NULL, scenario TEXT NOT NULL,
        contract_json TEXT NOT NULL, guard_enabled INTEGER NOT NULL, status TEXT NOT NULL,
        cart_json TEXT, decision_json TEXT, cart_hash TEXT, fix_attempts INTEGER NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, contract_confirmed INTEGER NOT NULL DEFAULT 0)"""
    )
    columns = {row[1] for row in db.execute("PRAGMA table_info(tasks)")}
    if "contract_confirmed" not in columns:
        db.execute("ALTER TABLE tasks ADD COLUMN contract_confirmed INTEGER NOT NULL DEFAULT 0")
    db.execute(
        """CREATE TABLE IF NOT EXISTS audit_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, ts TEXT NOT NULL,
        type TEXT NOT NULL, payload_json TEXT NOT NULL)"""
    )
    return db


def audit(task_id: str, event_type: str, payload: Any) -> int:
    with connection() as db:
        cursor = db.execute(
            "INSERT INTO audit_events (task_id, ts, type, payload_json) VALUES (?, ?, ?, ?)",
            (task_id, _now(), event_type, json.dumps(payload)),
        )
        return int(cursor.lastrowid)


def create_task(sentence: str, scenario: str, contract: dict[str, Any], guard_enabled: bool, status: str) -> str:
    task_id = str(uuid4())
    now = _now()
    with connection() as db:
        db.execute(
            """INSERT INTO tasks (id, sentence, scenario, contract_json, guard_enabled, status,
            cart_json, decision_json, cart_hash, fix_attempts, created_at, updated_at, contract_confirmed)
            VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, 0, ?, ?, 0)""",
            (task_id, sentence, scenario, json.dumps(contract), int(guard_enabled), status, now, now),
        )
    audit(task_id, "task_created", {"status": status, "scenario": scenario})
    return task_id


def get_task(task_id: str) -> dict[str, Any]:
    with connection() as db:
        row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise TaskNotFoundError(task_id)
    task = dict(row)
    for key in ("contract_json", "cart_json", "decision_json"):
        value = task.pop(key)
        task[key.removesuffix("_json")] = json.loads(value) if value is not None else None
    task["guard_enabled"] = bool(task["guard_enabled"])
    task["contract_confirmed"] = bool(task["contract_confirmed"])
    return task


def task_events(task_id: str, after_id: int = 0) -> list[dict[str, Any]]:
    with connection() as db:
        rows = db.execute(
            "SELECT id, task_id, ts, type, payload_json FROM audit_events WHERE task_id = ? AND id > ? ORDER BY id",
            (task_id, after_id),
        ).fetchall()
    return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]


def transition(task_id: str, new_status: str) -> dict[str, Any]:
    task = get_task(task_id)
    current = task["status"]
    confirmation_missing = new_status == "staging" and not any(
        event["type"] == "contract_confirmed" for event in task_events(task_id)
    )
    if new_status not in ALLOWED_TRANSITIONS.get(current, set()) or confirmation_missing:
        message = f"Illegal task status transition: {current} -> {new_status}."
        audit(task_id, "transition_rejected", {"from": current, "to": new_status, "error": message})
        raise InvalidTransitionError(message)
    with connection() as db:
        db.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?", (new_status, _now(), task_id))
    audit(task_id, "status_changed", {"from": current, "to": new_status})
    return get_task(task_id)


def update_contract(task_id: str, contract: dict[str, Any], *, confirmed: bool = False) -> None:
    task = get_task(task_id)
    changed_after_confirmation = task["contract_confirmed"] and task["contract"] != contract
    with connection() as db:
        db.execute("UPDATE tasks SET contract_json = ?, contract_confirmed = ?, updated_at = ? WHERE id = ?", (json.dumps(contract), int(confirmed and not changed_after_confirmation), _now(), task_id))
    if changed_after_confirmation:
        audit(task_id, "contract_unconfirmed", {"reason": "The stored contract changed."})


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def update_task(task_id: str, **fields: Any) -> None:
    allowed = {"cart_json", "decision_json", "cart_hash", "fix_attempts", "status", "contract_json", "contract_confirmed"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"Unsupported task fields: {sorted(unknown)}")
    if not fields:
        return
    fields["updated_at"] = _now()
    assignments = ", ".join(f"{key} = ?" for key in fields)
    with connection() as db:
        db.execute(f"UPDATE tasks SET {assignments} WHERE id = ?", (*fields.values(), task_id))


def save_cart(task_id: str, cart: Any) -> str:
    value = cart.model_dump(mode="json") if hasattr(cart, "model_dump") else cart
    encoded = canonical_json(value)
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    update_task(task_id, cart_json=encoded, cart_hash=digest)
    return digest


def save_decision(task_id: str, decision: Any) -> None:
    value = decision.model_dump(mode="json") if hasattr(decision, "model_dump") else decision
    update_task(task_id, decision_json=canonical_json(value))


def increment_fix_attempts(task_id: str) -> int:
    task = get_task(task_id)
    attempts = task["fix_attempts"] + 1
    update_task(task_id, fix_attempts=attempts)
    return attempts


def require_confirmed(task: dict[str, Any]) -> None:
    if task["status"] != "awaiting_confirmation" or not task["contract_confirmed"]:
        raise ConfirmationGateError("Task requires a confirmed contract before staging.")
