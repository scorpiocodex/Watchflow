"""Async process management utilities."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from dataclasses import dataclass
from pathlib import Path


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
        cmd: str,
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> ProcessResult:
        """Run *cmd* in a shell; return a :class:`ProcessResult`."""
        import time

        merged_env: dict[str, str] = {**os.environ}
        if env:
            merged_env.update(env)

        start = time.monotonic()
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=merged_env,
        )
        if proc.pid is not None:
            self._processes[proc.pid] = proc

        timed_out = False
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            timed_out = True
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            stdout_b, stderr_b = await proc.communicate()
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
                os.kill(pid, signal.SIGTERM)
        self._processes.clear()
