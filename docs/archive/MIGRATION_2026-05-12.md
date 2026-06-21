# Operating Narcisystem — Migration Notes (2026-05-12)

## Summary of changes

### Pixela → removed entirely
Pixela was the third-party habit tracking app. It's gone. All four habits
(meditation, pushups_100, nonfiction_pages_10, fiction_pages_10) are now
logged locally via the Streamlit dashboard and stored in DuckDB.

**Deleted scripts:**
- `scripts/pixela_client.py`
- `scripts/pixela_habits.py`
- `scripts/pixela_metrics.py`
- `scripts/setup_pixela_graphs.py`

You can also remove `PIXELA_USERNAME` and `PIXELA_TOKEN` from your `.env`.

---

### DLT — new extraction layer
[DLT (Data Load Tool)](https://dlthub.com) replaces the bespoke `*_fetch.py`
scripts for Strava and Hardcover. It handles schema inference, loading state,
and writes directly into DuckDB with proper merge/replace semantics.

**New pipelines (in `pipelines/`):**

| Pipeline | Replaces | Writes to (DuckDB schema) |
|---|---|---|
| `habits_pipeline.py` | Pixela entirely | `habits.*` |
| `strava_pipeline.py` | `fetch_strava_activities.py` + `running_metrics.py` | `strava.*` |
| `hardcover_pipeline.py` | `hardcover_fetch.py` + `hardcover_metrics.py` | `hardcover.*` |

**Deleted scripts (replaced by DLT):**
- `scripts/fetch_strava_activities.py`
- `scripts/running_metrics.py`
- `scripts/hardcover_fetch.py`
- `scripts/hardcover_metrics.py`

**Run all pipelines:**
```bash
python run_pipelines.py               # all three
python run_pipelines.py --only habits # just habits
python run_pipelines.py --only strava hardcover
```

`daily_sync.py` has been updated to call these instead of the old scripts.

---

### Streamlit — full multi-page app
`app/streamlit_app.py` is replaced by a proper multi-page app.

**New structure:**
```
app/
  Home.py              ← entry point (system status + goals scoreboard)
  pages/
    1_Habits.py        ← checkbox log + history heatmap + streaks
    2_Fitness.py       ← Strava running + SugarWOD CrossFit
    3_Reading.py       ← Hardcover fiction/nonfiction
    4_Goals.py         ← full goal inventory with progress bars
```

**Run with:**
```bash
streamlit run app/Home.py
```

---

### New dbt models
Two new staging models and two new mart models for habits:

- `dbt/models/staging/stg_habits__log.sql`
- `dbt/models/staging/stg_habits__summary.sql`
- `dbt/models/marts/mart_habit_performance.sql` — daily pivoted view (powers heatmap)
- `dbt/models/marts/mart_habit_streaks.sql` — current + longest streak per habit

After running the habits pipeline:
```bash
dbt run --select stg_habits__log stg_habits__summary mart_habit_performance mart_habit_streaks
```

---

### goals/2026.yaml
Habit `source` fields updated from `pixela` → `local`.

---

### pyproject.toml
Added `dlt[duckdb]>=1.4.0`, `python-dotenv`, and `requests` as explicit deps.

Install with:
```bash
uv sync
# or
pip install -e ".[dev]"
```

---

## First-run checklist

```bash
# 1. Install new deps
uv sync

# 2. Log today's habits in the dashboard (or they'll just be empty)
streamlit run app/Home.py

# 3. Run pipelines (Strava needs tokens from strava_auth.py first)
python run_pipelines.py

# 4. Run dbt
dbt run

# 5. Open dashboard
streamlit run app/Home.py
```
