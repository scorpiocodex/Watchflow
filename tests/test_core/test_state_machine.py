"""Tests for the reactive state machine."""

from __future__ import annotations

import asyncio

import pytest

from watchflow import InvalidTransitionError
from watchflow.core.state_machine import ReactiveStateMachine, State


@pytest.mark.asyncio
async def test_initial_state_is_idle(state_machine: ReactiveStateMachine) -> None:
    assert state_machine.state == State.IDLE


@pytest.mark.asyncio
async def test_valid_transition_idle_to_watching(state_machine: ReactiveStateMachine) -> None:
    await state_machine.transition(State.WATCHING)
    assert state_machine.state == State.WATCHING


@pytest.mark.asyncio
async def test_invalid_transition_raises(state_machine: ReactiveStateMachine) -> None:
    with pytest.raises(InvalidTransitionError):
        await state_machine.transition(State.EXECUTING)


@pytest.mark.asyncio
async def test_full_happy_path(state_machine: ReactiveStateMachine) -> None:
    await state_machine.transition(State.WATCHING)
    await state_machine.transition(State.DETECTING)
    await state_machine.transition(State.PLANNING)
    await state_machine.transition(State.EXECUTING)
    await state_machine.transition(State.WATCHING)
    assert state_machine.state == State.WATCHING


@pytest.mark.asyncio
async def test_recovering_path(state_machine: ReactiveStateMachine) -> None:
    await state_machine.transition(State.WATCHING)
    await state_machine.transition(State.DETECTING)
    await state_machine.transition(State.PLANNING)
    await state_machine.transition(State.EXECUTING)
    await state_machine.transition(State.RECOVERING)
    await state_machine.transition(State.WATCHING)
    assert state_machine.state == State.WATCHING


@pytest.mark.asyncio
async def test_shutting_down_is_terminal(state_machine: ReactiveStateMachine) -> None:
    await state_machine.transition(State.SHUTTING_DOWN)
    assert state_machine.is_terminal()
    with pytest.raises(InvalidTransitionError):
        await state_machine.transition(State.WATCHING)


@pytest.mark.asyncio
async def test_transition_publishes_state_event(event_bus) -> None:
    from watchflow.core.events import StateEvent

    sm = ReactiveStateMachine(bus=event_bus)
    q = event_bus.subscribe()
    await sm.transition(State.WATCHING)

    ev = await asyncio.wait_for(q.get(), timeout=1.0)
    assert isinstance(ev, StateEvent)
    assert ev.previous == "idle"
    assert ev.current == "watching"


@pytest.mark.asyncio
async def test_can_transition_check(state_machine: ReactiveStateMachine) -> None:
    assert state_machine.can_transition(State.WATCHING)
    assert not state_machine.can_transition(State.EXECUTING)
