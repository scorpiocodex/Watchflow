"""Typed event dataclasses for WatchFlow's async event bus."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EventKind(StrEnum):
    FILESYSTEM = "filesystem"
    INTENT = "intent"
    STATE = "state"
    PIPELINE = "pipeline"
    SYSTEM = "system"


class FSEventType(StrEnum):
    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"
    MOVED = "moved"


class PipelineEventType(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"


@dataclass(slots=True)
class FileSystemEvent:
    kind: EventKind = field(default=EventKind.FILESYSTEM, init=False)
    path: str
    event_type: FSEventType
    is_directory: bool = False
    watcher_name: str = ""
    timestamp: float = field(default_factory=time.monotonic)


@dataclass(slots=True)
class IntentEvent:
    kind: EventKind = field(default=EventKind.INTENT, init=False)
    intent_name: str
    pipeline_name: str
    confidence: float
    source_events: list[FileSystemEvent] = field(default_factory=list)
    reasoning: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.monotonic)


@dataclass(slots=True)
class StateEvent:
    kind: EventKind = field(default=EventKind.STATE, init=False)
    previous: str
    current: str
    timestamp: float = field(default_factory=time.monotonic)


@dataclass(slots=True)
class PipelineEvent:
    kind: EventKind = field(default=EventKind.PIPELINE, init=False)
    pipeline_name: str
    event_type: PipelineEventType
    step_name: str = ""
    duration_ms: float = 0.0
    error: str = ""
    timestamp: float = field(default_factory=time.monotonic)


@dataclass(slots=True)
class SystemEvent:
    kind: EventKind = field(default=EventKind.SYSTEM, init=False)
    message: str
    level: str = "info"
    timestamp: float = field(default_factory=time.monotonic)


# Union type for all event types
AnyEvent = FileSystemEvent | IntentEvent | StateEvent | PipelineEvent | SystemEvent
