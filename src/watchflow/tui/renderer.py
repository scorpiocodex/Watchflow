"""Rich Live TUI renderer — responsive breakpoints, 8 panels, branded identity."""

from __future__ import annotations

import shutil
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from watchflow.core.events import (
    AnyEvent,
    FileSystemEvent,
    FSEventType,
    IntentEvent,
    PipelineEvent,
    PipelineEventType,
    StateEvent,
    SystemEvent,
)

if TYPE_CHECKING:
    from watchflow.telemetry.metrics import TelemetryStore

log: structlog.BoundLogger = structlog.get_logger(__name__)


# ─── Visual constants ─────────────────────────────────────────────────────────

_STATE_COLOR: dict[str, str] = {
    "IDLE": "dim cyan",
    "WATCHING": "bold cyan",
    "DETECTING": "bold magenta",
    "PLANNING": "bold yellow",
    "EXECUTING": "bold green",
    "RECOVERING": "bold red",
    "SHUTTING_DOWN": "bright_red",
}

_STATE_ICON: dict[str, str] = {
    "IDLE": "◒",
    "WATCHING": "⟡",
    "DETECTING": "◎",
    "PLANNING": "◈",
    "EXECUTING": "▶",
    "RECOVERING": "⚠",
    "SHUTTING_DOWN": "■",
}

_FS_ICONS: dict[FSEventType, str] = {
    FSEventType.CREATED: "＋",
    FSEventType.MODIFIED: "～",
    FSEventType.DELETED: "✕",
    FSEventType.MOVED: "→",
}

_PIPE_ICONS: dict[PipelineEventType, str] = {
    PipelineEventType.STARTED: "▶",
    PipelineEventType.COMPLETED: "✔",
    PipelineEventType.FAILED: "✖",
    PipelineEventType.SKIPPED: "⏭",
    PipelineEventType.STEP_STARTED: "⏳",
    PipelineEventType.STEP_COMPLETED: "✔",
    PipelineEventType.STEP_FAILED: "✖",
}

_COLOR: dict[str, str] = {
    "fs": "cyan",
    "intent": "magenta",
    "success": "bold green",
    "failure": "bold red",
    "warning": "bold yellow",
    "info": "bright_blue",
    "state": "bright_white",
    "system": "dim cyan",
}


# ─── Fading event ─────────────────────────────────────────────────────────────

@dataclass
class FadingEvent:
    """A signal-stream entry with time-based opacity decay."""

    text: str
    color: str
    created_at: float = field(default_factory=time.monotonic)
    fade_after_s: float = 30.0
    count: int = 1

    @property
    def age_s(self) -> float:
        return time.monotonic() - self.created_at

    @property
    def is_expired(self) -> bool:
        return self.age_s >= self.fade_after_s

    @property
    def opacity_style(self) -> str:
        age = self.age_s
        if age < 5:
            return self.color
        if age < 15:
            return f"dim {self.color}"
        return "dim white"

    @property
    def display_text(self) -> str:
        if self.count > 1:
            return f"{self.text}  [dim]({self.count}x)[/dim]"
        return self.text


# ─── Renderer ─────────────────────────────────────────────────────────────────

class WatchFlowRenderer:
    """Rich Live display with adaptive breakpoints.

    Breakpoints (terminal width):
    - <70     MINIMAL      — branded status bar only
    - 70-109  COMPACT      — status bar + signal stream
    - 110-159 ADVANCED     — status, intent, signal stream, execution graph
    - ≥160    HOLOGRAPHIC  — all 8 panels
    """

    _MAX_SIGNALS = 50
    _REFRESH_RATE = 20  # fps

    def __init__(self, store: TelemetryStore | None = None, console: Console | None = None) -> None:
        self._store = store
        self._console = console or Console()
        self._live: Live | None = None
        self._signals: deque[FadingEvent] = deque(maxlen=self._MAX_SIGNALS)
        self._current_state = "IDLE"
        self._active_pipelines: dict[str, float] = {}  # name → start time
        self._active_steps: dict[str, str] = {}         # pipeline → current step
        self._recent_intents: deque[tuple[str, float, float]] = deque(maxlen=5)
        self._pipeline_history: deque[tuple[str, str, float, bool]] = deque(maxlen=5)  # name, step, duration, success
        self._plugin_log: deque[str] = deque(maxlen=10)
        self._started_at = time.monotonic()
        self._total_events: int = 0
        self._event_rate_window: deque[float] = deque(maxlen=60)  # timestamps

    @property
    def state(self) -> str:
        return self._current_state

    @state.setter
    def state(self, value: str) -> None:
        self._current_state = value.upper()
        self._refresh()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._live = Live(
            self._render(),
            console=self._console,
            refresh_per_second=self._REFRESH_RATE,
            screen=False,
        )
        self._live.start()

    def stop(self) -> None:
        if self._live:
            self._live.stop()

    # ── Event ingestion ───────────────────────────────────────────────────────

    def on_event(self, event: AnyEvent) -> None:
        """Process an incoming event and update internal state."""
        if isinstance(event, FileSystemEvent):
            icon = _FS_ICONS.get(event.event_type, "•")
            text = f"{icon}  {event.path}"
            
            # Simple deduplication: if the last signal is the same, increment count
            if self._signals and self._signals[0].text == text:
                self._signals[0].created_at = time.monotonic()  # Refresh timestamp
                self._signals[0].count += 1
            else:
                self._signals.appendleft(FadingEvent(text=text, color=_COLOR["fs"]))
            
            self._total_events += 1
            self._event_rate_window.append(time.monotonic())

        elif isinstance(event, IntentEvent):
            text = (
                f"🧠  {event.intent_name}  →  {event.pipeline_name}  "
                f"({event.confidence:.0%})"
            )
            self._signals.appendleft(FadingEvent(text=text, color=_COLOR["intent"]))
            self._recent_intents.appendleft(
                (event.intent_name, event.confidence, time.monotonic())
            )

        elif isinstance(event, StateEvent):
            self._current_state = event.current.upper()
            # We no longer add state transitions to the signal stream to reduce noise
            # text = f"⚙  {event.previous}  →  {event.current}"
            # self._signals.appendleft(FadingEvent(text=text, color=_COLOR["state"]))

        elif isinstance(event, PipelineEvent):
            icon = _PIPE_ICONS.get(event.event_type, "•")
            if event.event_type == PipelineEventType.STARTED:
                self._active_pipelines[event.pipeline_name] = time.monotonic()
            elif event.event_type in (
                PipelineEventType.COMPLETED,
                PipelineEventType.FAILED,
            ):
                self._active_pipelines.pop(event.pipeline_name, None)
                self._active_steps.pop(event.pipeline_name, None)
                self._pipeline_history.appendleft(
                    (
                        event.pipeline_name,
                        event.step_name or "",
                        event.duration_ms or 0.0,
                        event.event_type == PipelineEventType.COMPLETED,
                    )
                )
            elif event.event_type == PipelineEventType.STEP_STARTED:
                self._active_steps[event.pipeline_name] = event.step_name

            color = (
                _COLOR["success"]
                if event.event_type == PipelineEventType.COMPLETED
                else (
                    _COLOR["failure"]
                    if "fail" in str(event.event_type)
                    else _COLOR["info"]
                )
            )
            text = f"{icon}  [{event.pipeline_name}] {event.step_name or event.event_type}"
            self._signals.appendleft(FadingEvent(text=text, color=color))

        elif isinstance(event, SystemEvent):
            color = {
                "error": _COLOR["failure"],
                "warning": _COLOR["warning"],
            }.get(event.level, _COLOR["system"])
            text = f"◈  {event.message}"
            self._signals.appendleft(FadingEvent(text=text, color=color))

        self._refresh()

    # ── Rendering helpers ─────────────────────────────────────────────────────

    def _refresh(self) -> None:
        if self._live and self._live.is_started:
            self._live.update(self._render())

    def _width(self) -> int:
        return shutil.get_terminal_size((80, 24)).columns

    def _event_rate(self) -> str:
        """Return events/min over the last 60 seconds."""
        now = time.monotonic()
        recent = sum(1 for t in self._event_rate_window if now - t < 60)
        if recent == 0:
            return "0/min"
        return f"{recent}/min"

    def _render(self) -> Any:
        size = shutil.get_terminal_size((80, 24))
        width = size.columns
        height = size.lines

        # Prune expired signals
        while self._signals and self._signals[-1].is_expired:
            self._signals.pop()

        header = self._render_header()

        if width < 70:
            return Panel(header, border_style="dim blue", padding=(0, 1))

        if width < 110:
            stream = self._render_signal_stream(height=min(14, height - 8))
            return Panel(
                Group(header, Text(""), stream),
                border_style="dim blue",
                padding=(0, 1),
            )

        # ADVANCED and HOLOGRAPHIC
        # We use a max height to avoid pushing the Live display and causing repetition
        max_content_height = min(20, height - 4)
        
        if width < 160:
            left = self._render_intent_analyzer()
            # Dynamic signal height based on available space
            stream_height = max(5, max_content_height - 10)
            right = Group(
                self._render_signal_stream(height=stream_height),
                Text(""),
                self._render_execution_graph(),
            )
            
            grid = Table.grid(expand=True)
            grid.add_column(ratio=2, min_width=30)
            grid.add_column(ratio=3, min_width=50)
            
            grid.add_row(
                Panel(left, title="[dim cyan]Intents[/dim cyan]", border_style="dim blue", expand=True),
                Panel(right, title="[dim cyan]Activity[/dim cyan]", border_style="dim cyan", expand=True),
            )
            return Group(header, Text(""), grid)

        # HOLOGRAPHIC — all 8 panels
        col1 = Group(self._render_intent_analyzer())
        col2 = Group(self._render_signal_stream(height=8), Text(""), self._render_active_tasks())
        col3 = Group(self._render_execution_graph(), Text(""), self._render_diagnostics())
        col4 = Group(self._render_plugin_activity(), Text(""), self._render_resource_monitor())

        grid = Table.grid(expand=True)
        for _ in range(4):
            grid.add_column(ratio=1)
        grid.add_row(
            Panel(col1, title="[dim cyan]Intents[/dim cyan]", border_style="dim blue"),
            Panel(col2, title="[dim cyan]Signals[/dim cyan]", border_style="dim cyan"),
            Panel(col3, title="[dim cyan]Execution[/dim cyan]", border_style="dim magenta"),
            Panel(col4, title="[dim cyan]System[/dim cyan]", border_style="dim green"),
        )
        
        return Group(header, Text(""), grid)

    # ── Panel renderers ───────────────────────────────────────────────────────

    def _render_header(self) -> Text:
        """Dynamic status bar with state, uptime, and metrics."""
        state_color = _STATE_COLOR.get(self._current_state, "white")
        state_icon = _STATE_ICON.get(self._current_state, "○")

        uptime = time.monotonic() - self._started_at
        h = int(uptime // 3600)
        m = int((uptime % 3600) // 60)
        s = int(uptime % 60)
        uptime_str = f"{h:02d}:{m:02d}:{s:02d}"

        t = Text()
        t.append(f"{state_icon} {self._current_state}", style=f"bold {state_color}")
        t.append("  ┼  ", style="dim magenta")
        t.append(f"T+{uptime_str}", style="bold white")

        rate = self._event_rate()
        t.append("  ┼  ", style="dim magenta")
        t.append(f"∑ {rate}", style="bold cyan")

        if self._store:
            s_data = self._store.summary()
            runs = s_data["pipelines_run"]
            ok_rate = s_data["success_rate"]
            if runs > 0:
                ok_color = "green" if ok_rate >= 0.9 else ("yellow" if ok_rate >= 0.7 else "red")
                t.append("  │  ", style="dim white")
                t.append(f"▶ {runs} run{'s' if runs != 1 else ''}", style="dim white")
                t.append(f"  {ok_rate:.0%} ok", style=f"dim {ok_color}")

        return t

    def _render_signal_stream(self, height: int = 12) -> Table:
        table = Table.grid(padding=(0, 0))
        table.add_column(no_wrap=True)
        signals = list(self._signals)[:height]
        
        if not signals:
            table.add_row(Text("  Waiting for file system events…", style="dim white"))
            for _ in range(height - 1):
                table.add_row("")
            return table

        for fe in signals:
            table.add_row(Text.from_markup(fe.display_text, style=fe.opacity_style))
        
        # Fill remaining height with empty rows to prevent jumping
        for _ in range(height - len(signals)):
            table.add_row("")
            
        return table

    def _render_intent_analyzer(self) -> Table:
        table = Table(
            title="[dim]Intent History[/dim]",
            box=None,
            show_header=True,
            header_style="dim magenta",
            padding=(0, 1),
            expand=True,
        )
        table.add_column("Intent", style="magenta", min_width=14)
        table.add_column("Conf", justify="right", min_width=5)
        table.add_column("Age", min_width=8)
        for name, conf, ts in list(self._recent_intents)[:4]:
            age = time.monotonic() - ts
            age_str = f"{age:.0f}s" if age < 60 else (f"{age/60:.0f}m" if age < 3600 else f"{age/3600:.1f}h")
            conf_color = "green" if conf >= 0.8 else ("yellow" if conf >= 0.6 else "red")
            table.add_row(
                name,
                Text(f"{conf:.0%}", style=conf_color),
                Text(f"{age_str} ago", style="dim white"),
            )
        if not self._recent_intents:
            table.add_row(Text("No intents yet", style="dim blue"), "", "")
        return table

    def _render_execution_graph(self) -> Table:
        table = Table(
            title="[dim]Active Pipelines[/dim]",
            box=None,
            show_header=True,
            header_style="dim green",
            padding=(0, 1),
        )
        table.add_column("Pipeline", style="green", min_width=14)
        table.add_column("Step", style="dim white")
        table.add_column("Elapsed/Res", justify="right", min_width=12)
        
        # Active
        for name, start in list(self._active_pipelines.items()):
            elapsed = time.monotonic() - start
            step = self._active_steps.get(name, "…")
            elapsed_color = "green" if elapsed < 10 else ("yellow" if elapsed < 30 else "red")
            table.add_row(
                name,
                step,
                Text(f"{elapsed:.1f}s", style=elapsed_color),
            )
            
        # Recent history
        for name, step, duration, success in list(self._pipeline_history)[:3]:
            res_style = "bold green" if success else "bold red"
            res_text = "✔ ok" if success else "✖ fail"
            dur_str = f"{duration/1000:.1f}s" if duration > 1000 else f"{duration:.0f}ms"
            table.add_row(
                Text(name, style="dim green"),
                Text(step, style="dim white"),
                Text(f"{res_text} ({dur_str})", style=res_style),
            )

        if not self._active_pipelines and not self._pipeline_history:
            table.add_row(Text("idle", style="dim"), "", "")
        return table

    def _render_active_tasks(self) -> Table:
        table = Table(
            title="[dim]Task Queue[/dim]",
            box=None,
            show_header=False,
            padding=(0, 1),
        )
        table.add_column("Task")
        if not self._active_pipelines:
            table.add_row(Text("○  Watching for changes…", style="dim cyan"))
        else:
            for name in self._active_pipelines:
                table.add_row(Text(f"▶  {name}", style="bold yellow"))
        return table

    def _render_diagnostics(self) -> Text:
        t = Text()
        if self._store:
            s = self._store.summary()
            events = s["events"]
            failures = s["failures"]
            t.append(f"Events:    {events}\n", style="white")
            fail_style = "bold red" if failures else "dim white"
            t.append(f"Failures:  {failures}\n", style=fail_style)
            t.append(f"Uptime:    {s['uptime_s']:.0f}s\n", style="dim white")
        return t

    def _render_plugin_activity(self) -> Table:
        table = Table(
            title="[dim]Plugin Log[/dim]",
            box=None,
            show_header=False,
            padding=(0, 1),
        )
        table.add_column("Entry")
        if self._plugin_log:
            for entry in list(self._plugin_log)[:8]:
                table.add_row(Text(entry, style="dim cyan"))
        else:
            table.add_row(Text("No plugin activity", style="dim white"))
        return table

    def _render_resource_monitor(self) -> Text:
        t = Text()
        if self._store:
            snap = self._store.latest_resource()
            if snap:
                cpu = snap.cpu_percent
                mem = snap.memory_mb
                cpu_color = "green" if cpu < 50 else ("yellow" if cpu < 80 else "red")
                mem_color = "green" if mem < 256 else ("yellow" if mem < 512 else "red")
                t.append("CPU  ", style="dim white")
                t.append(f"{cpu:5.1f}%\n", style=cpu_color)
                t.append("RAM  ", style="dim white")
                t.append(f"{mem:5.0f} MB\n", style=mem_color)
            else:
                t.append("Sampling…", style="dim")
        else:
            t.append("Monitor unavailable", style="dim")
        return t
