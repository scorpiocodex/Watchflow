"""Telemetry storage and resource monitoring."""

from __future__ import annotations

import asyncio
import sqlite3
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psutil
import structlog

log: structlog.BoundLogger = structlog.get_logger(__name__)


@dataclass
class PipelineMetric:
    pipeline_name: str
    success: bool
    duration_ms: float
    timestamp: float = field(default_factory=time.monotonic)


@dataclass
class ResourceSnapshot:
    cpu_percent: float
    memory_mb: float
    timestamp: float = field(default_factory=time.monotonic)


class TelemetryStore:
    """In-memory telemetry store for pipeline metrics and resource snapshots."""

    _MAX_HISTORY = 500

    def __init__(self, db_path: Path | None = None) -> None:
        self._pipeline_metrics: list[PipelineMetric] = []
        self._resource_snapshots: deque[ResourceSnapshot] = deque(maxlen=200)
        self._event_count = 0
        self._pipeline_count = 0
        self._failure_count = 0
        self._started_at = time.monotonic()

        if db_path is None:
            db_dir = Path.home() / ".watchflow"
            db_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = db_dir / "metrics.db"
        else:
            self.db_path = db_path
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._init_db()

    def _init_db(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pipeline_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    pipeline_name TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    duration_ms REAL NOT NULL
                )
            """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS resource_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    cpu_percent REAL NOT NULL,
                    memory_mb REAL NOT NULL
                )
            """
            )

    def record_pipeline(self, name: str, success: bool, duration_ms: float) -> None:
        """Record a pipeline execution."""
        metric = PipelineMetric(name, success, duration_ms)
        self._pipeline_metrics.append(metric)
        if len(self._pipeline_metrics) > self._MAX_HISTORY:
            self._pipeline_metrics.pop(0)
        self._pipeline_count += 1
        if not success:
            self._failure_count += 1

        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO pipeline_metrics (timestamp, pipeline_name, success, duration_ms) VALUES (?, ?, ?, ?)",
                    (time.time(), name, 1 if success else 0, duration_ms),
                )
        except Exception as e:
            log.error("metrics.record_pipeline_error", exc=str(e))

    def record_event(self) -> None:
        """Record a filesystem event (non-blocking, in-memory only)."""
        self._event_count += 1

    def record_resource(self, cpu: float, mem_mb: float) -> None:
        """Record resource usage."""
        self._resource_snapshots.append(ResourceSnapshot(cpu, mem_mb))
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO resource_metrics (timestamp, cpu_percent, memory_mb) VALUES (?, ?, ?)",
                    (time.time(), cpu, mem_mb),
                )
        except Exception as e:
            log.error("metrics.record_resource_error", exc=str(e))

    @property
    def uptime_s(self) -> float:
        return time.monotonic() - self._started_at

    @property
    def event_count(self) -> int:
        return self._event_count

    @property
    def pipeline_count(self) -> int:
        return self._pipeline_count

    @property
    def failure_count(self) -> int:
        return self._failure_count

    @property
    def success_rate(self) -> float:
        if self._pipeline_count == 0:
            return 1.0
        return (self._pipeline_count - self._failure_count) / self._pipeline_count

    def latest_resource(self) -> ResourceSnapshot | None:
        if not self._resource_snapshots:
            return None
        return self._resource_snapshots[-1]

    def recent_pipelines(self, n: int = 10) -> list[PipelineMetric]:
        return self._pipeline_metrics[-n:]

    def summary(self) -> dict[str, Any]:
        latest = self.latest_resource()
        return {
            "uptime_s": round(self.uptime_s, 1),
            "events": self._event_count,
            "pipelines_run": self._pipeline_count,
            "failures": self._failure_count,
            "success_rate": round(self.success_rate, 3),
            "cpu_percent": latest.cpu_percent if latest else None,
            "memory_mb": round(latest.memory_mb, 1) if latest else None,
        }

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()


class ResourceMonitor:
    """Periodically sample CPU and memory usage and record to TelemetryStore."""

    def __init__(self, store: TelemetryStore, interval_s: float = 2.0) -> None:
        self._store = store
        self._interval = interval_s
        self._process = psutil.Process()

    async def run(self) -> None:
        """Run indefinitely, sampling resources every *interval_s* seconds."""
        while True:
            try:
                cpu = self._process.cpu_percent(interval=None)
                mem = self._process.memory_info().rss / (1024 * 1024)
                self._store.record_resource(cpu, mem)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                log.warning("resource_monitor.process_gone")
                break
            await asyncio.sleep(self._interval)
