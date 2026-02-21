"""Rule-based intent detection with confidence scoring."""

from __future__ import annotations

import fnmatch
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from watchflow.core.events import FileSystemEvent

if TYPE_CHECKING:
    from watchflow.config.schema import IntentRuleConfig

log: structlog.BoundLogger = structlog.get_logger(__name__)


@dataclass
class RuleMatch:
    rule_name: str
    pipeline_name: str
    confidence: float
    matched_patterns: list[str]
    total_events: int
    matched_events: int


@dataclass
class IntentResult:
    intent_name: str
    pipeline_name: str
    confidence: float
    rule_matches: list[RuleMatch] = field(default_factory=list)


@dataclass
class _Rule:
    name: str
    patterns: list[str]
    pipeline: str
    confidence_threshold: float = 0.6


# 5 built-in intent rules
_BUILTIN_RULES: list[_Rule] = [
    _Rule(
        name="run_tests",
        patterns=["test_*.py", "*_test.py", "*.py", "conftest.py", "pytest.ini", "setup.cfg"],
        pipeline="run_tests",
        confidence_threshold=0.6,
    ),
    _Rule(
        name="install_deps",
        patterns=[
            "requirements*.txt",
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "Pipfile",
            "poetry.lock",
            "package.json",
            "yarn.lock",
            "package-lock.json",
        ],
        pipeline="install_deps",
        confidence_threshold=0.7,
    ),
    _Rule(
        name="regenerate_schema",
        patterns=["*.proto", "*.graphql", "*.gql", "openapi.yaml", "openapi.yml", "schema.py"],
        pipeline="regenerate_schema",
        confidence_threshold=0.75,
    ),
    _Rule(
        name="format_python",
        patterns=["*.py"],
        pipeline="format_python",
        confidence_threshold=0.5,
    ),
    _Rule(
        name="docker_build",
        patterns=["Dockerfile", "Dockerfile.*", "docker-compose.yml", "docker-compose.yaml", ".dockerignore"],
        pipeline="docker_build",
        confidence_threshold=0.8,
    ),
]


def _compute_confidence(matched: int, total: int) -> float:
    """Confidence = event_weight × (0.6 + 0.4 × pattern_match_ratio).

    event_weight rises with the number of matched events so that a single
    well-matched event already clears moderate thresholds.
    """
    if total == 0:
        return 0.0
    ratio = matched / total
    # event_weight: 0 matches → 0.5, 1 match → 0.8, 2+ → 1.0
    event_weight = min(1.0, 0.5 + matched * 0.3)
    return min(1.0, event_weight * (0.6 + 0.4 * ratio))


class IntentDetector:
    """Detect developer intent from a batch of filesystem events.

    Built-in rules are loaded first; user-configured rules are appended
    and can override built-ins by matching the same ``name``.
    """

    def __init__(
        self, 
        user_rules: list[IntentRuleConfig] | None = None,
        allowed_pipelines: set[str] | None = None,
    ) -> None:
        self._rules: list[_Rule] = list(_BUILTIN_RULES)
        self._cache: dict[str, IntentResult | None] = {}

        if user_rules:
            user_rule_names = {r.name for r in user_rules}
            # Remove overridden built-ins
            self._rules = [r for r in self._rules if r.name not in user_rule_names]
            for ur in user_rules:
                self._rules.append(
                    _Rule(
                        name=ur.name,
                        patterns=ur.patterns,
                        pipeline=ur.pipeline,
                        confidence_threshold=ur.confidence_threshold,
                    )
                )

        if allowed_pipelines is not None:
            self._rules = [r for r in self._rules if r.pipeline in allowed_pipelines]

    def _hash_events(self, events: list[FileSystemEvent]) -> str:
        h = hashlib.sha256()
        for e in sorted(events, key=lambda x: (x.path, x.event_type.name)):
            h.update(f"{e.path}:{e.event_type.name}".encode())
        return h.hexdigest()

    def detect(self, events: list[FileSystemEvent]) -> IntentResult | None:
        """Return the best-matching intent, or ``None`` if below threshold."""
        if not events:
            return None

        evt_hash = self._hash_events(events)
        if evt_hash in self._cache:
            log.debug("intent.cache_hit", hash=evt_hash[:8])
            return self._cache[evt_hash]

        matches: list[RuleMatch] = []
        for rule in self._rules:
            matched = self._count_matches(events, rule.patterns)
            confidence = _compute_confidence(matched, len(events))
            if confidence >= rule.confidence_threshold:
                matches.append(
                    RuleMatch(
                        rule_name=rule.name,
                        pipeline_name=rule.pipeline,
                        confidence=confidence,
                        matched_patterns=rule.patterns,
                        total_events=len(events),
                        matched_events=matched,
                    )
                )

        if not matches:
            if len(self._cache) > 1000:
                self._cache.clear()
            self._cache[evt_hash] = None
            return None

        best = max(matches, key=lambda m: m.confidence)
        result = IntentResult(
            intent_name=best.rule_name,
            pipeline_name=best.pipeline_name,
            confidence=best.confidence,
            rule_matches=matches,
        )
        
        if len(self._cache) > 1000:
            self._cache.clear()
        self._cache[evt_hash] = result
        return result

    def explain(self, events: list[FileSystemEvent]) -> dict[str, Any]:
        """Return full reasoning tree for all rules (used by ``watchflow explain``)."""
        explanations: list[dict[str, Any]] = []
        for rule in self._rules:
            matched = self._count_matches(events, rule.patterns)
            confidence = _compute_confidence(matched, len(events))
            explanations.append(
                {
                    "rule": rule.name,
                    "pipeline": rule.pipeline,
                    "patterns": rule.patterns,
                    "threshold": rule.confidence_threshold,
                    "matched_events": matched,
                    "total_events": len(events),
                    "confidence": round(confidence, 4),
                    "above_threshold": confidence >= rule.confidence_threshold,
                }
            )
        explanations.sort(key=lambda x: x["confidence"], reverse=True)
        best = explanations[0] if explanations else None
        return {
            "input_events": [
                {"path": e.path, "type": str(e.event_type)} for e in events
            ],
            "rules_evaluated": len(explanations),
            "top_intent": best["rule"] if best and best["above_threshold"] else None,
            "reasoning": explanations,
        }

    def speculate(self, events: list[FileSystemEvent]) -> IntentResult | None:
        """Return a speculative match if confidence is between 0.4 and threshold."""
        if not events:
            return None
            
        speculative_matches: list[RuleMatch] = []
        for rule in self._rules:
            matched = self._count_matches(events, rule.patterns)
            confidence = _compute_confidence(matched, len(events))
            if 0.4 <= confidence < rule.confidence_threshold:
                speculative_matches.append(
                    RuleMatch(
                        rule_name=rule.name,
                        pipeline_name=rule.pipeline,
                        confidence=confidence,
                        matched_patterns=rule.patterns,
                        total_events=len(events),
                        matched_events=matched,
                    )
                )

        if not speculative_matches:
            return None

        best = max(speculative_matches, key=lambda m: m.confidence)
        log.debug("intent.speculated", intent=best.rule_name, confidence=round(best.confidence, 3))
        return IntentResult(
            intent_name=best.rule_name,
            pipeline_name=best.pipeline_name,
            confidence=best.confidence,
            rule_matches=speculative_matches,
        )

    @staticmethod
    def _count_matches(events: list[FileSystemEvent], patterns: list[str]) -> int:
        count = 0
        for ev in events:
            name = Path(ev.path).name
            if any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(ev.path, p) for p in patterns):
                count += 1
        return count
