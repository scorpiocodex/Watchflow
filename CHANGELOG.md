# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - Launch Candidate 
*Developed by ScorpioCodeX*

### Added
- **Global `__main__.py`**: Watchflow can now be dynamically executed as a module (`python -m watchflow`).
- **Daemon Orchestrator**: Added `watchflow daemon start | stop | status` commands for detached execution. Completely runs pipelines silently in the background tracking PID states.
- **`--dry-run` sandbox phase**: Implemented the dry-run parameter to securely validate intent rules natively without invoking subprocess logic.
- **Rich Central Exception Interceptors**: Typer commands will elegantly print actionable error boxes masking raw Python tracebacks unless `--debug` is explicitly parsed.

### Changed
- **CLI Aesthetic Overhaul**: Complete refactor of the terminal header, Typer Help logic, and overall terminal UI/UX into a professional, sleek, Sci-Fi Nexus UI.
- **Dependencies**: Integrated seamless UTF-8 Windows encoding fallbacks directly addressing Daemon pipe decoding errors.
- **Topological Refinement**: Optimized DAG scheduling for zero-downtime execution environments.

### Removed
- **`watchflow replay`**: Formally deprecated and removed the older static JSON replay logic in favor of the next-generation `watchflow wal` (Write-Ahead Log) execution forensics system.

### Fixed
- Fixed an insidious `UnicodeEncodeError` within `rich` tracebacks executing untracked without TTY access.
- Corrected a `NotImplementedError` regarding `asyncio.add_signal_handler` under Windows ProactorEventLoops.
- Achieved a 100% `Mypy` and `Ruff` error-free rating, actively resolving over 100 historical code-smells and deep lint issues across all 12 platform modules.
