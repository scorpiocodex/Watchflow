"""General utility helpers: template substitution, hashing, backoff, ignore checking."""

from __future__ import annotations

import fnmatch
import hashlib
import math
import re
import time
from pathlib import Path
from typing import Any

from watchflow.config.schema import RetryStrategy


def substitute_template(template: str, context: dict[str, Any]) -> str:
    """Replace ``{key}`` placeholders in *template* with values from *context*.

    Unknown keys are left as-is (no KeyError raised).
    """

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        return str(context.get(key, match.group(0)))

    return re.sub(r"\{(\w+)\}", _replace, template)


def split_command(cmd: str) -> list[str]:
    """Split a command string into list of arguments using shlex (respects quotes)."""
    import shlex

    return shlex.split(cmd)


def hash_file(path: Path, chunk_size: int = 65536) -> str | None:
    """Return the SHA-256 hex digest of *path*, or ``None`` if unreadable."""
    h = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            while chunk := fh.read(chunk_size):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def calculate_backoff(
    attempt: int,
    strategy: RetryStrategy,
    base_ms: float = 1000.0,
    max_ms: float = 30000.0,
) -> float:
    """Return sleep duration in *seconds* for a retry *attempt* (0-indexed).

    - IMMEDIATE: always 0
    - LINEAR: base_ms * (attempt + 1), capped at max_ms
    - EXPONENTIAL: base_ms * 2^attempt, capped at max_ms
    """
    if strategy == RetryStrategy.IMMEDIATE:
        return 0.0
    if strategy == RetryStrategy.LINEAR:
        ms = base_ms * (attempt + 1)
    else:  # EXPONENTIAL
        ms = base_ms * math.pow(2, attempt)
    return min(ms, max_ms) / 1000.0


def matches_ignore_pattern(path: str, patterns: list[str]) -> bool:
    """Return True if *path* matches any of the fnmatch *patterns*."""
    name = Path(path).name
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(name, pattern):
            return True
    return False


def current_ms() -> int:
    """Return current time in milliseconds."""
    return int(time.monotonic() * 1000)
