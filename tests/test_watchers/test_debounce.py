"""Tests for the AdaptiveDebouncer."""

from __future__ import annotations

import time

from hypothesis import given, settings
from hypothesis import strategies as st

from watchflow.watchers.watcher_matrix import AdaptiveDebouncer


class TestAdaptiveDebouncer:
    def test_no_events_returns_base(self) -> None:
        d = AdaptiveDebouncer(base_ms=500)
        assert d.current_delay_ms() == 500

    def test_burst_events_returns_max(self) -> None:
        d = AdaptiveDebouncer(base_ms=500, max_ms=2000)
        # Simulate very rapid events (~10ms apart)
        for _ in range(10):
            d.record_event()
            time.sleep(0.005)  # 5ms between calls
        # avg interval < 50ms → should return max_ms
        assert d.current_delay_ms() == 2000

    def test_idle_events_returns_min(self) -> None:
        d = AdaptiveDebouncer(base_ms=500, min_ms=50)
        # Simulate slow events (>500ms apart)
        for _ in range(5):
            d.record_event()
            time.sleep(0.55)
        assert d.current_delay_ms() == 50

    def test_single_event_returns_base(self) -> None:
        d = AdaptiveDebouncer(base_ms=300)
        d.record_event()
        # Only one event, no interval recorded
        assert d.current_delay_ms() == 300

    @given(
        base=st.integers(min_value=50, max_value=5000),
        events=st.integers(min_value=0, max_value=20),
    )
    @settings(max_examples=100)
    def test_delay_within_bounds(self, base: int, events: int) -> None:
        d = AdaptiveDebouncer(base_ms=base, min_ms=50, max_ms=base * 4 + 50)
        for _ in range(events):
            d.record_event()
        delay = d.current_delay_ms()
        assert 50 <= delay <= base * 4 + 50
