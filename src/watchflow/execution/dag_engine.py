"""DAG-based pipeline execution engine using networkx and asyncio."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import networkx as nx
import structlog

from watchflow.core.events import PipelineEvent, PipelineEventType
from watchflow.utils.helpers import calculate_backoff, substitute_template
from watchflow.utils.process_helpers import ProcessManager, ProcessResult

if TYPE_CHECKING:
    from watchflow.config.schema import CommandConfig, PipelineConfig
    from watchflow.core.event_bus import EventBus

log: structlog.BoundLogger = structlog.get_logger(__name__)


@dataclass
class StepResult:
    name: str
    success: bool
    skipped: bool = False
    duration_ms: float = 0.0
    stdout: str = ""
    stderr: str = ""
    attempts: int = 1
    error: str = ""


@dataclass
class PipelineResult:
    pipeline_name: str
    success: bool
    steps: list[StepResult] = field(default_factory=list)
    total_duration_ms: float = 0.0
    error: str = ""


class DAGEngine:
    """Execute a pipeline as a DAG, running independent commands in parallel."""

    def __init__(self, bus: EventBus | None = None, dry_run: bool = False) -> None:
        self._bus = bus
        self._proc_manager = ProcessManager()
        self._dry_run = dry_run

    async def execute(
        self,
        pipeline: PipelineConfig,
        context: dict[str, str] | None = None,
    ) -> PipelineResult:
        """Execute *pipeline* respecting dependency order and fail_fast setting."""
        import time

        ctx = context or {}
        start = time.monotonic()
        step_results: dict[str, StepResult] = {}
        failed = False

        if self._bus:
            self._bus.publish(
                PipelineEvent(
                    pipeline_name=pipeline.name,
                    event_type=PipelineEventType.STARTED,
                )
            )

        # Build execution graph
        graph = self._build_graph(pipeline)
        generations = list(nx.topological_generations(graph))

        try:
            async with asyncio.timeout(pipeline.total_timeout):
                for generation in generations:
                    if failed and pipeline.fail_fast:
                        for name in generation:
                            step_results[name] = StepResult(
                                name=name, success=False, skipped=True
                            )
                        continue

                    cmd_map = {cmd.name: cmd for cmd in pipeline.commands}
                    tasks = [
                        self._execute_step(cmd_map[name], ctx, pipeline)
                        for name in generation
                        if name in cmd_map
                    ]
                    results: list[StepResult] = await asyncio.gather(*tasks)
                    for r in results:
                        step_results[r.name] = r
                        if not r.success and not r.skipped:
                            failed = True
        except TimeoutError:
            failed = True
            error_msg = f"Pipeline '{pipeline.name}' timed out after {pipeline.total_timeout}s"
            log.error("dag.pipeline_timeout", pipeline=pipeline.name)
            total_ms = (time.monotonic() - start) * 1000
            result = PipelineResult(
                pipeline_name=pipeline.name,
                success=False,
                steps=list(step_results.values()),
                total_duration_ms=total_ms,
                error=error_msg,
            )
            if self._bus:
                self._bus.publish(
                    PipelineEvent(
                        pipeline_name=pipeline.name,
                        event_type=PipelineEventType.FAILED,
                        error=error_msg,
                        duration_ms=total_ms,
                    )
                )
            return result

        total_ms = (time.monotonic() - start) * 1000
        success = not failed
        result = PipelineResult(
            pipeline_name=pipeline.name,
            success=success,
            steps=list(step_results.values()),
            total_duration_ms=total_ms,
        )

        if self._bus:
            self._bus.publish(
                PipelineEvent(
                    pipeline_name=pipeline.name,
                    event_type=PipelineEventType.COMPLETED if success else PipelineEventType.FAILED,
                    duration_ms=total_ms,
                )
            )

        log.info(
            "dag.pipeline_done",
            pipeline=pipeline.name,
            success=success,
            duration_ms=round(total_ms, 1),
        )
        return result

    def _analyze_failure(self, stderr: str) -> str:
        """Analyze stderr and return a self-healing hint if a known pattern matches."""
        stderr_lower = stderr.lower()
        if "command not found" in stderr_lower or "is not recognized" in stderr_lower:
            return "\n[HEAL]: Ensure the command is installed and available in PATH."
        if "modulenotfounderror" in stderr_lower or "no module named" in stderr_lower:
            return "\n[HEAL]: Missing Python dependency. Run 'pip install <module>'."
        if "permission denied" in stderr_lower:
            return "\n[HEAL]: File permission error. Check system privileges."
        if "no such file or directory" in stderr_lower:
            return "\n[HEAL]: Path does not exist. Verify the working directory and inputs."
        return ""

    async def pre_warm(self, pipeline: PipelineConfig) -> None:
        """Speculatively prepare the execution environment for a pipeline."""
        log.info("dag.pre_warm", pipeline=pipeline.name)
        if self._bus:
            self._bus.publish(
                PipelineEvent(
                    pipeline_name=pipeline.name,
                    event_type=getattr(PipelineEventType, "PRE_WARM", PipelineEventType.STARTED),
                )
            )
        # In a real distributed system, we would allocate workers here.
        # For this local CLI, we just log and resolve config templates early.
        await asyncio.sleep(0.01)

    async def _execute_step(
        self,
        cmd: CommandConfig,
        ctx: dict[str, str],
        pipeline: PipelineConfig,
    ) -> StepResult:
        import time

        if self._bus:
            self._bus.publish(
                PipelineEvent(
                    pipeline_name=pipeline.name,
                    event_type=PipelineEventType.STEP_STARTED,
                    step_name=cmd.name,
                )
            )

        start = time.monotonic()
        resolved_cmd = substitute_template(cmd.cmd, ctx)
        cwd = Path(cmd.cwd) if cmd.cwd else None

        last_result: ProcessResult | None = None
        attempts = 0
        
        if self._dry_run:
            log.info("dag.dry_run", step=cmd.name, cmd=resolved_cmd)
            await asyncio.sleep(0.01)
            last_result = ProcessResult(
                returncode=0,
                stdout=f"DRY RUN: Skipped execution of '{resolved_cmd}'",
                stderr="",
                duration_ms=10.0,
            )
            attempts = 1
        else:
            for attempt in range(cmd.retry + 1):
                attempts = attempt + 1
                last_result = await self._proc_manager.run(
                    resolved_cmd,
                    cwd=cwd,
                    env=cmd.env or {},
                    timeout=cmd.timeout,
                )
                if last_result.success:
                    break
                if attempt < cmd.retry:
                    delay = calculate_backoff(attempt, cmd.retry_strategy)
                    log.warning(
                        "dag.step_retry",
                        step=cmd.name,
                        attempt=attempt + 1,
                        delay_s=delay,
                    )
                    await asyncio.sleep(delay)

        duration_ms = (time.monotonic() - start) * 1000
        assert last_result is not None
        success = last_result.success
        
        error_msg = last_result.stderr if not success else ""
        if not success and error_msg:
            error_msg += self._analyze_failure(error_msg)
            
        step = StepResult(
            name=cmd.name,
            success=success,
            duration_ms=duration_ms,
            stdout=last_result.stdout,
            stderr=last_result.stderr,
            attempts=attempts,
            error=error_msg,
        )

        event_type = PipelineEventType.STEP_COMPLETED if success else PipelineEventType.STEP_FAILED
        if self._bus:
            self._bus.publish(
                PipelineEvent(
                    pipeline_name=pipeline.name,
                    event_type=event_type,
                    step_name=cmd.name,
                    duration_ms=duration_ms,
                    error=step.error,
                )
            )

        log.debug(
            "dag.step_done",
            step=cmd.name,
            success=success,
            duration_ms=round(duration_ms, 1),
            attempts=attempts,
        )
        return step

    @staticmethod
    def _build_graph(pipeline: PipelineConfig) -> nx.DiGraph:
        g: nx.DiGraph = nx.DiGraph()
        for cmd in pipeline.commands:
            g.add_node(cmd.name)
            for dep in cmd.depends_on:
                g.add_edge(dep, cmd.name)
        return g

    def visualize(self, pipeline: PipelineConfig) -> Any:
        """Return a rich Renderable (Tree) representation of the pipeline DAG."""
        from rich.text import Text
        from rich.tree import Tree

        graph = self._build_graph(pipeline)
        tree = Tree(f"[bold cyan]Pipeline:[/bold cyan] {pipeline.name}", guide_style="bold blue")

        try:
            generations = list(nx.topological_generations(graph))
        except nx.NetworkXUnfeasible:
            return Text(f"Pipelines '{pipeline.name}' has cycles — cannot visualize", style="red bold")

        for i, gen in enumerate(generations):
            layer_node = tree.add(f"[magenta]Layer {i}[/magenta]")
            for node_name in sorted(gen):
                # find the command config to show details
                cmd = next((c for c in pipeline.commands if c.name == node_name), None)
                if cmd:
                    deps = f"[dim] (deps: {','.join(cmd.depends_on)})[/dim]" if cmd.depends_on else ""
                    timeout = f"[dim] (timeout: {cmd.timeout}s)[/dim]" if cmd.timeout else ""
                    layer_node.add(f"[green]■[/green] {node_name}{deps}{timeout}")
                else:
                    layer_node.add(f"[green]■[/green] {node_name}")
                    
        return tree
