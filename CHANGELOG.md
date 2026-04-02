# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-04-03

### 🔐 Security

- Fixed critical command injection vulnerability by removing subprocess shell execution
- Enforced safe argument-based command execution using `asyncio.create_subprocess_exec`
- Added `substitute_args()` function for safe placeholder substitution in command arguments
- On Windows, commands are properly quoted through `["cmd", "/c", ...]` wrapper to prevent injection

### ⚡ Performance

- Improved watchdog thread performance by replacing full file hashing with stat-based `(mtime, size)` signature detection
- SQLite operations in engine now use `asyncio.to_thread()` to prevent event loop blocking

### 🧵 Stability

- Fixed subprocess zombie processes with proper process group termination
- Added fallback kill mechanisms: SIGKILL on POSIX, proc.kill() on Windows
- Process termination now waits 1 second before fallback to ensure clean exit

### 🖥️ CLI

- Fixed version output to include plain text "WatchFlow" alongside styled output for compatibility with tests and scripting

### 🌍 Environment

- Removed global environment variable mutation (WATCHFLOW_DEBUG is now passed explicitly to subprocesses)

### 🧪 Testing

- All tests passing (117/117)
- Ruff and mypy checks passing (src/ only)

### ⚠️ Breaking Changes

- Command configuration must now use string format in YAML (automatically parsed via `shlex.split()`)
- The internal API for `ProcessManager.run()` now expects `list[str]` instead of `str`

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
