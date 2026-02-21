"""7-state reactive state machine with asyncio.Lock-protected transitions."""

from __future__ import annotations

import asyncio
from enum import StrEnum
from typing import TYPE_CHECKING

import structlog

from watchflow import InvalidTransitionError
from watchflow.core.events import StateEvent

if TYPE_CHECKING:
    from watchflow.core.event_bus import EventBus

log: structlog.BoundLogger = structlog.get_logger(__name__)


class State(StrEnum):
    IDLE = "idle"
    WATCHING = "watching"
    DETECTING = "detecting"
    PLANNING = "planning"
    EXECUTING = "executing"
    RECOVERING = "recovering"
    SHUTTING_DOWN = "shutting_down"


# Valid transitions: state -> set of states reachable from it
_TRANSITIONS: dict[State, frozenset[State]] = {
    State.IDLE: frozenset({State.WATCHING, State.SHUTTING_DOWN}),
    State.WATCHING: frozenset({State.DETECTING, State.SHUTTING_DOWN}),
    State.DETECTING: frozenset({State.PLANNING, State.WATCHING, State.SHUTTING_DOWN}),
    State.PLANNING: frozenset({State.EXECUTING, State.WATCHING, State.SHUTTING_DOWN}),
    State.EXECUTING: frozenset({State.WATCHING, State.RECOVERING, State.SHUTTING_DOWN}),
    State.RECOVERING: frozenset({State.WATCHING, State.SHUTTING_DOWN}),
    State.SHUTTING_DOWN: frozenset(),
}


class ReactiveStateMachine:
    """Thread-safe state machine for the WatchFlow execution lifecycle."""

    def __init__(self, bus: EventBus | None = None) -> None:
        self._state = State.IDLE
        self._lock = asyncio.Lock()
        self._bus = bus

    @property
    def state(self) -> State:
        return self._state

    async def transition(self, new_state: State) -> None:
        """Atomically transition to *new_state*.

        Raises :exc:`InvalidTransitionError` if the transition is not in the
        allowed table.  Publishes a :class:`StateEvent` on success.
        """
        async with self._lock:
            allowed = _TRANSITIONS.get(self._state, frozenset())
            if new_state not in allowed:
                raise InvalidTransitionError(
                    f"Cannot transition from {self._state!r} to {new_state!r}. "
                    f"Allowed: {sorted(allowed)}"
                )
            previous = self._state
            self._state = new_state
            log.debug("state_machine.transition", previous=previous, current=new_state)

        if self._bus is not None:
            self._bus.publish(StateEvent(previous=str(previous), current=str(new_state)))

    def is_terminal(self) -> bool:
        return self._state == State.SHUTTING_DOWN

    def can_transition(self, target: State) -> bool:
        return target in _TRANSITIONS.get(self._state, frozenset())
