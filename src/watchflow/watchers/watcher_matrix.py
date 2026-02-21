"""Filesystem watcher with adaptive debouncing, bridging watchdog → asyncio."""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from watchflow.core.events import FileSystemEvent, FSEventType
from watchflow.utils.helpers import current_ms, hash_file, matches_ignore_pattern

if TYPE_CHECKING:
    from watchflow.config.schema import WatcherConfig
    from watchflow.core.event_bus import EventBus

log: structlog.BoundLogger = structlog.get_logger(__name__)

# Type alias for the batch callback
_BatchCallback = Callable[[list[FileSystemEvent]], Coroutine[Any, Any, None]]


class AdaptiveDebouncer:
    """Adjust debounce delay based on observed event frequency.

    Maintains a rolling window of the last 10 inter-event intervals and
    selects the debounce delay according to:

    - avg < 50 ms  → max_ms (burst → 2000 ms)
    - avg < 100 ms → 2 × base_ms
    - avg < 500 ms → base_ms
    - avg ≥ 500 ms → min_ms (idle → respond fast)
    """

    _WINDOW = 10

    def __init__(self, base_ms: int, min_ms: int = 50, max_ms: int = 2000) -> None:
        self.base_ms = base_ms
        self.min_ms = min_ms
        self.max_ms = max_ms
        self._intervals: deque[float] = deque(maxlen=self._WINDOW)
        self._last_event_ms: float | None = None

    def record_event(self) -> None:
        now = current_ms()
        if self._last_event_ms is not None:
            self._intervals.append(now - self._last_event_ms)
        self._last_event_ms = now

    def current_delay_ms(self) -> int:
        if not self._intervals:
            return self.base_ms
        avg = sum(self._intervals) / len(self._intervals)
        if avg < 50:
            return self.max_ms
        if avg < 100:
            return min(self.base_ms * 2, self.max_ms)
        if avg < 500:
            return self.base_ms
        return self.min_ms


@dataclass
class _PendingBatch:
    events: list[FileSystemEvent] = field(default_factory=list)
    deadline_ms: float = 0.0


class _WatchdogBridge(FileSystemEventHandler):
    """Receives watchdog events (OS thread) and forwards to the asyncio loop."""

    def __init__(
        self,
        watcher_name: str,
        config: WatcherConfig,
        loop: asyncio.AbstractEventLoop,
        callback: _BatchCallback,
        debouncer: AdaptiveDebouncer,
    ) -> None:
        super().__init__()
        self._name = watcher_name
        self._config = config
        self._loop = loop
        self._callback = callback
        self._debouncer = debouncer
        self._lock = threading.Lock()
        self._batch: _PendingBatch = _PendingBatch()
        self._timer: threading.Timer | None = None
        self._file_hashes: dict[str, str | None] = {}

    def _matches(self, path: str) -> bool:
        import fnmatch

        name = Path(path).name
        if matches_ignore_pattern(path, self._config.ignore):
            return False
        return any(
            fnmatch.fnmatch(name, p) or fnmatch.fnmatch(path, p)
            for p in self._config.patterns
        )

    def _hash_changed(self, path: str) -> bool:
        if not self._config.hash_check:
            return True
        new_hash = hash_file(Path(path))
        old_hash = self._file_hashes.get(path)
        self._file_hashes[path] = new_hash
        return new_hash != old_hash

    def _map_event_type(self, event_type: str) -> FSEventType:
        return {
            "created": FSEventType.CREATED,
            "modified": FSEventType.MODIFIED,
            "deleted": FSEventType.DELETED,
            "moved": FSEventType.MOVED,
        }.get(event_type, FSEventType.MODIFIED)

    def dispatch(self, event: object) -> None:  # type: ignore[override]
        from watchdog.events import FileSystemEvent as WDEvent

        ev: WDEvent = event  # type: ignore[assignment]
        src_path: str = getattr(ev, "src_path", "")
        is_dir: bool = getattr(ev, "is_directory", False)

        if not self._matches(src_path):
            return
        if not self._hash_changed(src_path):
            return

        self._debouncer.record_event()
        delay_s = self._debouncer.current_delay_ms() / 1000.0

        fs_event = FileSystemEvent(
            path=src_path,
            event_type=self._map_event_type(ev.event_type),
            is_directory=is_dir,
            watcher_name=self._name,
        )

        with self._lock:
            self._batch.events.append(fs_event)
            self._batch.deadline_ms = current_ms() + self._debouncer.current_delay_ms()
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(delay_s, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            events = self._batch.events[:]
            self._batch = _PendingBatch()
            self._timer = None
        if events:
            asyncio.run_coroutine_threadsafe(self._callback(events), self._loop)


class WatcherMatrix:
    """Manages multiple watchdog Observer instances for all configured watchers."""

    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus
        self._observer: Observer | None = None  # type: ignore[valid-type]
        self._bridges: list[_WatchdogBridge] = []

    def setup(self, configs: list[WatcherConfig]) -> None:
        """Configure watchers from the list of :class:`WatcherConfig`.

        Must be called from within a running asyncio event loop.
        """
        loop = asyncio.get_running_loop()
        self._observer = Observer()
        for cfg in configs:
            debouncer = AdaptiveDebouncer(base_ms=cfg.debounce_ms)
            bridge = _WatchdogBridge(
                watcher_name=cfg.name,
                config=cfg,
                loop=loop,
                callback=self._on_batch,
                debouncer=debouncer,
            )
            self._bridges.append(bridge)
            for path_str in cfg.paths:
                path = Path(path_str)
                if path.exists():
                    self._observer.schedule(bridge, str(path), recursive=cfg.recursive)
                    log.info("watcher.scheduled", name=cfg.name, path=str(path))
                else:
                    log.warning("watcher.path_missing", name=cfg.name, path=str(path))

    async def _on_batch(self, events: list[FileSystemEvent]) -> None:
        for ev in events:
            self._bus.publish(ev)
        log.debug("watcher.batch_published", count=len(events))

    def start(self) -> None:
        if self._observer is not None:
            self._observer.start()
            log.info("watcher_matrix.started")

    def stop(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5.0)
            log.info("watcher_matrix.stopped")
