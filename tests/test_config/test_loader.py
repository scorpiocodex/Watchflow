"""Tests for config loading, validation, and template generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from watchflow import ConfigError
from watchflow.config.loader import generate_example_config, load_config, validate_config


class TestGenerateExampleConfig:
    def test_default_project_name(self) -> None:
        content = generate_example_config()
        assert "my-project" in content

    def test_custom_project_name(self) -> None:
        content = generate_example_config(project_name="awesome-svc")
        assert "awesome-svc" in content

    def test_contains_required_keys(self) -> None:
        content = generate_example_config()
        assert "watchers:" in content
        assert "pipelines:" in content
        assert "intent_rules:" in content
        assert "cooldown_ms:" in content

    def test_is_valid_yaml(self) -> None:
        import yaml

        content = generate_example_config()
        parsed = yaml.safe_load(content)
        assert isinstance(parsed, dict)

    def test_generated_config_passes_validation(self) -> None:
        import yaml

        content = generate_example_config()
        data = yaml.safe_load(content)
        cfg = validate_config(data)
        assert len(cfg.pipelines) >= 1
        assert len(cfg.intent_rules) >= 1


class TestLoadConfig:
    def test_load_valid_file(self, tmp_path: Path) -> None:
        f = tmp_path / "wf.yaml"
        f.write_text(
            """\
pipelines:
  - name: test
    commands:
      - name: t
        cmd: echo t
"""
        )
        cfg = load_config(f)
        assert cfg.pipelines[0].name == "test"

    def test_missing_file_raises_config_error(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="Cannot read"):
            load_config(tmp_path / "nonexistent.yaml")

    def test_broken_yaml_raises_config_error(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.yaml"
        f.write_text("key: [unclosed")
        with pytest.raises(ConfigError):
            load_config(f)

    def test_empty_yaml_is_valid(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.yaml"
        f.write_text("")
        cfg = load_config(f)
        assert cfg.pipelines == []

    def test_invalid_pipeline_ref_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.yaml"
        f.write_text(
            """\
pipelines:
  - name: real
    commands:
      - name: x
        cmd: echo
intent_rules:
  - name: r
    patterns: ["*.py"]
    pipeline: does_not_exist
"""
        )
        with pytest.raises(ConfigError):
            load_config(f)


class TestValidateConfig:
    def test_valid_empty_dict(self) -> None:
        cfg = validate_config({})
        assert cfg.cooldown_ms == 1000

    def test_invalid_raises_config_error(self) -> None:
        with pytest.raises(ConfigError, match="validation failed"):
            validate_config({"cooldown_ms": "not-a-number"})
