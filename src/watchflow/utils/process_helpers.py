"""Async process management utilities."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


def substitute_args(cmd: list[str], ctx: dict[str, str]) -> list[str]:
    """Substitute {key} placeholders in command args with context values."""
    return [
        str(ctx.get(part.strip("{}"), part))
        if part.startswith("{") and part.endswith("}")
        else part
        for part in cmd
    ]


@dataclass
class ProcessResult:
    """Result of a subprocess execution."""

    returncode: int
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool = False

    @property
    def success(self) -> bool:
        return self.returncode == 0 and not self.timed_out


class ProcessManager:
    """Track and manage spawned subprocesses; kill all on shutdown."""

    def __init__(self) -> None:
        self._processes: dict[int, asyncio.subprocess.Process] = {}

    async def run(
        self,
        cmd: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> ProcessResult:
        """Run *cmd* (as list) without shell; return a :class:`ProcessResult`."""
        merged_env: dict[str, str] = {**os.environ}
        if env:
            merged_env.update(env)

        start = time.monotonic()

        if sys.platform == "win32":
            cmd = ["cmd", "/c", *cmd]
        else:
            cmd = list(cmd)

        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

        preexec_fn: Callable[[], int] | None = None
        if sys.platform != "win32":
            preexec_fn = os.setsid

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=merged_env,
            creationflags=creation_flags,
            preexec_fn=preexec_fn,
        )
        if proc.pid is not None:
            self._processes[proc.pid] = proc

        timed_out = False
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            timed_out = True
            with contextlib.suppress(ProcessLookupError, OSError):
                if sys.platform == "win32":
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                await asyncio.wait_for(proc.wait(), timeout=1.0)
            except (TimeoutError, ProcessLookupError):
                with contextlib.suppress(ProcessLookupError, OSError):
                    if sys.platform == "win32":
                        proc.kill()
                    else:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            stdout_b, stderr_b = b"", b""
        finally:
            self._processes.pop(proc.pid or -1, None)

        duration_ms = (time.monotonic() - start) * 1000
        return ProcessResult(
            returncode=proc.returncode or 0,
            stdout=stdout_b.decode(errors="replace"),
            stderr=stderr_b.decode(errors="replace"),
            duration_ms=duration_ms,
            timed_out=timed_out,
        )

    def kill_all(self) -> None:
        """Kill all tracked subprocesses (sync, for shutdown)."""
        for pid, _proc in list(self._processes.items()):
            with contextlib.suppress(ProcessLookupError, OSError):
                if sys.platform == "win32":
                    os.kill(pid, signal.SIGTERM)
                else:
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
        self._processes.clear()
