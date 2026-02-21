"""Tests for the DAG execution engine."""

from __future__ import annotations

import pytest

from watchflow.config.schema import CommandConfig, PipelineConfig, RetryStrategy
from watchflow.execution.dag_engine import DAGEngine


def make_pipeline(*cmds: CommandConfig, **kwargs) -> PipelineConfig:
    return PipelineConfig(name="test", commands=list(cmds), **kwargs)


def make_cmd(name: str, cmd: str, timeout: float = 5.0, **kwargs) -> CommandConfig:
    return CommandConfig(name=name, cmd=cmd, timeout=timeout, **kwargs)


@pytest.mark.asyncio
async def test_dry_run_command_success() -> None:
    pipeline = make_pipeline(make_cmd("echo_cmd", "echo hello"))
    engine = DAGEngine(dry_run=True)
    result = await engine.execute(pipeline)

    assert result.success
    assert len(result.steps) == 1
    assert result.steps[0].name == "echo_cmd"
    assert "DRY RUN" in result.steps[0].stdout


@pytest.mark.asyncio
async def test_simple_command_success() -> None:
    pipeline = make_pipeline(make_cmd("echo", "echo hello"))
    engine = DAGEngine()
    result = await engine.execute(pipeline)
    assert result.success
    assert result.steps[0].name == "echo"
    assert "hello" in result.steps[0].stdout


@pytest.mark.asyncio
async def test_failing_command() -> None:
    pipeline = make_pipeline(make_cmd("fail", "exit 1"))
    engine = DAGEngine()
    result = await engine.execute(pipeline)
    assert not result.success


@pytest.mark.asyncio
async def test_fail_fast_skips_dependents() -> None:
    cmds = [
        make_cmd("fail", "exit 1"),
        make_cmd("skip", "echo should_skip", depends_on=["fail"]),
    ]
    pipeline = make_pipeline(*cmds, fail_fast=True)
    engine = DAGEngine()
    result = await engine.execute(pipeline)
    assert not result.success
    skipped = [s for s in result.steps if s.skipped]
    assert len(skipped) >= 1


@pytest.mark.asyncio
async def test_parallel_execution_order() -> None:
    """Independent commands should both succeed."""
    cmds = [
        make_cmd("a", "echo a"),
        make_cmd("b", "echo b"),
    ]
    pipeline = make_pipeline(*cmds)
    engine = DAGEngine()
    result = await engine.execute(pipeline)
    assert result.success
    assert all(s.success for s in result.steps)


@pytest.mark.asyncio
async def test_template_substitution() -> None:
    cmds = [make_cmd("greet", "echo hello_{intent}")]
    pipeline = make_pipeline(*cmds)
    engine = DAGEngine()
    result = await engine.execute(pipeline, context={"intent": "world"})
    assert "hello_world" in result.steps[0].stdout


@pytest.mark.asyncio
async def test_total_timeout() -> None:
    cmds = [make_cmd("slow", "python -c \"import time; time.sleep(10)\"")]
    pipeline = make_pipeline(*cmds, total_timeout=0.1)
    engine = DAGEngine()
    result = await engine.execute(pipeline)
    assert not result.success
    assert "timed out" in result.error


@pytest.mark.asyncio
async def test_retry_on_failure() -> None:
    """Command should retry and record attempt count."""
    cmds = [make_cmd("flaky", "exit 1", retry=2, retry_strategy=RetryStrategy.IMMEDIATE)]
    pipeline = make_pipeline(*cmds)
    engine = DAGEngine()
    result = await engine.execute(pipeline)
    assert not result.success
    assert result.steps[0].attempts == 3  # 1 original + 2 retries


def test_visualize() -> None:
    cmds = [
        make_cmd("build", "echo build"),
        make_cmd("test", "echo test", depends_on=["build"]),
    ]
    pipeline = make_pipeline(*cmds)
    engine = DAGEngine()
    art = engine.visualize(pipeline)
    
    # Render the tree to a string for testing
    from rich.console import Console
    import io
    
    console = Console(file=io.StringIO(), force_terminal=False)
    console.print(art)
    output = console.file.getvalue()
    
    assert "build" in output
    assert "test" in output
    assert "Layer" in output
