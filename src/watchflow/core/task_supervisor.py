"""Supervised async task lifecycle management."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

import structlog

log: structlog.BoundLogger = structlog.get_logger(__name__)

# A coroutine factory: a zero-argument callable that returns a fresh coroutine.
CoroFactory = Callable[[], Coroutine[Any, Any, Any]]


class TaskSupervisor:
    """Manage a group of long-running asyncio tasks with clean cancellation."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    def spawn(
        self,
        name: str,
        coro: Coroutine[Any, Any, Any],
        *,
        restart_on_failure: bool = False,
        factory: CoroFactory | None = None,
    ) -> asyncio.Task[Any]:
        """Create and register a supervised task.

        Parameters
        ----------
        name:
            Unique task identifier.
        coro:
            The coroutine to run.  Ignored when *factory* is supplied.
        restart_on_failure:
            If True, the task is automatically restarted (up to 3 times) when
            it raises an unexpected exception.  **Requires** *factory* to be
            provided so that a fresh coroutine can be created on each restart.
        factory:
            Zero-argument callable that creates a new coroutine on each call.
            Required when *restart_on_failure* is True.  When supplied it takes
            precedence over *coro*.
        """
        if restart_on_failure:
            if factory is None:
                # Coroutine objects can only be awaited once, so we cannot
                # restart from one.  Raise early to prevent silent breakage.
                raise TypeError(
                    f"spawn('{name}', restart_on_failure=True) requires a "
                    "coroutine factory — pass factory=<callable> instead of "
                    "a plain coroutine."
                )
            # Close the placeholder coro so it doesn't emit "was never awaited".
            coro.close()
            effective_coro: Coroutine[Any, Any, Any] = self._supervised(name, factory)
        elif factory is not None:
            # factory= without restart: close placeholder and use factory once.
            coro.close()
            effective_coro = factory()
        else:
            effective_coro = coro

        task = asyncio.create_task(effective_coro, name=name)
        task.add_done_callback(lambda t: self._on_done(name, t))
        self._tasks[name] = task
        log.debug("supervisor.spawned", task=name, restart=restart_on_failure)
        return task

    async def _supervised(
        self,
        name: str,
        factory: CoroFactory,
        max_restarts: int = 3,
    ) -> None:
        """Run *factory()* and restart on failure up to *max_restarts* times."""
        for attempt in range(max_restarts + 1):
            try:
                await factory()
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                if attempt >= max_restarts:
                    log.error("supervisor.task_exhausted", task=name, attempts=attempt + 1)
                    raise
                wait = 2**attempt
                log.warning(
                    "supervisor.restarting",
                    task=name,
                    attempt=attempt + 1,
                    wait_s=wait,
                )
                await asyncio.sleep(wait)

    def _on_done(self, name: str, task: asyncio.Task[Any]) -> None:
        self._tasks.pop(name, None)
        if task.cancelled():
            log.debug("supervisor.cancelled", task=name)
        elif task.exception():
            log.error("supervisor.failed", task=name, exc=task.exception())
        else:
            log.debug("supervisor.completed", task=name)

    async def cancel_all(self, timeout: float = 5.0) -> None:
        """Cancel all supervised tasks and wait for them to finish."""
        tasks = list(self._tasks.values())
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=timeout)
        self._tasks.clear()
        log.debug("supervisor.all_cancelled", count=len(tasks))

    @property
    def active_names(self) -> list[str]:
        return list(self._tasks.keys())
