"""SQLite task storage and append-only, hash-chained audit events."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from guard.request_check import canonical_json

TRANSITIONS = {
    "awaiting_answers": {"awaiting_confirmation"},
    "awaiting_confirmation": {"staging"},
    "staging": {"checking", "failed"},
    "checking": {"allowed", "blocked", "failed"},
    "blocked": {"fixing", "failed"},
    "fixing": {"checking", "failed"},
    "allowed": {"committing"},
    "committing": {"done", "failed"},
    "done": set(), "failed": set(),
}


def event_hash(event: dict) -> str:
    body = {key: event[key] for key in ("id", "ts", "type", "payload")}
    return hashlib.sha256((event["prev_hash"] + canonical_json(body)).encode("utf-8")).hexdigest()


def sign(last_hash: str, key: str) -> str:
    return hmac.new(key.encode("utf-8"), last_hash.encode("ascii"), hashlib.sha256).hexdigest()


class Store:
    def __init__(self, path: str, receipt_key: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.key = receipt_key
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None, timeout=10)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
                task_id TEXT NOT NULL REFERENCES tasks(id), id INTEGER NOT NULL,
                body TEXT NOT NULL, PRIMARY KEY(task_id, id)
            );
        """)

    def close(self):
        self.db.close()

    def healthy(self) -> bool:
        try:
            with self.lock:
                return self.db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        except sqlite3.Error:
            return False

    def create(self, task: dict):
        with self.lock:
            self.db.execute("INSERT INTO tasks VALUES (?, ?)", (task["task_id"], canonical_json(task)))
        def action(current, append):
            append("task_created", {"task_id": task["task_id"], "draft_contract": task["draft_contract"]})
            append("status", {"from": None, "to": current["status"]})
        self.mutate(task["task_id"], action)

    def get(self, task_id: str, *, events: bool = True) -> dict:
        with self.lock:
            row = self.db.execute("SELECT body FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise KeyError(task_id)
            task = json.loads(row[0])
            if events:
                task["events"] = [json.loads(row[0]) for row in self.db.execute(
                    "SELECT body FROM events WHERE task_id=? ORDER BY id", (task_id,)
                )]
            return task

    def mutate(self, task_id: str, action: Callable):
        """Serialize state changes and audit appends in one SQLite transaction."""
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                task = self.get(task_id, events=False)
                last = self.db.execute(
                    "SELECT body FROM events WHERE task_id=? ORDER BY id DESC LIMIT 1", (task_id,)
                ).fetchone()
                previous = json.loads(last[0]) if last else None

                def append(kind: str, payload: dict):
                    nonlocal previous
                    event = {
                        "id": previous["id"] + 1 if previous else 1,
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "type": kind, "payload": payload,
                        "prev_hash": previous["hash"] if previous else "0" * 64,
                    }
                    event["hash"] = event_hash(event)
                    self.db.execute("INSERT INTO events VALUES (?, ?, ?)", (task_id, event["id"], canonical_json(event)))
                    previous = event

                result = action(task, append)
                task["signature"] = sign(previous["hash"], self.key) if self.key and previous else None
                self.db.execute("UPDATE tasks SET body=? WHERE id=?", (canonical_json(task), task_id))
                self.db.execute("COMMIT")
                return result
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def audit(self, task_id: str, kind: str, payload: dict):
        self.mutate(task_id, lambda task, append: append(kind, payload))

    @staticmethod
    def move(task: dict, append: Callable, target: str) -> bool:
        origin = task["status"]
        if target not in TRANSITIONS.get(origin, set()):
            append("transition_rejected", {"from": origin, "to": target})
            return False
        task["status"] = target
        append("status", {"from": origin, "to": target})
        return True

    def transition(self, task_id: str, target: str) -> bool:
        return self.mutate(task_id, lambda task, append: self.move(task, append, target))

    def receipt(self, task_id: str) -> dict:
        task = self.get(task_id)
        return {
            "task_id": task_id, "contract": task["contract"] or task["draft_contract"],
            "events": task["events"], "final": task["final"] or {}, "signature": task["signature"],
        }


def verify_receipt(receipt: dict, key: str) -> dict:
    """Verify chain, signature, and the receipt envelope's signed contents."""
    previous = "0" * 64
    contract = None
    final = {}
    try:
        events = receipt["events"]
        if set(receipt) != {"task_id", "contract", "events", "final", "signature"}:
            return {"valid": False, "broken_at": "structure"}
        if not events or not key:
            return {"valid": False, "broken_at": "signature"}
        for index, event in enumerate(events, 1):
            if (set(event) != {"id", "ts", "type", "payload", "prev_hash", "hash"}
                    or event["id"] != index or event["prev_hash"] != previous
                    or not hmac.compare_digest(event["hash"], event_hash(event))):
                return {"valid": False, "broken_at": index}
            previous = event["hash"]
            if index == 1:
                if event["type"] != "task_created" or event["payload"]["task_id"] != receipt["task_id"]:
                    return {"valid": False, "broken_at": "task_id"}
                contract = event["payload"]["draft_contract"]
            if event["type"] == "answers_recorded":
                mapping = {"yes": True, "no": False, "don't care": None}
                contract = json.loads(canonical_json(contract))
                contract["requirements"].update({name: mapping[value] for name, value in event["payload"]["answers"].items()})
            if event["type"] == "contract_confirmed":
                contract = event["payload"]["contract"]
            if event["type"] == "order_committed":
                final = event["payload"]["final"]
        if not hmac.compare_digest(receipt["signature"], sign(previous, key)):
            return {"valid": False, "broken_at": "signature"}
        if canonical_json(receipt["contract"]) != canonical_json(contract):
            return {"valid": False, "broken_at": "contract"}
        if canonical_json(receipt["final"]) != canonical_json(final):
            return {"valid": False, "broken_at": "final"}
        return {"valid": True, "broken_at": None}
    except (KeyError, TypeError, ValueError):
        return {"valid": False, "broken_at": "structure"}
