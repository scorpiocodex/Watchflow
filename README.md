<div align="center">

# ◢ 𝙒𝘼𝙏𝘾𝙃𝙁𝙇𝙊𝙒 ◣
## ❖ NEXUS A.I. INTENT ENGINE ❖
  
A sleek, next-generation automation platform that watches your files and runs your tasks automatically.

[![Build Status](https://img.shields.io/badge/Build-Passing-brightgreen.svg?style=for-the-badge)](https://github.com/scorpiocodex/Watchflow)
[![Code Quality](https://img.shields.io/badge/Code_Quality-Pristine-purple.svg?style=for-the-badge)](https://github.com/scorpiocodex/Watchflow)
[![Version](https://img.shields.io/badge/Version-0.1.0-blue.svg?style=for-the-badge)](https://github.com/scorpiocodex/Watchflow)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

*Author:* **ScorpioCodeX**  
*Contact:* **scorpiocodex0@gmail.com**

</div>

---

## ⚡ WHAT IS WATCHFLOW?

**WatchFlow** is a modern, powerful tool designed to make automating your workflow effortless. If you write code, you probably run the same commands over and over again—like testing, formatting, and building your project. 

WatchFlow sits in the background, carefully watching your files. The moment you save a file, it instantly runs the exact commands you need. It features a stunning, sci-fi inspired dashboard right in your terminal, making automation look and feel amazing.

---

## 🌌 NEXT-GENERATION FEATURES

- 🧠 **Plain English Rules**: Tell WatchFlow what to do using a simple, easy-to-read configuration file. If a file changes, WatchFlow knows what to do.
- ⚡ **Lightning Fast & Smart Execution**: WatchFlow runs your tasks in parallel when possible and automatically skips commands if previous steps fail.
- 🛸 **Live Holographic Dashboard**: Press `watchflow run` to launch a stunning visual dashboard in your terminal showing live logs, running tasks, and system performance.
- 🛡️ **Time-Travel Logging**: WatchFlow records everything. If you leave your computer running, you can look back and see exactly what changed and what scripts ran while you were gone.
- 📊 **Built-in Analytics**: See how often your tests fail or how long your builds take over time with local, private analytics.
- 👻 **Ghost Mode (Daemon)**: Run WatchFlow completely silently in the background (`watchflow daemon start`), so it never clutters your active terminal.
- 🧪 **Safe Simulation (Dry-Run)**: Want to test complex rules without actually running any destructive commands? Use `--dry-run` to trace what *would* happen safely.

---

## 🧑‍🚀 INSTALLATION PROTOCOL

WatchFlow is maintained securely on GitHub. To use it, simply install it directly from this repository using `pipx` or `pip`.

### The Best Way (`pipx`)
If you want WatchFlow to be available anywhere on your computer in any folder, use `pipx`:
```bash
pipx install git+https://github.com/scorpiocodex/Watchflow.git
```

### The Standard Way (`pip`)
If you're using a virtual environment for a specific project, `pip` works perfectly:
```bash
pip install git+https://github.com/scorpiocodex/Watchflow.git
```

---

## 🚀 QUICK START GUIDE

Ready to experience the future? Getting started takes less than a minute.

**1. Initialize your project**
Open your terminal in your project folder and run:
```bash
watchflow init
```
*This asks you a few simple questions and generates a basic `watchflow.yaml` configuration file for you.*

**2. Check your setup**
Make sure your rules are written correctly and your system is ready:
```bash
watchflow validate
```

**3. Boot the Orchestrator!**
Start the live dashboard and let WatchFlow do the work:
```bash
watchflow run
```
*Now, keep this terminal open on the side. Every time you save a file in your project, WatchFlow will instantly run your tasks!*

---

### 🛠️ Useful Commands

| Command | What it does |
| --- | --- |
| `watchflow run` | Starts the live visual dashboard. (Use `--dry-run` to simulate tasks) |
| `watchflow daemon start` | Starts WatchFlow silently in the background. |
| `watchflow daemon stop` | Stops the background WatchFlow process. |
| `watchflow explain` | Reads your config file and explains what it does in plain English. |
| `watchflow graph` | Draws a visual map of how your tasks connect to each other. |
| `watchflow analytics` | Shows you statistics on your past runs and task success rates. |
| `watchflow wal list` | Shows a history log of all past events and file changes. |

---

## 📖 CONFIGURATION EXAMPLE

Your automation rules live inside a beautifully simple file called `watchflow.yaml`. 

Here is what a simple configuration looks like to run Python tests whenever a file is saved:

```yaml
version: '1'

# 1. WHAT TO WATCH
watchers:
  python-tracker:
    paths: ["src/", "tests/"]   # Folders to watch
    events: ["modified"]        # Watch for saved/modified files
    patterns: ["*.py"]          # Only care about Python files

# 2. WHAT TO DO
pipelines:
  quality-check:
    trigger: "python-tracker"   # Run this when the tracker above sees a change
    steps:
      - name: "Format Code"
        cmd: "ruff format src/"
      - name: "Run Tests"
        cmd: "pytest tests/"
        depends_on: ["Format Code"] # Wait for formatting to finish first!
```
*In this example, whenever you save any `.py` file, WatchFlow instantly formats the code. Once formatting is done, it automatically runs your tests. It's that simple!*

---

<div align="center">
  <p><b>Created with passion by ScorpioCodeX.</b></p>
  <p><i>The future of reactive automation has arrived.</i></p>
</div>
