# Architecture
_Last updated: 2026-05-29_

## Summary

Life OS 2026 is a personal analytics platform built on a modern data stack: external APIs and local inputs are ingested via DLT pipelines into a local DuckDB warehouse, transformed by dbt into clean mart tables, and surfaced through a Streamlit multi-page dashboard. The entire pipeline runs automatically every morning at 9am via macOS launchd, with zero manual intervention required to keep data fresh.

---

## System Overview

```
External APIs         Local Inputs
(Strava, Hardcover,   (habits JSONL,
 Spotify, Calendar,    SugarWOD CSV,
 AEG, Ticketmaster,    goals YAML,
 streamed.pk)          goal_progress.csv)
        │                     │
        ▼                     ▼
┌────────────────────────────────────────┐
│          Ingestion Layer               │
│  pipelines/  ←── DLT pipelines        │
│  scripts/    ←── ad-hoc fetch scripts │
└────────────────┬───────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────┐
│      DuckDB Warehouse                  │
│   data/warehouse/lifeos.duckdb         │
│                                        │
│  strava.*   hardcover.*   habits.*     │
│  raw.*      calendar.*                 │
└────────────────┬───────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────┐
│         dbt Transformation             │
│   dbt/models/staging/   stg_*         │
│   dbt/models/marts/     mart_*        │
└────────────────┬───────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────┐
│       Streamlit Dashboard              │
│   app/Home.py + app/pages/            │
│   Queries mart_* tables only          │
└────────────────────────────────────────┘
```

---

## Major Components

| Component | Responsibility | Location |
|-----------|----------------|----------|
| Orchestrator | Runs all steps in order daily, logs results | `scripts/daily_sync.py` |
| DLT Pipelines | API extraction + upsert into DuckDB | `pipelines/` |
| Fetch Scripts | Secondary data fetch (shows, streams, Spotify) | `scripts/` |
| DuckDB Warehouse | Single local database, all raw + transformed data | `data/warehouse/lifeos.duckdb` |
| dbt Models | Staging views + mart tables built on raw schemas | `dbt/models/` |
| Streamlit Dashboard | 7-page interactive UI, queries marts directly | `app/` |
| Goals Definition | Declarative YAML intent file | `goals/2026.yaml` |
| AI Co-processor | OpenAI gpt-4o for digest; gpt-image-1 for cover art | called from `app/Home.py`, `scripts/spotify_daily10_decorate.py` |

---

## Data Flow

### Primary Daily Path (automated via launchd at 9am)

`launchd` → `scripts/daily_sync.py` runs 15 steps in order:

1. **DLT pipelines** (`run_pipelines.py --only strava/hardcover/habits`)
   - `pipelines/strava_pipeline.py` → fetches Strava OAuth API → upserts `strava.activities`, replaces `strava.running_summary`
   - `pipelines/hardcover_pipeline.py` → GraphQL API → upserts `hardcover.books_read`, replaces `hardcover.reading_summary`
   - `pipelines/habits_pipeline.py` → reads `data/habits/habits_log.jsonl` → upserts `habits.habit_log`, replaces `habits.habit_summary`

2. **Calendar** (`scripts/calendar_export.py`, `scripts/calendar_metrics.py`)
   - Google Calendar OAuth API → `data/calendar/raw/events_*.json` → `data/calendar/processed/events_clean_2026.csv`
   - Date night metrics → `data/calendar/metrics/`

3. **Shows** (`scripts/aeg_events_fetch.py`, `scripts/ticketmaster_fetch_denver.py`, `scripts/shows_metrics.py`)
   - AEG + Ticketmaster public APIs → `data/shows/raw/` → `data/shows/processed/` + `data/shows/metrics/`

4. **Spotify** (`scripts/spotify_ingest_streaming.py`, `scripts/spotify_metrics.py`, `scripts/spotify_daily10_playlist.py`)
   - JSON export files from `data/spotify/raw/streaming_history/` → `data/spotify/processed/streams_clean.csv`
   - YTD metrics → `data/spotify/metrics/`
   - Daily 10 playlist generated via Spotipy + written to `data/spotify/processed/daily10_latest.json`

5. **Streams** (`scripts/fetch_streams.py`) → streamed.pk API → `data/streams/today.json`

6. **Playlist/show cross-reference** (`scripts/sync_playlist_artists.py`) → matches Spotify playlist artists against upcoming shows → `data/shows/my_artist_shows.json`

7. **Goal progress sync** (`scripts/sync_goal_progress.py`) → queries DuckDB actuals → writes `data/manual/goal_progress.csv` → calls `scripts/load_goal_progress.py` → loads `raw.raw_goal_progress` in DuckDB

8. **dbt run** → builds all staging views and mart tables in DuckDB from raw schemas

Each step writes a per-step log to `data/daily/YYYY-MM-DD/<step>.log` and a `summary.json`.

### Habit Logging (user-triggered)

User opens `app/pages/1_Habits.py` → checks boxes → Streamlit writes/updates today's entry in `data/habits/habits_log.jsonl` (append-only JSONL). The next daily sync pushes this into `habits.habit_log` via the DLT pipeline.

### Dashboard Query Path

Any page in `app/` opens read-only connection to `data/warehouse/lifeos.duckdb` and queries `main_marts.*` (or `main_staging.*`) tables. Data is cached with `@st.cache_data(ttl=300–600)`.

---

## DuckDB Schema Structure

| Schema | Tables | Source |
|--------|--------|--------|
| `strava` | `activities`, `running_summary` | DLT / Strava API |
| `hardcover` | `books_read`, `reading_summary` | DLT / Hardcover GraphQL |
| `habits` | `habit_log`, `habit_summary` | DLT / local JSONL |
| `raw` | `raw_goals`, `raw_goal_progress` | load scripts |
| `main_staging` | `stg_goals__annual_goals`, `stg_goals__progress`, `stg_habits__log`, `stg_habits__summary` | dbt views |
| `main_marts` | `mart_goal_progress`, `mart_goal_detail`, `mart_habit_performance`, `mart_habit_streaks`, `mart_lifeos_healthcheck`, `mart_goal_inventory` | dbt tables |

---

## dbt Transformation Layer

Staging models (materialized as views) clean and type raw sources:
- `dbt/models/staging/stg_goals__annual_goals.sql` — unnests `goals/2026.yaml` JSON into one row per goal
- `dbt/models/staging/stg_goals__progress.sql` — cleans `raw.raw_goal_progress`
- `dbt/models/staging/stg_habits__log.sql` — cleans `habits.habit_log`, adds year/month columns
- `dbt/models/staging/stg_habits__summary.sql` — cleans `habits.habit_summary`

Mart models (materialized as tables) build business logic:
- `dbt/models/marts/mart_goal_detail.sql` — goal inventory with metadata
- `dbt/models/marts/mart_goal_progress.sql` — joins goals + actuals, computes `progress_percent`
- `dbt/models/marts/mart_habit_performance.sql` — daily pivot table + completion %
- `dbt/models/marts/mart_habit_streaks.sql` — current streak + longest streak per habit
- `dbt/models/marts/mart_lifeos_healthcheck.sql` — system health metrics
- `dbt/models/marts/mart_goal_inventory.sql` — full goal list

dbt profile targets DuckDB at `/Users/kg/life-os-2026/data/warehouse/lifeos.duckdb`, schema `main`, 4 threads.

---

## Scheduling and Automation

**Trigger:** macOS launchd plist (not in repo) fires daily at 9am.

**Entry point:** `scripts/daily_sync.py`

**Behavior:**
- `--only` flag: run a subset of named steps or tag groups (`pipelines`, `calendar`, `shows`, `spotify`, `streams`, `dbt`)
- `--skip` flag: exclude named steps
- `--year` flag: override the year (default: current year)
- Steps with `required=True` (`sync_goal_progress`, `dbt`) halt the sync on failure
- All other steps are best-effort; failure is logged but execution continues
- `run_if_exists` guard: steps with a missing prerequisite file are silently skipped

**Log output:**
- Per-step logs: `data/daily/YYYY-MM-DD/<step>.log`
- Daily summary JSON: `data/daily/YYYY-MM-DD/summary.json`
- launchd stdout/stderr: `data/daily/launchd.log`, `data/daily/launchd.err`

**Manual run:**
```bash
source .venv/bin/activate
python scripts/daily_sync.py
streamlit run app/Home.py
```

---

## Dashboard Pages

| Page | Entry Point | Data Sources |
|------|-------------|--------------|
| Home / Digest | `app/Home.py` | `data/streams/today.json`, `data/calendar/processed/events_clean_2026.csv`, `main_marts.mart_goal_progress`, `data/shows/my_artist_shows.json`, OpenAI API |
| Habits | `app/pages/1_Habits.py` | `data/habits/habits_log.jsonl` (write), `main_marts.mart_habit_*` (read) |
| Fitness | `app/pages/2_Fitness.py` | `main_marts.*`, DuckDB `strava.*`, `data/sugarwod/` |
| Reading | `app/pages/3_Reading.py` | DuckDB `hardcover.*` |
| Goals | `app/pages/4_Goals.py` | `main_marts.mart_goal_progress` |
| Music | `app/pages/5_Music.py` | `data/spotify/processed/streams_clean.csv`, `data/spotify/metrics/`, `data/spotify/processed/daily10_latest.json` |
| Shows | `app/pages/6_Shows.py` | `data/shows/processed/`, `data/shows/metrics/`, `data/shows/my_artist_shows.json` |

---

## Key Design Patterns

**Separation of concerns:**
- Intent: `goals/2026.yaml` (declarative, version-controlled)
- Facts: `data/` (local, gitignored)
- Logic: `scripts/` and `dbt/` (version-controlled)

**DuckDB as the hub:** All sources land in DuckDB. No cross-script CSV hand-offs for data that passes through the warehouse. The dashboard queries marts only, never raw schemas.

**DLT for structured extraction:** DLT handles schema inference, merge semantics (`write_disposition="merge"` with `primary_key`), and load state. Strava and Hardcover pipelines use merge on a natural key; habits pipeline merges on `(log_date, habit)`.

**AI as bounded co-processor:**
- `app/Home.py` calls OpenAI `gpt-4o` to generate a calendar digest (on-demand, cached in `st.session_state` per day)
- `scripts/spotify_daily10_decorate.py` calls `gpt-image-1` to generate playlist cover art
- `scripts/generate_insights.py` calls an LLM with exported CSVs to produce `data/insights/latest.json` (dormant — not wired into daily sync)

**Step orchestration pattern** (`scripts/daily_sync.py`):
- Steps are defined as `Step` dataclasses with `name`, `cmd`, `required`, `run_if_exists`, `tags`
- Each step is run via `subprocess.run()` with its own log file
- Tags allow bulk selection (`--only pipelines` runs all three DLT steps)

---

## Entry Points Summary

| Entrypoint | How invoked | Purpose |
|------------|-------------|---------|
| `scripts/daily_sync.py` | launchd (9am) or `python scripts/daily_sync.py` | Runs all 15 pipeline steps |
| `run_pipelines.py` | called by daily_sync.py or directly | Runs DLT pipelines (strava, hardcover, habits) |
| `app/Home.py` | `streamlit run app/Home.py` | Launches the multi-page dashboard |
| `scripts/strava_auth.py` | One-time manual setup | OAuth token bootstrap for Strava |
| `scripts/calendar_export.py` | One-time or via daily_sync | OAuth token bootstrap + export for Google Calendar |
| `scripts/import_sugarwod_csv.py` | Manual, on CSV export from SugarWOD | Loads CrossFit data |
| `scripts/spotify_ingest_streaming.py` | Via daily_sync or manual | Processes Spotify JSON export files |

---

*Architecture analysis: 2026-05-29*
