"""Tests for the async event bus."""

from __future__ import annotations

import asyncio

import pytest

from watchflow.core.event_bus import EventBus
from watchflow.core.events import FileSystemEvent, FSEventType


def make_fs_event(path: str = "test.py") -> FileSystemEvent:
    return FileSystemEvent(path=path, event_type=FSEventType.MODIFIED)


@pytest.mark.asyncio
async def test_publish_delivers_to_subscriber(event_bus: EventBus) -> None:
    q = event_bus.subscribe()
    ev = make_fs_event()
    event_bus.publish(ev)
    received = await asyncio.wait_for(q.get(), timeout=1.0)
    assert received is ev


@pytest.mark.asyncio
async def test_multiple_subscribers_all_receive(event_bus: EventBus) -> None:
    queues = [event_bus.subscribe() for _ in range(3)]
    ev = make_fs_event("multi.py")
    event_bus.publish(ev)
    for q in queues:
        received = await asyncio.wait_for(q.get(), timeout=1.0)
        assert received is ev


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery(event_bus: EventBus) -> None:
    q = event_bus.subscribe()
    event_bus.unsubscribe(q)
    event_bus.publish(make_fs_event())
    assert q.empty()


@pytest.mark.asyncio
async def test_full_queue_drops_event(event_bus: EventBus) -> None:
    q = event_bus.subscribe()
    # Fill the queue to capacity
    for i in range(1000):
        try:
            q.put_nowait(make_fs_event(f"file{i}.py"))
        except asyncio.QueueFull:
            break

    # Publishing to a full queue should not raise
    event_bus.publish(make_fs_event("overflow.py"))


def test_subscriber_count(event_bus: EventBus) -> None:
    assert event_bus.subscriber_count == 0
    q1 = event_bus.subscribe()
    event_bus.subscribe()
    assert event_bus.subscriber_count == 2
    event_bus.unsubscribe(q1)
    assert event_bus.subscriber_count == 1
