"""Small SQLite event log for backend steps."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


_DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "events.db"


def log_event(task_id: str, kind: str, payload: Any) -> None:
    """Append one JSON payload event, creating the database schema when needed."""

    _DATABASE_PATH.parent.mkdir(exist_ok=True)
    with sqlite3.connect(_DATABASE_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                ts TEXT NOT NULL,
                kind TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO events (id, task_id, ts, kind, payload_json) VALUES (?, ?, ?, ?, ?)",
            (str(uuid4()), task_id, datetime.now(UTC).isoformat(), kind, json.dumps(payload, default=str)),
        )
