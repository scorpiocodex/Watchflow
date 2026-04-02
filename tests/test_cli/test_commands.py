"""Tests for CLI commands using Typer's test runner."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from watchflow.cli.main import app

runner = CliRunner()

_MINIMAL_CONFIG = """\
pipelines:
  - name: run_tests
    commands:
      - name: test
        cmd: echo test
intent_rules:
  - name: run_tests
    patterns: ["*.py"]
    pipeline: run_tests
"""


# ─── info ─────────────────────────────────────────────────────────────────────


def test_info_command() -> None:
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    assert "WatchFlow" in result.output
    assert "Python" in result.output


def test_info_shows_versions() -> None:
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    # Should show real version strings (not "unknown") for core packages
    assert "typer" in result.output.lower()
    assert "pydantic" in result.output.lower()


# ─── --version ────────────────────────────────────────────────────────────────


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "WatchFlow" in result.output
    # Should contain a semver-like string
    assert "0." in result.output or "1." in result.output


def test_version_short_flag() -> None:
    result = runner.invoke(app, ["-V"])
    assert result.exit_code == 0
    assert "WatchFlow" in result.output


# ─── doctor ───────────────────────────────────────────────────────────────────


def test_doctor_command() -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Python" in result.output


def test_doctor_shows_packages() -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "pydantic" in result.output.lower()
    assert "rich" in result.output.lower()


# ─── validate ─────────────────────────────────────────────────────────────────


def test_validate_command_valid(tmp_path: Path) -> None:
    config = tmp_path / "watchflow.yaml"
    config.write_text(_MINIMAL_CONFIG)
    result = runner.invoke(app, ["validate", "--config", str(config)])
    assert result.exit_code == 0
    assert "valid" in result.output.lower()


def test_validate_command_shows_summary(tmp_path: Path) -> None:
    config = tmp_path / "watchflow.yaml"
    config.write_text(_MINIMAL_CONFIG)
    result = runner.invoke(app, ["validate", "--config", str(config)])
    assert result.exit_code == 0
    assert "Pipeline" in result.output or "pipeline" in result.output


def test_validate_command_invalid(tmp_path: Path) -> None:
    config = tmp_path / "watchflow.yaml"
    config.write_text("invalid: yaml: content: [broken")
    result = runner.invoke(app, ["validate", "--config", str(config)])
    assert result.exit_code != 0


def test_validate_missing_config(tmp_path: Path) -> None:
    result = runner.invoke(app, ["validate", "--config", str(tmp_path / "missing.yaml")])
    assert result.exit_code != 0


# ─── explain ──────────────────────────────────────────────────────────────────


def test_explain_command() -> None:
    result = runner.invoke(app, ["explain", "src/test_api.py"])
    assert result.exit_code == 0
    assert "Intent analysis" in result.output


def test_explain_python_file_detects_intent() -> None:
    result = runner.invoke(app, ["explain", "src/main.py"])
    assert result.exit_code == 0
    # Python files should trigger at least one matching rule
    assert "✔" in result.output


def test_explain_requirements_file() -> None:
    result = runner.invoke(app, ["explain", "requirements.txt"])
    assert result.exit_code == 0
    assert "install_deps" in result.output


def test_explain_dockerfile() -> None:
    result = runner.invoke(app, ["explain", "Dockerfile"])
    assert result.exit_code == 0
    assert "docker_build" in result.output


def test_explain_unmatched_file() -> None:
    result = runner.invoke(app, ["explain", "totally_unknown.xyz"])
    assert result.exit_code == 0
    assert "No intent" in result.output


# ─── graph ────────────────────────────────────────────────────────────────────


def test_graph_command(tmp_path: Path) -> None:
    config = tmp_path / "watchflow.yaml"
    config.write_text(
        """\
pipelines:
  - name: build
    commands:
      - name: compile
        cmd: echo compile
      - name: link
        cmd: echo link
        depends_on: [compile]
"""
    )
    result = runner.invoke(app, ["graph", "build", "--config", str(config)])
    assert result.exit_code == 0
    assert "compile" in result.output
    assert "link" in result.output


def test_graph_missing_pipeline(tmp_path: Path) -> None:
    config = tmp_path / "watchflow.yaml"
    config.write_text(_MINIMAL_CONFIG)
    result = runner.invoke(app, ["graph", "nonexistent", "--config", str(config)])
    assert result.exit_code != 0


# ─── plugins ──────────────────────────────────────────────────────────────────


def test_plugins_command() -> None:
    result = runner.invoke(app, ["plugins"])
    assert result.exit_code == 0
    assert "notification" in result.output.lower()


def test_plugins_shows_all_builtins() -> None:
    result = runner.invoke(app, ["plugins"])
    assert result.exit_code == 0
    assert "repeat_failure" in result.output.lower()
    assert "after_pipeline" in result.output.lower()
    assert "on_failure" in result.output.lower()


def test_plugins_shows_registration_count() -> None:
    result = runner.invoke(app, ["plugins"])
    assert result.exit_code == 0
    # Should mention registration count
    assert "registration" in result.output.lower()


# ─── status ───────────────────────────────────────────────────────────────────


def test_status_command(tmp_path: Path) -> None:
    config = tmp_path / "watchflow.yaml"
    config.write_text(_MINIMAL_CONFIG)
    result = runner.invoke(app, ["status", "--config", str(config)])
    assert result.exit_code == 0
    assert "run_tests" in result.output


def test_status_shows_watchers(tmp_path: Path) -> None:
    config = tmp_path / "watchflow.yaml"
    config.write_text(
        """\
watchers:
  - name: src_watcher
    paths: ["."]
    patterns: ["*.py"]
pipelines:
  - name: test
    commands:
      - name: t
        cmd: echo t
intent_rules:
  - name: test
    patterns: ["*.py"]
    pipeline: test
"""
    )
    result = runner.invoke(app, ["status", "--config", str(config)])
    assert result.exit_code == 0
    assert "src_watcher" in result.output


def test_status_missing_config(tmp_path: Path) -> None:
    result = runner.invoke(app, ["status", "--config", str(tmp_path / "missing.yaml")])
    assert result.exit_code != 0


# ─── init ─────────────────────────────────────────────────────────────────────


def test_init_creates_config(tmp_path: Path) -> None:
    out = tmp_path / "watchflow.yaml"
    result = runner.invoke(
        app,
        ["init", "--output", str(out)],
        input="my-project\nsrc/\n",
    )
    assert result.exit_code == 0
    assert out.exists()
    content = out.read_text()
    assert "my-project" in content
    assert "watchflow" in content.lower()


def test_init_includes_project_name(tmp_path: Path) -> None:
    out = tmp_path / "watchflow.yaml"
    runner.invoke(
        app,
        ["init", "--output", str(out)],
        input="awesome-project\nsrc/\n",
    )
    content = out.read_text()
    assert "awesome-project" in content


def test_init_no_overwrite_by_default(tmp_path: Path) -> None:
    out = tmp_path / "watchflow.yaml"
    out.write_text("existing: content\n")
    # Respond 'n' to the overwrite prompt
    runner.invoke(
        app,
        ["init", "--output", str(out)],
        input="n\n",
    )
    # File should still have original content
    assert "existing" in out.read_text()
