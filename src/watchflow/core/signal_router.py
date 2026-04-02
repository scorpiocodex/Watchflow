"""Routes filesystem event batches to pipeline routing decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from watchflow.core.events import FileSystemEvent

if TYPE_CHECKING:
    from typing import Any

    from watchflow.config.schema import GlobalConfig
    from watchflow.intelligence.intent_detector import IntentDetector, IntentResult

log: structlog.BoundLogger = structlog.get_logger(__name__)


@dataclass
class RoutingDecision:
    """Result of routing a batch of filesystem events."""

    pipeline_name: str
    intent_name: str
    confidence: float
    context: dict[str, str]
    source_events: list[FileSystemEvent]


class SignalRouter:
    """Route filesystem event batches through the intent detector to pipeline decisions."""

    def __init__(self, config: GlobalConfig, detector: IntentDetector) -> None:
        self._config = config
        self._detector = detector

    def route(self, events: list[FileSystemEvent]) -> RoutingDecision | None:
        """Detect intent from *events* and return a routing decision, or ``None``."""
        if not events:
            return None

        result: IntentResult | None = self._detector.detect(events)
        if result is None:
            log.debug("signal_router.no_intent", event_count=len(events))
            return None

        # Build template context from the first event
        primary = events[0]
        context: dict[str, str] = {
            "changed_file": primary.path,
            "watcher": primary.watcher_name,
            "event_type": str(primary.event_type),
            "intent": result.intent_name,
            "pipeline": result.pipeline_name,
        }

        log.info(
            "signal_router.routed",
            intent=result.intent_name,
            pipeline=result.pipeline_name,
            confidence=round(result.confidence, 3),
            events=len(events),
        )
        return RoutingDecision(
            pipeline_name=result.pipeline_name,
            intent_name=result.intent_name,
            confidence=result.confidence,
            context=context,
            source_events=events,
        )

    def speculate(self, events: list[FileSystemEvent]) -> RoutingDecision | None:
        """Attempt to find a speculative routing decision below the full confidence threshold."""
        if not events:
            return None

        # Check IntentDetector for a speculate() method
        if not hasattr(self._detector, "speculate"):
            return None

        result: "IntentResult | None" = self._detector.speculate(events)
        if result is None:
            return None

        primary = events[0]
        context: dict[str, str] = {
            "changed_file": primary.path,
            "watcher": primary.watcher_name,
            "event_type": str(primary.event_type),
            "intent": result.intent_name,
            "pipeline": result.pipeline_name,
        }

        return RoutingDecision(
            pipeline_name=result.pipeline_name,
            intent_name=result.intent_name,
            confidence=result.confidence,
            context=context,
            source_events=events,
        )
