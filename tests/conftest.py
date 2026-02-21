"""Shared pytest fixtures for WatchFlow tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from watchflow.config.schema import (
    CommandConfig,
    GlobalConfig,
    IntentRuleConfig,
    PipelineConfig,
    WatcherConfig,
)
from watchflow.core.event_bus import EventBus
from watchflow.core.events import FileSystemEvent, FSEventType
from watchflow.core.state_machine import ReactiveStateMachine


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def state_machine(event_bus: EventBus) -> ReactiveStateMachine:
    return ReactiveStateMachine(bus=event_bus)


@pytest.fixture
def simple_command() -> CommandConfig:
    return CommandConfig(name="echo", cmd="echo hello", timeout=5.0)


@pytest.fixture
def simple_pipeline(simple_command: CommandConfig) -> PipelineConfig:
    return PipelineConfig(name="test_pipeline", commands=[simple_command])


@pytest.fixture
def sample_fs_event() -> FileSystemEvent:
    return FileSystemEvent(path="src/test_api.py", event_type=FSEventType.MODIFIED)


@pytest.fixture
def sample_config(tmp_path: Path) -> GlobalConfig:
    return GlobalConfig(
        watchers=[
            WatcherConfig(name="w1", paths=[str(tmp_path)], patterns=["*.py"])
        ],
        pipelines=[
            PipelineConfig(
                name="run_tests",
                commands=[CommandConfig(name="test", cmd="echo test", timeout=5.0)],
            )
        ],
        intent_rules=[
            IntentRuleConfig(name="run_tests", patterns=["*.py"], pipeline="run_tests")
        ],
    )
