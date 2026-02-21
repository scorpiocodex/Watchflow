"""Tests for the hook registry and plugin system."""

from __future__ import annotations

import pytest

from watchflow.hooks.plugin_system import HookPoint, HookRegistry


@pytest.mark.asyncio
async def test_sync_callback_fired() -> None:
    registry = HookRegistry()
    called_with: list = []

    def cb(**kwargs):
        called_with.append(kwargs)

    registry.register(HookPoint.ON_STARTUP, cb)
    await registry.fire(HookPoint.ON_STARTUP, key="value")
    assert called_with == [{"key": "value"}]


@pytest.mark.asyncio
async def test_async_callback_fired() -> None:
    registry = HookRegistry()
    called: list = []

    async def acb(**kwargs):
        called.append(True)

    registry.register(HookPoint.AFTER_PIPELINE, acb)
    await registry.fire(HookPoint.AFTER_PIPELINE)
    assert called == [True]


@pytest.mark.asyncio
async def test_failing_callback_does_not_propagate() -> None:
    registry = HookRegistry()

    def bad_cb(**kwargs):
        raise RuntimeError("intentional failure")

    registry.register(HookPoint.ON_FAILURE, bad_cb)
    # Should not raise
    await registry.fire(HookPoint.ON_FAILURE)


@pytest.mark.asyncio
async def test_priority_ordering() -> None:
    registry = HookRegistry()
    order: list[int] = []

    registry.register(HookPoint.BEFORE_PIPELINE, lambda **kw: order.append(3), priority=300)
    registry.register(HookPoint.BEFORE_PIPELINE, lambda **kw: order.append(1), priority=100)
    registry.register(HookPoint.BEFORE_PIPELINE, lambda **kw: order.append(2), priority=200)

    await registry.fire(HookPoint.BEFORE_PIPELINE)
    assert order == [1, 2, 3]


def test_list_registrations() -> None:
    registry = HookRegistry()
    registry.register(HookPoint.ON_STARTUP, lambda: None, plugin_name="myplugin", priority=50)
    regs = registry.list_registrations()
    assert len(regs) == 1
    assert regs[0]["plugin"] == "myplugin"
    assert regs[0]["priority"] == 50


@pytest.mark.asyncio
async def test_no_registrations_fires_cleanly() -> None:
    registry = HookRegistry()
    await registry.fire(HookPoint.ON_IDLE)  # no registrations — should not fail
