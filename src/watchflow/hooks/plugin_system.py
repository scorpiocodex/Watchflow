"""Hook registry for lifecycle events, supporting sync and async callbacks."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import structlog

log: structlog.BoundLogger = structlog.get_logger(__name__)


class HookPoint(StrEnum):
    ON_STARTUP = "on_startup"
    ON_SHUTDOWN = "on_shutdown"
    ON_INTENT_DETECTED = "on_intent_detected"
    BEFORE_PIPELINE = "before_pipeline"
    AFTER_PIPELINE = "after_pipeline"
    ON_FAILURE = "on_failure"
    ON_REPEAT_FAILURE = "on_repeat_failure"
    ON_IDLE = "on_idle"


AnyCallback = Callable[..., Any]


@dataclass
class Registration:
    hook: HookPoint
    callback: AnyCallback
    priority: int = 100
    plugin_name: str = "anonymous"


class HookRegistry:
    """Manages plugin hook registrations and fires them in priority order."""

    def __init__(self) -> None:
        self._registrations: list[Registration] = []

    def register(
        self,
        hook: HookPoint,
        callback: AnyCallback,
        *,
        priority: int = 100,
        plugin_name: str = "anonymous",
    ) -> None:
        self._registrations.append(
            Registration(hook=hook, callback=callback, priority=priority, plugin_name=plugin_name)
        )
        log.debug("hook.registered", hook=hook, plugin=plugin_name, priority=priority)

    async def fire(self, hook: HookPoint, **kwargs: Any) -> None:
        """Fire all callbacks registered for *hook* in priority order.

        Failures are caught and logged; they never propagate.
        """
        relevant = sorted(
            (r for r in self._registrations if r.hook == hook),
            key=lambda r: r.priority,
        )
        for reg in relevant:
            try:
                if inspect.iscoroutinefunction(reg.callback):
                    await reg.callback(**kwargs)
                else:
                    reg.callback(**kwargs)
            except Exception as exc:
                log.error(
                    "hook.callback_failed",
                    hook=hook,
                    plugin=reg.plugin_name,
                    error=str(exc),
                )

    def list_registrations(self) -> list[dict[str, Any]]:
        return [
            {
                "hook": str(r.hook),
                "plugin": r.plugin_name,
                "priority": r.priority,
                "callback": getattr(r.callback, "__name__", repr(r.callback)),
            }
            for r in sorted(self._registrations, key=lambda r: (r.hook, r.priority))
        ]
