"""Pydantic v2 configuration models for WatchFlow."""

from __future__ import annotations

from enum import StrEnum

import networkx as nx
from pydantic import BaseModel, ConfigDict, Field, model_validator


class RetryStrategy(StrEnum):
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    IMMEDIATE = "immediate"


class CommandConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    cmd: str
    timeout: float = Field(default=30.0, gt=0)
    retry: int = Field(default=0, ge=0, le=10)
    retry_strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    env: dict[str, str] = Field(default_factory=dict)
    cwd: str | None = None
    depends_on: list[str] = Field(default_factory=list)


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    commands: list[CommandConfig]
    fail_fast: bool = True
    total_timeout: float = Field(default=300.0, gt=0)

    @model_validator(mode="after")
    def _check_no_cycles(self) -> PipelineConfig:
        names = {cmd.name for cmd in self.commands}
        g: nx.DiGraph = nx.DiGraph()
        for cmd in self.commands:
            g.add_node(cmd.name)
            for dep in cmd.depends_on:
                if dep not in names:
                    raise ValueError(
                        f"Command '{cmd.name}' depends_on unknown command '{dep}'"
                    )
                g.add_edge(dep, cmd.name)
        if not nx.is_directed_acyclic_graph(g):
            raise ValueError(
                f"Pipeline '{self.name}' contains a dependency cycle"
            )
        return self


class WatcherConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    paths: list[str]
    patterns: list[str] = Field(default_factory=lambda: ["*"])
    ignore: list[str] = Field(default_factory=list)
    debounce_ms: int = Field(default=500, ge=50, le=30000)
    recursive: bool = True
    hash_check: bool = False


class IntentRuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    patterns: list[str]
    pipeline: str
    confidence_threshold: float = Field(default=0.6, ge=0.0, le=1.0)


class GlobalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    watchers: list[WatcherConfig] = Field(default_factory=list)
    pipelines: list[PipelineConfig] = Field(default_factory=list)
    intent_rules: list[IntentRuleConfig] = Field(default_factory=list)
    cooldown_ms: int = Field(default=1000, ge=0)
    max_concurrent_pipelines: int = Field(default=4, ge=1)

    @model_validator(mode="after")
    def _check_pipeline_refs(self) -> GlobalConfig:
        pipeline_names = {p.name for p in self.pipelines}
        for rule in self.intent_rules:
            if rule.pipeline not in pipeline_names:
                raise ValueError(
                    f"IntentRule '{rule.name}' references unknown pipeline '{rule.pipeline}'"
                )
        return self
