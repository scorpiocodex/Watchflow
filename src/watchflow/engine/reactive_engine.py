"""Top-level orchestrator for WatchFlow's reactive engine."""

from __future__ import annotations

import asyncio
import signal
from pathlib import Path

import structlog
from rich.console import Console

from watchflow.config.loader import load_config
from watchflow.config.schema import GlobalConfig
from watchflow.core.event_bus import EventBus
from watchflow.core.events import (
    AnyEvent,
    FileSystemEvent,
    IntentEvent,
    SystemEvent,
)
from watchflow.core.signal_router import SignalRouter
from watchflow.core.state_machine import ReactiveStateMachine, State
from watchflow.core.task_supervisor import TaskSupervisor
from watchflow.core.wal import WriteAheadLog
from watchflow.execution.dag_engine import DAGEngine
from watchflow.hooks.plugin_system import HookPoint, HookRegistry
from watchflow.intelligence.intent_detector import IntentDetector
from watchflow.plugins.builtin import register_builtin_plugins
from watchflow.telemetry.metrics import ResourceMonitor, TelemetryStore
from watchflow.tui.renderer import WatchFlowRenderer
from watchflow.utils.helpers import current_ms
from watchflow.watchers.watcher_matrix import WatcherMatrix

log: structlog.BoundLogger = structlog.get_logger(__name__)


class ReactiveEngine:
    """Wire together all WatchFlow subsystems and run the main event loop."""

    def __init__(
        self,
        config: GlobalConfig,
        console: Console | None = None,
        config_path: Path | None = None,
        dry_run: bool = False,
    ) -> None:
        self.config = config
        self._config_path = config_path
        self._config_mtime = (
            config_path.stat().st_mtime if config_path and config_path.exists() else 0.0
        )
        self._console = console or Console()
        self._bus = EventBus()
        self._state = ReactiveStateMachine(bus=self._bus)
        self._supervisor = TaskSupervisor()
        self._store = TelemetryStore()
        self._hook_registry = HookRegistry()
        pipeline_names = {p.name for p in config.pipelines}
        self._intent_detector = IntentDetector(
            user_rules=config.intent_rules, allowed_pipelines=pipeline_names
        )
        self._router = SignalRouter(config, self._intent_detector)
        self._dag_engine = DAGEngine(bus=self._bus, dry_run=dry_run)
        self._watcher_matrix = WatcherMatrix(self._bus)
        self._renderer = WatchFlowRenderer(store=self._store, console=self._console)
        self._resource_monitor = ResourceMonitor(self._store)
        self._pipeline_map = {p.name: p for p in config.pipelines}
        self._fs_queue: asyncio.Queue[FileSystemEvent] = asyncio.Queue()
        self._wal = WriteAheadLog()
        self._last_pipeline_ms: float = 0.0
        self._running = False
        self._stop_event = asyncio.Event()

        register_builtin_plugins(self._hook_registry)

    @classmethod
    def from_config_file(
        cls, path: Path, console: Console | None = None, dry_run: bool = False
    ) -> ReactiveEngine:
        """Load config from *path* and return a fully-wired engine."""
        config = load_config(path)
        return cls(config, console=console, config_path=path, dry_run=dry_run)

    @property
    def store(self) -> TelemetryStore:
        return self._store

    async def start(self) -> None:
        """Start the engine: wire watchers, spawn tasks, enter the main loop."""
        log.info("engine.starting")
        self._running = True

        # Setup signal handlers
        import contextlib

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, lambda: asyncio.ensure_future(self.stop()))

        # Configure watchers
        self._watcher_matrix.setup(self.config.watchers)

        # Transition to WATCHING
        await self._state.transition(State.WATCHING)

        # Sync renderer state
        self._renderer.state = self._state.state.name

        # Subscribe to bus events for TUI and internal routing
        tui_queue = self._bus.subscribe()
        fs_sub_queue = self._bus.subscribe()
        wal_queue = self._bus.subscribe()

        # Fire startup hook
        await self._hook_registry.fire(HookPoint.ON_STARTUP)

        # Start TUI only if not in daemon mode
        import os

        if os.environ.get("WATCHFLOW_DAEMON") != "1":
            self._renderer.start()

        # Spawn supervised tasks
        if self._config_path:
            self._supervisor.spawn("config_watcher", self._watch_config())
        self._supervisor.spawn("resource_monitor", self._resource_monitor.run())
        self._supervisor.spawn("tui_feed", self._feed_tui(tui_queue))
        self._supervisor.spawn("event_collector", self._collect_fs_events(fs_sub_queue))
        self._supervisor.spawn("wal_writer", self._record_wal(wal_queue))
        self._supervisor.spawn("watcher_matrix", self._run_watcher())

        # Main processing loop
        await self._main_loop()

    async def stop(self) -> None:
        """Graceful shutdown."""
        if not self._running:
            return
        self._running = False
        log.info("engine.stopping")

        try:
            if self._state.can_transition(State.SHUTTING_DOWN):
                await self._state.transition(State.SHUTTING_DOWN)
        except Exception:
            pass

        await self._hook_registry.fire(HookPoint.ON_SHUTDOWN)
        self._watcher_matrix.stop()
        await self._supervisor.cancel_all(timeout=5.0)
        self._renderer.stop()
        self._wal.close()
        self._store.close()
        self._stop_event.set()
        log.info("engine.stopped")

    async def _record_wal(self, queue: asyncio.Queue[AnyEvent]) -> None:
        """Continuously drain the queue and record events to WAL."""
        while self._running:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=2.0)
                await asyncio.to_thread(self._wal.record, event)
            except TimeoutError:
                continue

    async def _run_watcher(self) -> None:
        self._watcher_matrix.start()
        await self._stop_event.wait()

    async def _watch_config(self) -> None:
        """Poll the config file for zero-downtime hot-reloading."""
        while self._running:
            await asyncio.sleep(2.0)
            if not self._config_path or not self._config_path.exists():
                continue
            try:
                mtime = self._config_path.stat().st_mtime
                if mtime > self._config_mtime:
                    self._config_mtime = mtime
                    self._reload_config()
            except Exception as e:
                log.error("engine.config_reload_error", exc=str(e))

    def _reload_config(self) -> None:
        if self._config_path is None:
            return
        try:
            new_config = load_config(self._config_path)
            self.config = new_config
            self._pipeline_map = {p.name: p for p in new_config.pipelines}
            pipeline_names = {p.name for p in new_config.pipelines}
            self._intent_detector = IntentDetector(
                user_rules=new_config.intent_rules,
                allowed_pipelines=pipeline_names,
            )
            self._router = SignalRouter(new_config, self._intent_detector)
            msg = f"Zero-downtime hot-reload completed for {self._config_path.name}"
            log.info("engine.config_reloaded")
            self._bus.publish(SystemEvent(message=msg, level="info"))
        except Exception as e:
            self._bus.publish(SystemEvent(message=f"Hot-reload failed: {e}", level="error"))

    async def _feed_tui(self, queue: asyncio.Queue[AnyEvent]) -> None:
        while self._running:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.5)
                self._renderer.on_event(event)
                if isinstance(event, FileSystemEvent):
                    self._store.record_event()
            except TimeoutError:
                continue

    async def _collect_fs_events(self, queue: asyncio.Queue[AnyEvent]) -> None:
        """Collect filesystem events from the bus into a local queue for batching."""
        while self._running:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.5)
                if isinstance(event, FileSystemEvent):
                    await self._fs_queue.put(event)
            except TimeoutError:
                continue

    async def _safe_transition(self, state: State) -> None:
        """Transition only if not already in a terminal state."""
        if not self._state.is_terminal():
            await self._state.transition(state)

    async def _main_loop(self) -> None:
        """Main processing loop: collect events → intent → pipeline execution."""
        idle_fire_ms = current_ms()
        idle_threshold_ms = 30_000  # fire on_idle after 30s without events

        while self._running and not self._state.is_terminal():
            # Drain the filesystem event queue into a batch
            batch: list[FileSystemEvent] = []
            try:
                while True:
                    ev = self._fs_queue.get_nowait()
                    batch.append(ev)
            except asyncio.QueueEmpty:
                pass

            if not batch:
                # Check idle
                if current_ms() - idle_fire_ms > idle_threshold_ms:
                    await self._hook_registry.fire(HookPoint.ON_IDLE)
                    idle_fire_ms = current_ms()
                await asyncio.sleep(0.05)
                continue

            idle_fire_ms = current_ms()

            # Detect intent
            await self._safe_transition(State.DETECTING)
            decision = self._router.route(batch)
            if decision is None:
                # Attempt speculative pre-warming
                if hasattr(self._router, "speculate"):
                    speculative = self._router.speculate(batch)
                    if speculative is not None:
                        speculative_pipeline = self._pipeline_map.get(speculative.pipeline_name)
                        if speculative_pipeline:
                            # Run pre-warm blindly in the background
                            self._supervisor.spawn(
                                "pre_warm_" + speculative.pipeline_name,
                                self._dag_engine.pre_warm(speculative_pipeline),
                            )

                await self._safe_transition(State.WATCHING)
                continue

            # Publish intent event
            self._bus.publish(
                IntentEvent(
                    intent_name=decision.intent_name,
                    pipeline_name=decision.pipeline_name,
                    confidence=decision.confidence,
                    source_events=batch,
                )
            )

            # Cooldown check
            now_ms = current_ms()
            if now_ms - self._last_pipeline_ms < self.config.cooldown_ms:
                log.debug(
                    "engine.cooldown",
                    remaining_ms=self.config.cooldown_ms - (now_ms - self._last_pipeline_ms),
                )
                await self._safe_transition(State.WATCHING)
                continue

            # Dynamic Resource Throttling
            res = self._store.latest_resource()
            if res and (res.cpu_percent > 90.0 or res.memory_mb > 2000.0):
                msg = f"Resource critical (CPU: {res.cpu_percent:.1f}%, RAM: {res.memory_mb:.0f}MB) — throttling pipeline."
                log.warning("engine.throttle", cpu=res.cpu_percent, ram=res.memory_mb)
                self._bus.publish(SystemEvent(message=msg, level="warning"))
                await self._safe_transition(State.WATCHING)
                await asyncio.sleep(2.0)
                continue

            # Resolve pipeline
            pipeline = self._pipeline_map.get(decision.pipeline_name)
            if pipeline is None:
                msg = f"Unknown pipeline: {decision.pipeline_name}"
                log.warning("engine.unknown_pipeline", name=decision.pipeline_name)
                self._bus.publish(SystemEvent(message=msg, level="error"))
                await self._safe_transition(State.WATCHING)
                continue

            # Planning → Executing
            await self._safe_transition(State.PLANNING)
            await self._hook_registry.fire(
                HookPoint.BEFORE_PIPELINE,
                pipeline_name=pipeline.name,
            )
            await self._safe_transition(State.EXECUTING)
            self._last_pipeline_ms = current_ms()

            try:
                result = await self._dag_engine.execute(pipeline, context=decision.context)
            except Exception as exc:
                log.exception("engine.execute_error", exc=str(exc))
                result = None

            if result and result.success:
                await self._hook_registry.fire(
                    HookPoint.AFTER_PIPELINE,
                    pipeline_name=pipeline.name,
                    success=True,
                )
                await self._safe_transition(State.WATCHING)
            else:
                error_msg = result.error if result else "Unknown error"
                await self._hook_registry.fire(
                    HookPoint.ON_FAILURE,
                    pipeline_name=pipeline.name,
                    error=error_msg,
                )
                await self._hook_registry.fire(
                    HookPoint.AFTER_PIPELINE,
                    pipeline_name=pipeline.name,
                    success=False,
                )
                await self._safe_transition(State.RECOVERING)
                await asyncio.sleep(1.0)
                await self._safe_transition(State.WATCHING)

            if result:
                self._store.record_pipeline(pipeline.name, result.success, result.total_duration_ms)
