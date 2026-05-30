# Coding Conventions
_Last updated: 2026-05-29_

## Summary

This is a personal data-pipeline and Streamlit dashboard project written entirely in Python 3.12. There are no linting or formatting tools configured (no ruff, flake8, black, or mypy configs). Conventions are consistent across scripts and pipelines because the codebase is single-author, and the dominant style is clean imperative Python with explicit type hints and `from __future__ import annotations` throughout.

---

## Code Style and Formatting

**Formatter:** None configured. No `pyproject.toml [tool.ruff]`, `.flake8`, `setup.cfg`, or `biome.json` found.

**Type checking:** `"python.analysis.typeCheckingMode": "basic"` in `.vscode/settings.json`. No mypy or pyright config file. No `type: ignore` suppressions exist in the codebase.

**Python version target:** 3.12 (declared in `pyproject.toml`: `requires-python = ">=3.12,<3.15"`).

**Consistent style observed across all files:**
- 4-space indentation (no tabs)
- `from __future__ import annotations` at the top of every script and pipeline file — enables PEP 604 `X | Y` union syntax for Python 3.10+ style on 3.12
- Double-quoted strings are the norm; single quotes used only inside f-strings when needed
- Trailing commas in multi-line argument lists and data structures
- `encoding="utf-8"` specified on every `open()` call
- `newline=""` specified on every CSV `open()` call for write operations

---

## Naming Conventions

**Files:**
- Scripts: `snake_case.py` — e.g., `spotify_daily10_playlist.py`, `sync_goal_progress.py`
- App pages: numeric prefix + title-case — e.g., `1_Habits.py`, `5_Music.py`
- Pipelines: `{service}_pipeline.py` — e.g., `strava_pipeline.py`
- Data files: `snake_case` with date stamps — e.g., `events_2026_20260528.json`

**Functions:**
- Public/main functions: `snake_case` — e.g., `build_steps()`, `run_pipeline()`, `fetch_tewnidge()`
- Private/internal helpers: leading underscore `_snake_case` — e.g., `_parse_dt()`, `_as_aware_denver()`, `_normalize_venue()`, `_hc_post()`, `_load_tokens()`
- Entry point is always named `main()` and returns `int` (0 for success, 1 for failure)

**Variables:**
- `snake_case` throughout
- Constants and module-level path variables: `UPPER_SNAKE_CASE` — e.g., `ROOT`, `DB_PATH`, `STREAMS_CSV`, `API_BASE`, `DENVER_TZ`
- Loop variables: short descriptive names — `act`, `row`, `rec`, `ub`, `tk`

**Classes:**
- `PascalCase` — only two classes exist: `Step` (dataclass in `daily_sync.py`) and `TrackKey` (frozen dataclass in `spotify_daily10_playlist.py`)

**Type annotations:**
- All function signatures include return type annotations
- Parameters use stdlib types from `typing` (`List`, `Dict`, `Optional`, `Iterator`, `Tuple`) in older-style files, and the newer lowercase built-ins (`list`, `dict`, `tuple`) in newer files — both coexist
- `from __future__ import annotations` makes both styles work at runtime

---

## Module-Level Structure Pattern

Every script follows this consistent layout:

```python
#!/usr/bin/env python3
"""Module docstring — what it does, what tables it produces, usage examples."""
from __future__ import annotations

# stdlib imports
import argparse, csv, json, os, ...
from datetime import datetime
from pathlib import Path
from typing import ...

# third-party imports
import requests
from dotenv import load_dotenv

# optional: load_dotenv()
ROOT = Path(__file__).resolve().parents[1]

# Module-level path constants
DB_PATH = ROOT / "data" / "warehouse" / "lifeos.duckdb"
SOME_PATH = ROOT / "data" / ...

# ---------------------------------------------------------------------------
# Section name
# ---------------------------------------------------------------------------

def _private_helper(...) -> ...:
    ...

def public_helper(...) -> ...:
    ...

def main() -> int:
    ...

if __name__ == "__main__":
    raise SystemExit(main())
```

**Section separators:** Long dashes `# ---------------------------------------------------------------------------` (75 dashes) for top-level sections in pipelines; shorter `# --------------------` (20 dashes) in some scripts. Inline step comments use `# ------------------------------------------------------------------`.

---

## Import Organization

**Order (consistent across files):**
1. `from __future__ import annotations`
2. Standard library (`argparse`, `csv`, `json`, `os`, `subprocess`, `sys`, `time`)
3. `from datetime import ...`, `from pathlib import Path`, `from typing import ...`
4. Third-party (`requests`, `dlt`, `pandas`, `yaml`, `spotipy`, `streamlit`)
5. Local (none — no internal packages imported across modules)

**No path aliases** — all imports are absolute.

---

## Path Resolution

All files compute the repo root the same way:

```python
ROOT = Path(__file__).resolve().parents[1]
```

All data paths are constructed as `ROOT / "data" / ...`. No hardcoded absolute paths. This makes scripts runnable from any working directory.

---

## Error Handling

**Fatal configuration errors:** `raise SystemExit("Human-readable message")` at import time or at the top of `main()`. Used when env vars or required files are missing.

```python
if not client_id or not client_secret:
    raise SystemExit("Missing SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET")
```

**Runtime errors from APIs/IO:** `raise RuntimeError(...)` with descriptive message. Example from `strava_pipeline.py`:

```python
raise RuntimeError("Missing STRAVA_CLIENT_ID or STRAVA_CLIENT_SECRET in .env")
```

**Missing-file preconditions:** `raise FileNotFoundError(...)` or `raise SystemExit(f"Missing {path}. Run X first.")` — always tells the user what to run next.

**Non-fatal data errors:** `except Exception: continue` or silent `return None` / `return []`. Used heavily for per-row parsing (bad timestamps, malformed JSON lines, bad CSV fields):

```python
try:
    row = json.loads(line)
except json.JSONDecodeError:
    continue
```

**HTTP requests:** Always `r.raise_for_status()` immediately after the request. Always `timeout=30` (20 for some calls). Never silent HTTP failures.

**Orchestrator-level failures:** `daily_sync.py` catches `Exception` per subprocess step, logs it, and marks the step `"failed"` in the summary JSON. Required steps abort the run; optional steps are noted and skipped.

**Streamlit pages:** `try/except Exception: pass` or `st.info(...)` — all data-loading failures degrade gracefully to empty state rather than crashing the page.

---

## Logging

**No stdlib `logging` module used anywhere.** All output is `print()` to stdout.

**Patterns observed:**

- Scripts print progress lines as they run: `print(f"Wrote: {out_path}")`, `print(f"Fetched {n} events")`
- Pipelines delegate to DLT's built-in print output: `print(load_info)`
- `daily_sync.py` captures each step's stdout/stderr to per-step `.log` files in `data/daily/YYYY-MM-DD/`
- Streamlit pages use `st.info()` / `st.warning()` / `st.success()` for user-visible status
- `file=sys.stderr` used for error messages in orchestrator paths: `print(f"✗ {name} failed: {e}", file=sys.stderr)`

**Log file location:** `data/daily/YYYY-MM-DD/{step_name}.log` — one file per daily-sync step, written by `daily_sync.py`. `data/daily/launchd.log` / `launchd.err` for cron output.

---

## Configuration Management

**Environment variables:** All secrets and external URLs come from `.env` (loaded with `python-dotenv`).

- Scripts call `load_dotenv()` or `load_dotenv(ROOT / ".env")` near the top
- All env var reads use `os.getenv("VAR_NAME", "default")` with explicit fallbacks
- `.env.example` documents all required variables with placeholder values
- Secrets files (OAuth tokens, Google credentials) stored in `secrets/` directory

**Goals configuration:** `goals/2026.yaml` — read with `yaml.safe_load()`. Queried via `safe_get(goals, ["domains", "personal", "outcomes", "key"], default)` to avoid KeyError on missing keys.

**No config classes or Pydantic models** — configuration is read inline at the point of use.

---

## Comments

**Module docstrings:** Multi-line triple-quoted strings at the top of pipeline files documenting purpose, tables produced, and CLI usage. Some scripts omit the module docstring (e.g., `spotify_metrics.py`, `shows_metrics.py`).

**Function docstrings:** Used selectively on complex or non-obvious functions (e.g., `normalize_timestamp_to_iso`, `iter_rows_from_json`, `running_summary_resource`). Simple helpers often have no docstring.

**Inline comments:** Used to explain non-obvious logic — date format quirks, API pagination, dedup strategies, fallback logic. Example:
```python
# Legacy format
# Handle trailing Z (UTC)
# all-day events use "date"; timed use "dateTime"
```

**No TODO or FIXME comments** exist anywhere in the codebase.

---

## Function Design

**Entry point:** Every runnable script ends with:
```python
if __name__ == "__main__":
    raise SystemExit(main())
```
`main()` always returns `int` (0 or 1), never `None`.

**Size:** Functions are generally short (10-40 lines). Longer functions are `main()` functions that sequence steps. No functions exceed ~80 lines.

**Arguments:** CLI args always parsed with `argparse` in `main()`. `--year` defaults to `datetime.now().year` in every script that supports it. `--dry-run` supported in scripts that write files.

**Helper naming:** Internal helpers that should not be called externally use `_` prefix. Public helpers have no prefix.

---

## dbt SQL Conventions

- Model files: `staging/stg_{source}__{entity}.sql`, `marts/mart_{name}.sql`
- Staging models materialized as views, mart models as tables
- SQL style: lowercase keywords, each selected column on its own line, trailing comma after last column
- Source references are direct schema-qualified table names (`habits.habit_log`, not dbt `source()` macro)
