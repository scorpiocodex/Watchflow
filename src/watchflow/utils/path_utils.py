"""Path resolution utilities."""

from __future__ import annotations

from pathlib import Path

_CONFIG_NAMES = [
    "watchflow.yaml",
    "watchflow.yml",
    ".watchflow.yaml",
    ".watchflow.yml",
]


def find_config_file(start: Path | None = None) -> Path | None:
    """Walk up from *start* (default: cwd) searching for a WatchFlow config file."""
    current = (start or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        for name in _CONFIG_NAMES:
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


def resolve_paths(paths: list[str], base: Path | None = None) -> list[Path]:
    """Resolve each path string relative to *base* (default: cwd)."""
    base = (base or Path.cwd()).resolve()
    resolved: list[Path] = []
    for p in paths:
        candidate = Path(p)
        if not candidate.is_absolute():
            candidate = base / candidate
        resolved.append(candidate.resolve())
    return resolved
