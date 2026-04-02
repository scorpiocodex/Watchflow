"""WatchFlow CLI — 9 commands with structured output and branded identity."""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from watchflow.cli import daemon

app = typer.Typer(
    name="watchflow",
    help=(
        "[bold cyan]◢ 𝙒𝘼𝙏𝘾𝙃𝙁𝙇𝙊𝙒 ◣[/bold cyan] — [magenta]NEXUS A.I. ORCHESTRATOR[/magenta]\n\n"
        "Next-generation reactive automation platform powered by semantic engine."
    ),
    add_completion=False,
    rich_markup_mode="rich",
    no_args_is_help=True,
)
app.add_typer(daemon.app, name="daemon")
console = Console(stderr=False)
err_console = Console(stderr=True)

# ─── Version ──────────────────────────────────────────────────────────────────


def _version_callback(value: bool) -> None:
    if value:
        import watchflow

        console.print(f"[bold cyan]◢  WatchFlow v{watchflow.__version__} ◣[/bold cyan]")
        raise typer.Exit()


# ─── Global callback (version + debug flags) ──────────────────────────────────


@app.callback(invoke_without_command=True)
def _global(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            callback=_version_callback,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option(
            "--debug",
            help="Enable verbose debug logging to stderr.",
            envvar="WATCHFLOW_DEBUG",
        ),
    ] = False,
) -> None:
    """⚡ WatchFlow — Nexus A.I. Reactive Automation Terminal."""
    # Set debug flag implicitly
    import os

    if debug:
        os.environ["WATCHFLOW_DEBUG"] = "1"

    from watchflow import configure_logging

    configure_logging(debug=debug)

    # Print header when invoked with a subcommand (not --version alone)
    # Skip printing header when in daemon mode
    if (
        ctx.invoked_subcommand is not None
        and os.environ.get("WATCHFLOW_DAEMON") != "1"
        and ctx.invoked_subcommand != "daemon"
    ):
        _print_header()


def _print_header() -> None:
    """Print the branded WatchFlow header bar."""
    import watchflow

    t = Text()
    t.append("◢ 𝙒𝘼𝙏𝘾𝙃𝙁𝙇𝙊𝙒", style="bold cyan")
    t.append(f" // v{watchflow.__version__} ", style="dim cyan")
    t.append("◣\n", style="bold cyan")
    t.append("  ❖ NEXUS A.I. ORCHESTRATOR ❖", style="bold magenta")
    console.print(Panel(t, border_style="cyan", padding=(0, 2)))


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _find_config(config: Path | None) -> Path:
    """Locate a config file or exit with a helpful error."""
    from watchflow.utils.path_utils import find_config_file

    if config is not None:
        if config.exists():
            return config
        # Explicit path was given but file doesn't exist — hard error.
        err_console.print(
            f"[red bold]✖  Config file not found:[/red bold]  {config}\n"
            "  Pass an existing file path with [bold]--config PATH[/bold]."
        )
        raise typer.Exit(1)

    found = find_config_file()
    if found:
        return found
    err_console.print(
        "[red bold]✖  Config not found.[/red bold]\n"
        "  Run [bold cyan]watchflow init[/bold cyan] to create a config file, "
        "or pass [bold]--config PATH[/bold]."
    )
    raise typer.Exit(1)


def _find_config_optional() -> Path | None:
    from watchflow.utils.path_utils import find_config_file

    return find_config_file()


def _pkg_version(name: str) -> str:
    """Return installed version of *name* using importlib.metadata."""
    from importlib.metadata import PackageNotFoundError, version

    # Some packages use different distribution names vs import names
    _dist_map = {
        "yaml": "PyYAML",
        "anyio": "anyio",
        "rich": "rich",
        "watchdog": "watchdog",
        "uvloop": "uvloop",
        "typer": "typer",
        "structlog": "structlog",
        "pydantic": "pydantic",
        "networkx": "networkx",
        "psutil": "psutil",
    }
    dist_name = _dist_map.get(name, name)
    try:
        return version(dist_name)
    except PackageNotFoundError:
        return "unknown"


# ─── Commands ─────────────────────────────────────────────────────────────────


@app.command()
def run(
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Config file path."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="Simulate pipeline execution without running actual shell commands."
        ),
    ] = False,
) -> None:
    """Start the WatchFlow engine with live TUI."""
    import anyio

    from watchflow.engine.reactive_engine import ReactiveEngine

    cfg_path = _find_config(config)
    console.print(
        f"  [dim]Config:[/dim] [cyan]{cfg_path}[/cyan]  [dim]│  Press Ctrl+C to stop[/dim]"
    )

    engine = ReactiveEngine.from_config_file(cfg_path, console=console, dry_run=dry_run)

    async def _main() -> None:
        await engine.start()

    with contextlib.suppress(KeyboardInterrupt):
        anyio.run(_main, backend="asyncio")

    _print_summary(engine.store)


def _print_summary(store: Any) -> None:
    """Print a session summary when the engine stops."""
    from rich.panel import Panel

    summary = store.summary()
    t = Text()
    t.append("✔ ", style="bold green")
    t.append("WatchFlow stopped. ", style="bold white")
    t.append(f"Uptime: {summary['uptime_s']:.0f}s  ", style="dim white")
    t.append(f"Events: {summary['events']}  ", style="dim cyan")
    t.append(f"Pipelines: {summary['pipelines_run']} ", style="dim green")
    if summary["failures"] > 0:
        t.append(f"({summary['failures']} failed) ", style="bold red")

    console.print("\n")
    console.print(Panel(t, border_style="dim blue", expand=False))


@app.command()
def init(
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output file path."),
    ] = None,
) -> None:
    """Interactively generate a [bold]watchflow.yaml[/bold] config."""
    from watchflow.config.loader import generate_example_config

    out = output or Path("watchflow.yaml")
    if out.exists():
        overwrite = typer.confirm(
            f"[yellow]{out}[/yellow] already exists. Overwrite?", default=False
        )
        if not overwrite:
            raise typer.Exit(0)

    project_name = typer.prompt("Project name", default=out.stem)
    watch_path = typer.prompt("Watch path", default="src/")

    content = generate_example_config(project_name=project_name)
    content = content.replace("  - src/\n", f"  - {watch_path}\n", 1)
    out.write_text(content, encoding="utf-8")

    console.print(f"\n  [green]✔[/green]  Created [bold]{out}[/bold]")
    console.print(
        "  Edit the file to customise pipelines, then run [bold cyan]watchflow run[/bold cyan].\n"
    )


@app.command()
def doctor() -> None:
    """Check system requirements and package availability."""
    import shutil

    table = Table(
        title="System Check",
        show_header=True,
        header_style="bold blue",
        border_style="dim blue",
        min_width=60,
    )
    table.add_column("Check", style="white", min_width=22)
    table.add_column("Status", justify="center", min_width=8)
    table.add_column("Detail", style="dim white")

    # Python version
    ver = sys.version_info
    py_ok = ver >= (3, 12)
    table.add_row(
        "Python ≥ 3.12",
        "[green]✔[/green]" if py_ok else "[red]✖[/red]",
        f"{ver.major}.{ver.minor}.{ver.micro}",
    )

    # Required packages (check via importlib so we get real version strings)
    pkg_list = [
        ("typer", "typer"),
        ("rich", "rich"),
        ("watchdog", "watchdog"),
        ("pydantic", "pydantic"),
        ("structlog", "structlog"),
        ("anyio", "anyio"),
        ("networkx", "networkx"),
        ("psutil", "psutil"),
        ("yaml", "PyYAML"),
        ("uvloop", "uvloop"),
    ]
    for import_name, dist_name in pkg_list:
        try:
            __import__(import_name)
            ver_str = _pkg_version(import_name)
            table.add_row(dist_name, "[green]✔[/green]", ver_str)
        except ImportError:
            table.add_row(dist_name, "[red]✖[/red]", "[red]not installed[/red]")

    # External tools
    for tool in ["git", "pytest", "ruff", "mypy"]:
        found = shutil.which(tool)
        table.add_row(
            f"{tool}",
            "[green]✔[/green]" if found else "[yellow]⚠[/yellow]",
            found or "[yellow]not in PATH[/yellow]",
        )

    console.print(table)

    if not py_ok:
        err_console.print(
            "\n[red]✖  Python 3.12+ is required.[/red]  "
            f"You have {ver.major}.{ver.minor}.{ver.micro}."
        )
        raise typer.Exit(1)


@app.command()
def validate(
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Config file to validate."),
    ] = None,
) -> None:
    """Validate a [bold]watchflow.yaml[/bold] config file."""
    from watchflow.config.loader import load_config

    cfg_path = _find_config(config)
    try:
        cfg = load_config(cfg_path)
    except Exception as exc:
        err_console.print(f"\n[red bold]✖  Validation failed[/red bold]\n  {exc}\n")
        raise typer.Exit(1) from exc

    table = Table(
        show_header=False,
        border_style="dim green",
        min_width=50,
    )
    table.add_column("Key", style="dim white", min_width=20)
    table.add_column("Value", style="white")
    table.add_row("Config file", str(cfg_path))
    table.add_row("Watchers", str(len(cfg.watchers)))
    table.add_row("Pipelines", str(len(cfg.pipelines)))
    table.add_row("Intent rules", str(len(cfg.intent_rules)))
    table.add_row("Cooldown", f"{cfg.cooldown_ms} ms")
    table.add_row("Max concurrent", str(cfg.max_concurrent_pipelines))

    console.print("\n  [green bold]✔  Config valid[/green bold]\n")
    console.print(table)
    console.print()


@app.command()
def explain(
    file_path: Annotated[str, typer.Argument(help="File path to analyse intent for.")],
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Config file for user rules."),
    ] = None,
) -> None:
    """Show [bold]IntentDetector[/bold] reasoning for a file path."""
    from watchflow.config.loader import load_config
    from watchflow.core.events import FileSystemEvent, FSEventType
    from watchflow.intelligence.intent_detector import IntentDetector

    cfg = None
    cfg_path: Path | None = config or _find_config_optional()
    if cfg_path:
        try:
            cfg = load_config(cfg_path)
        except Exception:
            cfg = None

    detector = IntentDetector(user_rules=cfg.intent_rules if cfg else None)
    events = [FileSystemEvent(path=file_path, event_type=FSEventType.MODIFIED)]
    result = detector.explain(events)

    console.print(f"\n  [bold]Intent analysis[/bold]  [dim white]{file_path}[/dim white]\n")

    table = Table(
        show_header=True,
        header_style="bold magenta",
        border_style="dim magenta",
        min_width=70,
    )
    table.add_column("Rule", style="white", min_width=18)
    table.add_column("Pipeline", style="cyan")
    table.add_column("Confidence", justify="right", min_width=10)
    table.add_column("Threshold", justify="right", min_width=10)
    table.add_column("Match", justify="center", min_width=6)

    for r in result["reasoning"]:
        match_style = "bold green" if r["above_threshold"] else "dim red"
        check = "✔" if r["above_threshold"] else "✖"
        conf_style = "green" if r["above_threshold"] else "red"
        table.add_row(
            r["rule"],
            r["pipeline"],
            Text(f"{r['confidence']:.1%}", style=conf_style),
            f"{r['threshold']:.1%}",
            Text(check, style=match_style),
        )

    console.print(table)

    top = result["top_intent"]
    if top:
        console.print(f"\n  [green bold]Top intent:[/green bold]  [bold cyan]{top}[/bold cyan]\n")
    else:
        console.print("\n  [yellow]No intent detected above any threshold.[/yellow]\n")


@app.command()
def graph(
    pipeline_name: Annotated[str, typer.Argument(help="Pipeline name to visualize.")],
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Config file path."),
    ] = None,
) -> None:
    """Print an ASCII DAG visualization of a pipeline."""
    from watchflow.config.loader import load_config
    from watchflow.execution.dag_engine import DAGEngine

    cfg_path = _find_config(config)
    cfg = load_config(cfg_path)
    pipeline = next((p for p in cfg.pipelines if p.name == pipeline_name), None)
    if pipeline is None:
        err_console.print(
            f"\n[red bold]✖  Pipeline not found:[/red bold]  [white]{pipeline_name}[/white]"
        )
        available = ", ".join(f"[cyan]{p.name}[/cyan]" for p in cfg.pipelines)
        err_console.print(f"  Available: {available or '[dim]none[/dim]'}\n")
        raise typer.Exit(1)

    engine = DAGEngine()
    art = engine.visualize(pipeline)

    console.print()
    console.print(
        Panel(
            art,
            title=f"[bold green]DAG:[/bold green] [bold cyan]{pipeline_name}[/bold cyan]",
            border_style="dim cyan",
            padding=(1, 2),
        )
    )


@app.command()
def plugins(
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Config file path."),
    ] = None,
) -> None:
    """List all registered hook plugin registrations."""
    from watchflow.hooks.plugin_system import HookRegistry
    from watchflow.plugins.builtin import register_builtin_plugins

    registry = HookRegistry()
    register_builtin_plugins(registry)
    regs = registry.list_registrations()

    table = Table(
        title="Plugin Registrations",
        show_header=True,
        header_style="bold cyan",
        border_style="dim cyan",
        min_width=65,
    )
    table.add_column("Hook Point", style="cyan", min_width=18)
    table.add_column("Plugin", style="white", min_width=16)
    table.add_column("Priority", justify="right", min_width=9)
    table.add_column("Callback", style="dim white")

    for r in regs:
        table.add_row(r["hook"], r["plugin"], str(r["priority"]), r["callback"])

    console.print(table)
    console.print(
        f"\n  [dim]{len(regs)} registration(s) across {len({r['plugin'] for r in regs})} plugin(s)[/dim]\n"
    )


@app.command()
def info() -> None:
    """Show platform details and all installed package versions."""
    import platform

    import watchflow

    table = Table(
        title="WatchFlow Environment",
        show_header=False,
        border_style="dim blue",
        min_width=60,
    )
    table.add_column("Item", style="dim white", min_width=22)
    table.add_column("Value", style="white")

    table.add_row("WatchFlow version", f"[bold cyan]{watchflow.__version__}[/bold cyan]")
    table.add_row(
        "Python version",
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    )
    table.add_row("Platform", platform.system())
    table.add_row("OS release", platform.release())
    table.add_row("Architecture", platform.machine())
    table.add_row("Python executable", sys.executable)

    pkg_list = [
        "typer",
        "rich",
        "watchdog",
        "pydantic",
        "structlog",
        "anyio",
        "networkx",
        "psutil",
        "yaml",
        "uvloop",
    ]
    for pkg in pkg_list:
        try:
            __import__(pkg)
            ver = _pkg_version(pkg)
            table.add_row(pkg, ver)
        except ImportError:
            table.add_row(pkg, "[red]not installed[/red]")

    console.print(table)
    console.print()


@app.command()
def status(
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Config file path."),
    ] = None,
) -> None:
    """Show config summary and intent rule overview (no engine required)."""
    from watchflow.config.loader import load_config

    cfg_path = _find_config(config)
    try:
        cfg = load_config(cfg_path)
    except Exception as exc:
        err_console.print(f"\n[red bold]✖  Config error:[/red bold]  {exc}\n")
        raise typer.Exit(1) from exc

    # Config summary
    summary = Table(
        title="Config Summary",
        show_header=False,
        border_style="dim blue",
        min_width=55,
    )
    summary.add_column("Key", style="dim white", min_width=22)
    summary.add_column("Value", style="white")
    summary.add_row("Config file", str(cfg_path))
    summary.add_row("Cooldown", f"{cfg.cooldown_ms} ms")
    summary.add_row("Max concurrent pipelines", str(cfg.max_concurrent_pipelines))
    summary.add_row("Watchers", str(len(cfg.watchers)))
    summary.add_row("Pipelines", str(len(cfg.pipelines)))
    summary.add_row("Intent rules", str(len(cfg.intent_rules)))
    console.print(summary)

    # Watcher table
    if cfg.watchers:
        console.print()
        wt = Table(
            title="Watchers",
            show_header=True,
            header_style="bold cyan",
            border_style="dim cyan",
        )
        wt.add_column("Name", style="cyan")
        wt.add_column("Paths", style="white")
        wt.add_column("Patterns", style="dim white")
        wt.add_column("Debounce", justify="right")
        for w in cfg.watchers:
            wt.add_row(
                w.name,
                ", ".join(w.paths),
                ", ".join(w.patterns),
                f"{w.debounce_ms} ms",
            )
        console.print(wt)

    # Pipeline table
    if cfg.pipelines:
        console.print()
        pt = Table(
            title="Pipelines",
            show_header=True,
            header_style="bold green",
            border_style="dim green",
        )
        pt.add_column("Name", style="green")
        pt.add_column("Steps", justify="right")
        pt.add_column("Timeout", justify="right")
        pt.add_column("Fail-fast", justify="center")
        for p in cfg.pipelines:
            pt.add_row(
                p.name,
                str(len(p.commands)),
                f"{p.total_timeout}s",
                "[green]✔[/green]" if p.fail_fast else "[dim]✖[/dim]",
            )
        console.print(pt)

    # Intent rules table
    if cfg.intent_rules:
        console.print()
        it = Table(
            title="Intent Rules",
            show_header=True,
            header_style="bold magenta",
            border_style="dim magenta",
        )
        it.add_column("Rule", style="magenta")
        it.add_column("Pipeline", style="cyan")
        it.add_column("Threshold", justify="right")
        it.add_column("Patterns", style="dim white")
        for r in cfg.intent_rules:
            it.add_row(
                r.name,
                r.pipeline,
                f"{r.confidence_threshold:.0%}",
                ", ".join(r.patterns[:4]) + ("…" if len(r.patterns) > 4 else ""),
            )
        console.print(it)

    console.print()


@app.command()
def wal(
    limit: int = typer.Option(50, "--limit", "-l", help="Number of recent events to show."),
    clear: bool = typer.Option(False, "--clear", is_flag=True, help="Clear the WAL database."),
) -> None:
    """[bold magenta]TIME TRAVEL[/bold magenta]: Replay historical WatchFlow events from the WAL."""
    from rich.panel import Panel
    from rich.table import Table

    from watchflow.core.wal import WriteAheadLog

    wal = WriteAheadLog()
    try:
        if clear:
            wal.clear()
            console.print("[bold green]✔[/bold green] Write-Ahead Log cleared.")
            return

        events = wal.read_all()
        if not events:
            console.print(
                Panel("WAL is empty. No historical events found.", border_style="dim yellow")
            )
            return

        events = events[-limit:]

        table = Table(
            title="Time-Travel Event Replay (WAL)",
            show_header=True,
            header_style="bold cyan",
            border_style="dim blue",
        )
        table.add_column("Time", style="dim white")
        table.add_column("Type", style="bold magenta")
        table.add_column("Details", style="white")

        import datetime

        for ev in events:
            dt = datetime.datetime.fromtimestamp(ev["timestamp"]).strftime("%H:%M:%S.%f")[:-3]
            typ = ev["event_type"]
            payload = ev["payload"]

            if typ == "fs":
                detail = f"[cyan]{payload.get('event_type')}[/cyan] {payload.get('path')}"
            elif typ == "intent":
                detail = f"[magenta]{payload.get('intent_name')}[/magenta] [dim]({payload.get('confidence'):.0%})[/dim] → {payload.get('pipeline_name')}"
            elif typ == "pipeline":
                success = (
                    payload.get("event_type") == "COMPLETED"
                    or payload.get("event_type") == "STEP_COMPLETED"
                )
                color = "green" if success else "red"
                detail = f"[{color}]{payload.get('event_type')}[/{color}] {payload.get('pipeline_name')} {payload.get('step_name') or ''}"
            else:
                detail = str(payload)

            table.add_row(dt, typ.upper(), detail)

        console.print(table)
    finally:
        wal.close()


@app.command()
def analytics(
    limit: int = typer.Option(20, "--limit", "-l", help="Number of recent pipelines to show."),
) -> None:
    """[bold blue]METRICS[/bold blue]: View cross-session historical pipeline analytics."""
    import sqlite3
    from pathlib import Path

    from rich.panel import Panel
    from rich.table import Table

    db_path = Path.home() / ".watchflow" / "metrics.db"
    if not db_path.exists():
        console.print(
            Panel("No analytics data found. Run pipelines first.", border_style="dim yellow")
        )
        return

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Pipeline metrics
        cursor = conn.cursor()
        cursor.execute(
            "SELECT pipeline_name, success, duration_ms, timestamp FROM pipeline_metrics ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        rows = cursor.fetchall()

        if not rows:
            console.print(Panel("No pipeline executions recorded.", border_style="dim yellow"))
            return

        table = Table(
            title="Recent Pipeline Executions (Cross-Session)",
            show_header=True,
            header_style="bold blue",
            border_style="dim cyan",
        )
        table.add_column("Time", style="dim white")
        table.add_column("Pipeline", style="cyan")
        table.add_column("Result", justify="center")
        table.add_column("Duration", justify="right")

        import datetime

        for row in rows:
            dt = datetime.datetime.fromtimestamp(row["timestamp"]).strftime("%m/%d %H:%M:%S")
            success = "✔" if row["success"] else "✖"
            color = "green" if row["success"] else "red"
            duration = f"{row['duration_ms']:.1f}ms"
            table.add_row(dt, row["pipeline_name"], f"[{color}]{success}[/{color}]", duration)

        console.print()
        console.print(table)

        # Aggregate stats
        cursor.execute("SELECT COUNT(*) as total, SUM(success) as ok FROM pipeline_metrics")
        stats = cursor.fetchone()
        if stats and stats["total"] > 0:
            total = stats["total"]
            ok = stats["ok"] or 0
            fail = total - ok
            rate = ok / total

            summary = Table(
                title="Global Lifetime Stats", show_header=False, border_style="dim blue"
            )
            summary.add_column("Metric", style="white")
            summary.add_column("Value", style="bold cyan", justify="right")
            summary.add_row("Total Executions", str(total))
            summary.add_row("Successes", f"[green]{ok}[/green]")
            summary.add_row("Failures", f"[red]{fail}[/red]")
            summary.add_row("Global Reliability", f"{rate:.1%}")
            console.print()
            console.print(summary)

    finally:
        conn.close()


def _global_exception_handler(
    exc_type: type[BaseException], exc_value: BaseException, exc_traceback: Any
) -> None:
    if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    import os

    from rich.panel import Panel

    if os.environ.get("WATCHFLOW_DEBUG") == "1":
        from rich.traceback import Traceback

        err_console.print(Traceback.from_exception(exc_type, exc_value, exc_traceback))
    else:
        err_console.print(
            Panel(
                f"[red]{str(exc_value)}[/red]\n\n[dim]Run with --debug or WATCHFLOW_DEBUG=1 for full traceback.[/dim]",
                title=f"[bold red]WatchFlow Error: {exc_type.__name__}[/bold red]",
                border_style="red",
            )
        )
    sys.exit(1)


sys.excepthook = _global_exception_handler

if __name__ == "__main__":
    app()
