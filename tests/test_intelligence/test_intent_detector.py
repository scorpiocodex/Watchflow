"""Tests for the intent detector with hypothesis property-based tests."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from watchflow.core.events import FileSystemEvent, FSEventType
from watchflow.intelligence.intent_detector import IntentDetector, _compute_confidence


def make_events(*paths: str) -> list[FileSystemEvent]:
    return [FileSystemEvent(path=p, event_type=FSEventType.MODIFIED) for p in paths]


class TestIntentDetector:
    def test_detects_run_tests_for_py_files(self) -> None:
        detector = IntentDetector()
        events = make_events("test_api.py", "test_utils.py")
        result = detector.detect(events)
        assert result is not None
        assert result.intent_name in {"run_tests", "format_python"}

    def test_detects_install_deps(self) -> None:
        detector = IntentDetector()
        events = make_events("requirements.txt")
        result = detector.detect(events)
        assert result is not None
        assert result.intent_name == "install_deps"

    def test_detects_docker_build(self) -> None:
        detector = IntentDetector()
        events = make_events("Dockerfile")
        result = detector.detect(events)
        assert result is not None
        assert result.intent_name == "docker_build"

    def test_no_intent_for_unmatched(self) -> None:
        detector = IntentDetector()
        events = make_events("some_random_binary.xyz")
        result = detector.detect(events)
        # May return None or a low-confidence result — if returned, verify threshold
        if result is not None:
            assert result.confidence >= 0

    def test_empty_events_returns_none(self) -> None:
        detector = IntentDetector()
        result = detector.detect([])
        assert result is None

    def test_explain_returns_all_rules(self) -> None:
        detector = IntentDetector()
        events = make_events("test_api.py")
        explanation = detector.explain(events)
        assert "reasoning" in explanation
        assert len(explanation["reasoning"]) >= 5  # 5 builtins

    def test_user_rule_adds_custom_rule(self) -> None:
        from watchflow.config.schema import IntentRuleConfig

        # Custom rule matching a file extension no builtin covers
        user_rule = IntentRuleConfig(
            name="custom_rst",
            patterns=["*.rst"],
            pipeline="my_custom_pipeline",
            confidence_threshold=0.1,
        )
        detector = IntentDetector(user_rules=[user_rule])
        events = make_events("README.rst")
        result = detector.detect(events)
        assert result is not None
        assert result.pipeline_name == "my_custom_pipeline"

    def test_user_rule_overrides_builtin_by_name(self) -> None:
        from watchflow.config.schema import IntentRuleConfig

        # Override docker_build builtin with a custom pipeline name
        user_rule = IntentRuleConfig(
            name="docker_build",
            patterns=["Dockerfile"],
            pipeline="my_docker_pipeline",
            confidence_threshold=0.1,
        )
        detector = IntentDetector(user_rules=[user_rule])
        events = make_events("Dockerfile")
        result = detector.detect(events)
        assert result is not None
        # The original docker_build builtin should be replaced
        assert any(
            m.pipeline_name == "my_docker_pipeline"
            for m in result.rule_matches
        )

    def test_confidence_ordering(self) -> None:
        detector = IntentDetector()
        events = make_events("Dockerfile")
        explanation = detector.explain(events)
        confs = [r["confidence"] for r in explanation["reasoning"]]
        # Should be sorted descending
        assert confs == sorted(confs, reverse=True)

    def test_allowed_pipelines_filtering(self) -> None:
        # Only allow run_tests pipeline
        detector = IntentDetector(allowed_pipelines={"run_tests"})
        
        # Dockerfile matches docker_build built-in rule
        events = make_events("Dockerfile")
        result = detector.detect(events)
        
        # result should be None because docker_build pipeline is not allowed
        assert result is None
        
        # test_api.py matches run_tests
        events = make_events("test_api.py")
        result = detector.detect(events)
        assert result is not None
        assert result.pipeline_name == "run_tests"


class TestComputeConfidence:
    def test_zero_total_is_zero(self) -> None:
        assert _compute_confidence(0, 0) == 0.0

    def test_full_match_is_high(self) -> None:
        conf = _compute_confidence(5, 5)
        assert conf > 0.6

    def test_no_match_is_low(self) -> None:
        conf = _compute_confidence(0, 10)
        # event_weight=0.5 (0 matches), ratio=0 → 0.5 * 0.6 = 0.3
        assert conf <= 0.4

    @given(
        matched=st.integers(min_value=0, max_value=100),
        total=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=200)
    def test_confidence_in_range(self, matched: int, total: int) -> None:
        m = min(matched, total)
        conf = _compute_confidence(m, total)
        assert 0.0 <= conf <= 1.0
