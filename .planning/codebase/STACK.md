# Technology Stack
_Last updated: 2026-05-29_

## Summary

Life OS 2026 is a pure-Python personal analytics platform. It uses Python 3.12 as the sole language, managed by `uv` for packaging and virtual environment. The stack follows a modern data-engineering pattern: DLT for extraction, DuckDB as the local warehouse, dbt for transformation, and Streamlit for the dashboard UI.

---

## Languages

**Primary:**
- Python 3.12 — all scripts, pipelines, dashboard pages, and orchestration

No JavaScript, TypeScript, or frontend build tooling. Streamlit renders the UI entirely from Python.

---

## Runtime

**Interpreter:** Python 3.12.13 (system install, confirmed via `python3 --version`)

**Python version requirement:** `>=3.12,<3.15` (declared in `pyproject.toml`)

**Package Manager:** `uv` 0.11.8 (Homebrew install)
- Lockfile: `uv.lock` — present and committed
- Virtual environment: `.venv/` — local, gitignored

**No `.python-version` or `.nvmrc` files present.**

---

## Frameworks

**Dashboard / UI:**
- `streamlit` 1.57.0 — multi-page dashboard at `app/Home.py` and `app/pages/`
- `plotly` 6.7.0 — interactive charts (used in dashboard pages)
- `pandas` 3.0.2 (pyproject) / 2.3.3 (requirements.txt) — dataframes throughout; 3.x resolved in uv.lock

**Data Ingestion:**
- `dlt` 1.26.0 (resolved) / `>=1.4.0` (declared) — DLT pipelines in `pipelines/`; schema inference, merge semantics, load state management
- `dlt[duckdb]` extra — DLT writes directly to DuckDB

**Data Warehouse:**
- `duckdb` 1.5.2 — embedded analytical database at `data/warehouse/lifeos.duckdb`; all pipelines, scripts, and the dashboard query this file directly

**Transformation:**
- `dbt-core` 1.11.8 — SQL transformation layer in `dbt/`
- `dbt-duckdb` 1.10.1 — dbt adapter for DuckDB

**Image Processing:**
- `pillow` 12.1.0 — JPEG compression for Spotify playlist cover art in `scripts/spotify_daily10_decorate.py`

**Data Serialization:**
- `pyarrow` 24.0.0 — columnar format support (DLT/DuckDB dependency)
- `pyyaml` 6.0.3 — goals config at `goals/2026.yaml`

---

## Key Dependencies (Resolved Versions from uv.lock)

| Package | Version | Purpose |
|---|---|---|
| `streamlit` | 1.57.0 | Dashboard UI |
| `dlt` | 1.26.0 | Data extraction pipelines |
| `duckdb` | 1.5.2 | Local analytical warehouse |
| `dbt-core` | 1.11.8 | SQL transformation |
| `dbt-duckdb` | 1.10.1 | dbt → DuckDB adapter |
| `pandas` | 2.3.3 | Data manipulation |
| `plotly` | 6.7.0 | Interactive charts |
| `spotipy` | 2.26.0 | Spotify Web API client |
| `google-api-python-client` | 2.196.0 | Google Calendar API |
| `google-auth-oauthlib` | 1.4.0 | Google OAuth flows |
| `requests` | 2.33.1 | HTTP calls to all external APIs |
| `python-dotenv` | 1.2.2 | `.env` loading |
| `pyyaml` | 6.0.3 | Goals YAML config |
| `pyarrow` | 24.0.0 | Columnar data support |
| `pillow` | 12.1.0 | JPEG image processing |
| `redis` | 7.4.0 | In lock but not used in any `.py` file (DLT transitive dependency) |

---

## Build Tools

**No build step.** Python files are run directly. No compilation, bundling, or transpilation.

**Orchestration:**
- `scripts/daily_sync.py` — custom orchestrator that runs all pipeline steps via `subprocess.run()`. Triggered at 9am by macOS `launchd`. Run manually with `python scripts/daily_sync.py`.
- `run_pipelines.py` — direct DLT pipeline runner (called by `daily_sync.py`)

**dbt:**
- `dbt run --profiles-dir dbt/profiles --project-dir dbt` — run by `daily_sync.py` as the final step
- Profile config: `dbt/profiles/profiles.yml` — points to `data/warehouse/lifeos.duckdb`, schema `main`, 4 threads

---

## Configuration

**Environment:**
- All secrets and API keys loaded from `.env` via `python-dotenv`
- `.env.example` documents all required variables (see INTEGRATIONS.md for full list)
- `.env` is gitignored

**Goals:**
- `goals/2026.yaml` — declarative goal definitions read at pipeline runtime by `pipelines/hardcover_pipeline.py` and `scripts/sync_goal_progress.py`

---

## Platform / Runtime Environment

**Development + Production:** Same machine (macOS). No containers, no cloud deployment.

**Scheduler:** macOS `launchd` — triggers `daily_sync.py` at 9am daily. Log output written to `data/daily/launchd.log` and `data/daily/launchd.err`.

**No Docker, no CI/CD pipeline, no remote deployment.**

**Dashboard startup:**
```bash
source .venv/bin/activate
streamlit run app/Home.py
```

---

## Notable Absent Technologies

- No Node.js / npm / frontend build tools
- No Docker or containerization
- No cloud database (DuckDB is fully local)
- No test framework (no `pytest`, `unittest`, or test files)
- Redis is in the lock file as a DLT transitive dependency but is not used directly anywhere in the codebase
- Pixela (habit tracking SaaS) was previously used; fully replaced by local DuckDB via DLT (`pipelines/habits_pipeline.py`)
