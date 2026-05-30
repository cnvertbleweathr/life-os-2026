# Directory Structure
_Last updated: 2026-05-29_

## Summary
The repository is organized into five primary source areas: `app/` (Streamlit dashboard), `scripts/` (data pipeline scripts), `pipelines/` (heavier pipeline modules), `dbt/` (SQL transformation layer), and `data/` (all data files — raw, processed, exports, and the DuckDB warehouse). Config and goals live at the root level.

## Directory Tree

```
ons-2026/
├── app/                        # Streamlit dashboard
│   ├── Home.py                 # Home/overview page
│   └── pages/
│       ├── 1_Habits.py
│       ├── 2_Fitness.py
│       ├── 3_Reading.py
│       ├── 4_Goals.py
│       ├── 5_Music.py
│       └── 6_Shows.py
│
├── scripts/                    # Individual data pipeline scripts
│   ├── daily_sync.py           # Master orchestrator — runs all pipelines
│   ├── spotify_daily10_playlist.py
│   ├── spotify_daily10_decorate.py
│   ├── spotify_ingest_streaming.py
│   ├── spotify_metrics.py
│   ├── sync_playlist_artists.py
│   ├── strava_auth.py
│   ├── fetch_streams.py        # streamed.pk sports data
│   ├── calendar_export.py
│   ├── calendar_metrics.py
│   ├── shows_metrics.py
│   ├── ticketmaster_fetch_denver.py
│   ├── aeg_events_fetch.py
│   ├── aeg_events_inspect.py
│   ├── load_goals.py
│   ├── load_goal_progress.py
│   ├── sync_goal_progress.py
│   ├── create_goal_progress_template.py
│   ├── import_sugarwod_csv.py
│   ├── fitness_metrics.py      # NOT wired into daily_sync.py
│   ├── show_radar.py
│   ├── generate_insights.py    # dormant — not wired in
│   ├── weekly_reflection.py    # dormant — not wired in
│   └── export_for_insights.py  # dormant — not wired in
│
├── pipelines/                  # Heavier pipeline modules (imported by scripts)
│   ├── __init__.py
│   ├── habits_pipeline.py
│   ├── hardcover_pipeline.py
│   └── strava_pipeline.py
│
├── dbt/                        # SQL transformation layer (DuckDB via dbt)
│   ├── dbt_project.yml
│   ├── profiles/
│   │   └── profiles.yml
│   ├── models/
│   │   ├── staging/            # stg_*.sql — raw → clean
│   │   │   ├── stg_goals__annual_goals.sql
│   │   │   ├── stg_goals__progress.sql
│   │   │   ├── stg_habits__log.sql
│   │   │   └── stg_habits__summary.sql
│   │   └── marts/             # mart_*.sql — business-level aggregates
│   │       ├── mart_goal_detail.sql
│   │       ├── mart_goal_inventory.sql
│   │       ├── mart_goal_progress.sql
│   │       ├── mart_habit_performance.sql
│   │       ├── mart_habit_streaks.sql
│   │       └── mart_ons_healthcheck.sql
│   └── target/                # dbt compiled output (generated — do not edit)
│
├── data/                       # All data files
│   ├── warehouse/
│   │   └── ons.duckdb       # Primary database
│   ├── exports/                # CSV files read by Streamlit pages
│   │   ├── books_read.csv
│   │   ├── crossfit_lifts.csv
│   │   ├── crossfit_weekly.csv
│   │   ├── goal_progress.csv
│   │   ├── habit_daily.csv
│   │   ├── habit_summary.csv
│   │   ├── reading_summary.csv
│   │   ├── running_summary.csv
│   │   ├── running_weekly.csv
│   │   ├── spotify_summary.csv
│   │   └── manifest.json
│   ├── spotify/
│   │   ├── raw/streaming_history/   # Manual exports from Spotify
│   │   ├── processed/               # Cleaned/enriched files
│   │   └── metrics/
│   ├── shows/
│   │   ├── raw/aeg/                 # AEG venue event JSON (dated snapshots)
│   │   ├── raw/ticketmaster/        # Ticketmaster event JSON (dated, paginated)
│   │   ├── processed/               # Merged/deduped event CSVs
│   │   └── metrics/
│   ├── calendar/
│   │   ├── raw/                     # Google Calendar JSON exports (dated)
│   │   ├── processed/               # Clean events CSV
│   │   └── metrics/
│   ├── running/raw/                 # Strava OAuth tokens
│   ├── sugarwod/
│   │   ├── exports/                 # Manual SugarWOD CSV exports
│   │   └── processed/
│   ├── habits/
│   │   └── habits_log.jsonl         # Append-only habits log
│   ├── manual/
│   │   └── goal_progress.csv        # Hand-maintained goal progress
│   ├── insights/
│   │   └── latest.json              # Output from dormant insights pipeline
│   ├── streams/
│   │   └── today.json               # Sports streams (from streamed.pk)
│   └── daily/                       # Per-day sync logs (YYYY-MM-DD/)
│       ├── launchd.log
│       └── launchd.err
│
├── goals/
│   └── 2026.yaml                    # Annual goals definition
│
├── secrets/                         # OAuth tokens and credentials (gitignored)
│   ├── google_calendar_credentials.json
│   ├── google_calendar_token.json
│   └── spotify_token_cache.json
│
├── .env                             # Local environment variables (gitignored)
├── .env.example                     # Template for required env vars
├── pyproject.toml                   # Python project config (uv)
├── requirements.txt                 # Python dependencies
├── uv.lock                          # Lockfile
├── run_pipelines.py                 # Legacy entry point (superseded by daily_sync.py)
├── README.md
├── CHECKPOINT.md                    # Development notes (partially stale)
└── MIGRATION.md                     # Migration notes
```

## File Naming Conventions

| Pattern | Meaning |
|---|---|
| `stg_<domain>__<entity>.sql` | dbt staging model |
| `mart_<entity>.sql` | dbt mart model |
| `<domain>_pipeline.py` | Heavier pipeline module in `pipelines/` |
| `<domain>_<action>.py` | Script in `scripts/` |
| `*_2026.csv` | Year-scoped data export |
| `events_YYYYMMDD*.json` | Dated raw API snapshot |
| `<N>_<PageName>.py` | Numbered Streamlit page (controls sidebar order) |

## Source vs Generated Files

**Source (committed, hand-maintained):**
- All `scripts/`, `pipelines/`, `app/`, `dbt/models/` Python and SQL files
- `goals/2026.yaml`, `.env.example`, `requirements.txt`, `pyproject.toml`
- `data/spotify/raw/` (manual Spotify data exports)
- `data/sugarwod/exports/` (manual SugarWOD exports)
- `data/manual/goal_progress.csv`

**Generated (committed for persistence, written by pipelines):**
- `data/exports/*.csv` — written by dbt + pipeline scripts, read by Streamlit
- `data/*/processed/` — cleaned/enriched versions of raw data
- `data/*/metrics/` — aggregated metric CSVs
- `data/spotify/processed/daily10_latest.json`, `streams_clean.csv`
- `data/shows/*.json` — radar/artist show caches
- `data/warehouse/ons.duckdb` — primary database

**Generated (gitignored):**
- `data/daily/` — per-day sync logs
- `data/calendar/raw/` — raw Google Calendar JSON snapshots
- `data/shows/raw/` — raw Ticketmaster/AEG JSON snapshots
- `dbt/target/` — dbt compiled output
- `.env`, `secrets/`, `.spotify_token_cache`, `.cache/`

## Entry Points

| Entry point | How it runs | Purpose |
|---|---|---|
| `scripts/daily_sync.py` | launchd (9am daily) | Master orchestrator — runs all active pipelines |
| `app/Home.py` | `streamlit run app/Home.py` | Launches the Streamlit dashboard |
| `run_pipelines.py` | Manual | Legacy orchestrator (superseded) |
| Individual `scripts/*.py` | Manual / ad-hoc | Run a single pipeline step |
| `dbt run` (from `dbt/`) | Called by `daily_sync.py` | SQL transformation layer |
