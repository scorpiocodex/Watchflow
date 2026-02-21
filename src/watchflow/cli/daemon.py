"""Daemon control commands for WatchFlow."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(help="Manage the background Nexus Daemon for WatchFlow.")
console = Console()

def get_pid_file() -> Path:
    pid_dir = Path.home() / ".watchflow"
    pid_dir.mkdir(parents=True, exist_ok=True)
    return pid_dir / "daemon.pid"

@app.command()
def start(
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Config file path."),
    ] = None,
) -> None:
    """Start the WatchFlow daemon in the background."""
    pid_file = get_pid_file()
    if pid_file.exists():
        console.print("[yellow]Daemon might already be running. Check status.[/yellow]")
        return

    config_arg = ["--config", str(config)] if config else []
    # We invoke the module natively
    cmd = [sys.executable, "-m", "watchflow", "run"] + config_arg
    
    env = os.environ.copy()
    env["WATCHFLOW_DAEMON"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    
    log_file = open(pid_file.parent / "daemon.log", "a", encoding="utf-8")  # noqa: SIM115
    
    if sys.platform == "win32":
        proc = subprocess.Popen(
            cmd,
            creationflags=subprocess.DETACHED_PROCESS | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 512),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
        )
    else:
        proc = subprocess.Popen(
            cmd,
            start_new_session=True,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
        )

    pid_file.write_text(str(proc.pid))
    console.print(Panel.fit(f"[green]Daemon started with PID {proc.pid}[/green]", title="WatchFlow Daemon"))

@app.command()
def stop() -> None:
    """Stop the running WatchFlow daemon."""
    pid_file = get_pid_file()
    if not pid_file.exists():
        console.print("[yellow]No daemon PID file found. Is it running?[/yellow]")
        return
        
    try:
        pid = int(pid_file.read_text().strip())
        import psutil
        try:
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True):
                child.terminate()
            parent.terminate()
            parent.wait(5)
            console.print(f"[green]Sent terminate signal to PID {pid} and its children.[/green]")
        except psutil.NoSuchProcess:
            console.print(f"[yellow]Process {pid} not found. Deleting stale PID file.[/yellow]")
            
    except Exception as e:
        console.print(f"[red]Error stopping daemon: {e}[/red]")
    finally:
        pid_file.unlink(missing_ok=True)

@app.command()
def status() -> None:
    """Check the status of the WatchFlow daemon."""
    pid_file = get_pid_file()
    if not pid_file.exists():
        console.print("[dim]Daemon is not running.[/dim]")
        return
        
    try:
        pid = int(pid_file.read_text().strip())
        import psutil
        if psutil.pid_exists(pid):
            proc = psutil.Process(pid)
            if proc.status() != psutil.STATUS_ZOMBIE:
                console.print(f"[green]Daemon is running (PID: {pid}).[/green]")
            else:
                 console.print(f"[yellow]Daemon PID {pid} is a zombie process.[/yellow]")   
        else:
            console.print("[yellow]Daemon PID exists but process is dead.[/yellow]")
            pid_file.unlink(missing_ok=True)
    except Exception as e:
        console.print(f"[red]Status check failed: {e}[/red]")
