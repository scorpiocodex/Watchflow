"""Write-Ahead Log (WAL) for time-travel event replay."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import structlog

from watchflow.core.events import AnyEvent, FileSystemEvent, IntentEvent, PipelineEvent, SystemEvent

log: structlog.BoundLogger = structlog.get_logger(__name__)


class WriteAheadLog:
    """Records system events to an SQLite database for time-travel replay."""

    def __init__(self, db_path: Path | None = None) -> None:
        if db_path is None:
            self.db_dir = Path.home() / ".watchflow"
            self.db_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = self.db_dir / "wal.db"
        else:
            self.db_path = db_path
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON events(timestamp)")

    def record(self, event: AnyEvent) -> None:
        """Record an event to the WAL."""
        try:
            payload: dict[str, Any] = {}
            event_type = "unknown"

            if isinstance(event, FileSystemEvent):
                event_type = "fs"
                payload = {
                    "path": event.path,
                    "event_type": event.event_type.name,
                    "is_directory": event.is_directory,
                }
            elif isinstance(event, IntentEvent):
                event_type = "intent"
                payload = {
                    "intent_name": event.intent_name,
                    "pipeline_name": event.pipeline_name,
                    "confidence": event.confidence,
                }
            elif isinstance(event, PipelineEvent):
                event_type = "pipeline"
                payload = {
                    "pipeline_name": event.pipeline_name,
                    "event_type": event.event_type.name,
                    "step_name": getattr(event, "step_name", None),
                    "duration_ms": getattr(event, "duration_ms", None),
                    "error": getattr(event, "error", None),
                }
            elif isinstance(event, SystemEvent):
                event_type = "system"
                payload = {
                    "message": event.message,
                    "level": event.level,
                }
            else:
                return

            with self._conn:
                self._conn.execute(
                    "INSERT INTO events (timestamp, event_type, payload) VALUES (?, ?, ?)",
                    (time.time(), event_type, json.dumps(payload)),
                )
        except Exception as e:
            log.error("wal.record_error", exc=str(e))

    def read_all(self) -> list[dict[str, Any]]:
        """Read all events ordered by time."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT timestamp, event_type, payload FROM events ORDER BY timestamp ASC")
        results = []
        for row in cursor:
            results.append(
                {
                    "timestamp": row["timestamp"],
                    "event_type": row["event_type"],
                    "payload": json.loads(row["payload"]),
                }
            )
        return results

    def clear(self) -> None:
        """Clear all events from the WAL."""
        with self._conn:
            self._conn.execute("DELETE FROM events")

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
