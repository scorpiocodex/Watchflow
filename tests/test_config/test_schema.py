"""Tests for Pydantic v2 config schema validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from watchflow.config.schema import (
    CommandConfig,
    GlobalConfig,
    PipelineConfig,
    RetryStrategy,
    WatcherConfig,
)


def make_cmd(**kwargs) -> CommandConfig:
    return CommandConfig(name="test", cmd="echo hi", **kwargs)


class TestCommandConfig:
    def test_defaults(self) -> None:
        cmd = make_cmd()
        assert cmd.timeout == 30.0
        assert cmd.retry == 0
        assert cmd.retry_strategy == RetryStrategy.EXPONENTIAL

    def test_invalid_timeout(self) -> None:
        with pytest.raises(ValidationError):
            CommandConfig(name="x", cmd="x", timeout=-1)

    def test_retry_cap(self) -> None:
        with pytest.raises(ValidationError):
            CommandConfig(name="x", cmd="x", retry=11)


class TestPipelineConfig:
    def test_valid_dag(self) -> None:
        cmds = [
            CommandConfig(name="a", cmd="echo a"),
            CommandConfig(name="b", cmd="echo b", depends_on=["a"]),
        ]
        p = PipelineConfig(name="p", commands=cmds)
        assert len(p.commands) == 2

    def test_cycle_raises(self) -> None:
        cmds = [
            CommandConfig(name="a", cmd="echo a", depends_on=["b"]),
            CommandConfig(name="b", cmd="echo b", depends_on=["a"]),
        ]
        with pytest.raises(ValidationError, match="cycle"):
            PipelineConfig(name="cycle_pipe", commands=cmds)

    def test_missing_dep_raises(self) -> None:
        cmds = [CommandConfig(name="a", cmd="echo", depends_on=["nonexistent"])]
        with pytest.raises(ValidationError, match="unknown command"):
            PipelineConfig(name="p", commands=cmds)


class TestWatcherConfig:
    def test_debounce_bounds(self) -> None:
        with pytest.raises(ValidationError):
            WatcherConfig(name="w", paths=["."], debounce_ms=10)  # below 50
        with pytest.raises(ValidationError):
            WatcherConfig(name="w", paths=["."], debounce_ms=99999)  # above 30000

    def test_valid(self) -> None:
        w = WatcherConfig(name="w", paths=["src/"])
        assert w.recursive is True
        assert w.hash_check is False


class TestGlobalConfig:
    def test_invalid_pipeline_ref(self) -> None:
        cfg_data = {
            "pipelines": [
                {
                    "name": "p1",
                    "commands": [{"name": "c", "cmd": "echo"}],
                }
            ],
            "intent_rules": [
                {
                    "name": "r1",
                    "patterns": ["*.py"],
                    "pipeline": "nonexistent",
                }
            ],
        }
        with pytest.raises(ValidationError, match="unknown pipeline"):
            GlobalConfig.model_validate(cfg_data)

    def test_empty_is_valid(self) -> None:
        cfg = GlobalConfig()
        assert cfg.watchers == []
        assert cfg.pipelines == []
