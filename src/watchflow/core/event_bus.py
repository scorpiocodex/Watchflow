"""Async event bus with per-subscriber Queue-based pub/sub."""

from __future__ import annotations

import asyncio
import contextlib

import structlog

from watchflow.core.events import AnyEvent

log: structlog.BoundLogger = structlog.get_logger(__name__)


class EventBus:
    """Non-blocking publish/subscribe message bus.

    Each call to :meth:`subscribe` returns a dedicated :class:`asyncio.Queue`.
    :meth:`publish` uses ``put_nowait``; if a subscriber's queue is full, the
    event is dropped and a warning is logged.
    """

    _MAX_QUEUE_SIZE = 1000

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[AnyEvent]] = []

    def subscribe(self) -> asyncio.Queue[AnyEvent]:
        """Register a new subscriber; return its dedicated queue."""
        q: asyncio.Queue[AnyEvent] = asyncio.Queue(maxsize=self._MAX_QUEUE_SIZE)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, queue: asyncio.Queue[AnyEvent]) -> None:
        """Remove a subscriber queue."""
        with contextlib.suppress(ValueError):
            self._subscribers.remove(queue)

    def publish(self, event: AnyEvent) -> None:
        """Publish *event* to all subscribers (non-blocking).

        Drops events on full queues rather than blocking.
        """
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                log.warning(
                    "event_bus.dropped",
                    event_kind=getattr(event, "kind", "unknown"),
                    queue_size=q.qsize(),
                )

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
