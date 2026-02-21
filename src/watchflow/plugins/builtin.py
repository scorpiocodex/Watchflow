"""Built-in WatchFlow plugins."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import structlog

from watchflow.hooks.plugin_system import HookPoint, HookRegistry

log: structlog.BoundLogger = structlog.get_logger(__name__)


class NotificationPlugin:
    """Emit structured log notifications on pipeline events."""

    name = "notification"

    def __init__(self, registry: HookRegistry) -> None:
        registry.register(
            HookPoint.AFTER_PIPELINE,
            self.on_after_pipeline,
            priority=200,
            plugin_name=self.name,
        )
        registry.register(
            HookPoint.ON_FAILURE,
            self.on_failure,
            priority=200,
            plugin_name=self.name,
        )

    def on_after_pipeline(self, pipeline_name: str = "", success: bool = True, **kwargs: Any) -> None:
        if success:
            log.info("plugin.notification.success", pipeline=pipeline_name)
        else:
            log.warning("plugin.notification.failure", pipeline=pipeline_name)

    def on_failure(self, pipeline_name: str = "", error: str = "", **kwargs: Any) -> None:
        log.error("plugin.notification.error", pipeline=pipeline_name, error=error)


class RepeatFailurePlugin:
    """Track pipelines that fail repeatedly and fire the on_repeat_failure hook."""

    name = "repeat_failure"
    _THRESHOLD = 3

    def __init__(self, registry: HookRegistry) -> None:
        self._registry = registry
        self._failure_counts: dict[str, int] = defaultdict(int)
        registry.register(
            HookPoint.ON_FAILURE,
            self.on_failure,
            priority=100,
            plugin_name=self.name,
        )

    def on_failure(self, pipeline_name: str = "", **kwargs: Any) -> None:
        self._failure_counts[pipeline_name] += 1
        count = self._failure_counts[pipeline_name]
        if count >= self._THRESHOLD:
            log.warning(
                "plugin.repeat_failure.triggered",
                pipeline=pipeline_name,
                count=count,
            )
            # Fire on_repeat_failure asynchronously — schedule on the event loop
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self._registry.fire(
                        HookPoint.ON_REPEAT_FAILURE,
                        pipeline_name=pipeline_name,
                        failure_count=count,
                    )
                )
            except RuntimeError:
                pass  # No running loop; skip

    def reset(self, pipeline_name: str) -> None:
        self._failure_counts.pop(pipeline_name, None)


def register_builtin_plugins(registry: HookRegistry) -> None:
    """Instantiate and register all built-in plugins."""
    NotificationPlugin(registry)
    RepeatFailurePlugin(registry)
    log.info("plugins.builtins_registered")
