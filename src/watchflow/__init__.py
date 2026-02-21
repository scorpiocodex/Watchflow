"""WatchFlow — Reactive automation CLI platform with semantic intent engine."""

from __future__ import annotations

import sys
import warnings

__version__ = "0.1.0"
__author__ = "ScorpioCodeX"

# Install uvloop on Linux/macOS for performance.
# Suppress DeprecationWarning from uvloop.install() on Python 3.12+.
if sys.platform != "win32":
    try:
        import uvloop  # type: ignore[import]

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            uvloop.install()
    except ImportError:
        pass


class WatchFlowError(Exception):
    """Base exception for all WatchFlow errors."""


class ConfigError(WatchFlowError):
    """Configuration validation or loading error."""


class ExecutionError(WatchFlowError):
    """Pipeline execution error."""


class InvalidTransitionError(WatchFlowError):
    """State machine invalid transition attempt."""


class PluginError(WatchFlowError):
    """Hook/plugin system error."""


def configure_logging(debug: bool = False) -> None:
    """Configure structlog for CLI or engine usage.

    In non-debug mode, only WARNING and above are emitted to stderr.
    In debug mode, all levels are emitted with timestamps and colors.
    """
    import logging

    import structlog

    level = logging.DEBUG if debug else logging.WARNING

    logging.basicConfig(
        format="%(message)s",
        level=level,
        stream=sys.stderr,
        force=True,
    )

    if debug:
        processors: list[structlog.types.Processor] = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="%H:%M:%S"),
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        processors = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.dev.ConsoleRenderer(colors=False),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )
