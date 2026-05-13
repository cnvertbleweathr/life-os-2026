"""
Fitness page — running (Strava) + CrossFit (SugarWOD).
"""

import streamlit as st
import duckdb
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = str(ROOT / "data" / "warehouse" / "lifeos.duckdb")

st.set_page_config(page_title="Fitness · Life OS", page_icon="💪", layout="wide")
st.title("💪 Fitness")
st.caption("Running · CrossFit · 2026")


def safe_query(sql: str, params=None) -> pd.DataFrame | None:
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        df = con.execute(sql, params or []).df()
        con.close()
        return df
    except Exception as e:
        st.warning(f"Query unavailable: {e}")
        return None


# ---------------------------------------------------------------------------
# Running summary
# ---------------------------------------------------------------------------

st.subheader("🏃 Running")

running = safe_query("""
    SELECT * FROM strava.running_summary WHERE year = 2026
""")

if running is not None and not running.empty:
    r = running.iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Miles YTD", f"{r['miles_total']:.1f}", f"goal: {r['miles_goal']:.0f}")
    c2.metric("Runs", int(r["runs_count"]))
    c3.metric("Miles/Week", f"{r['miles_per_week']:.1f}", f"need: {r['required_miles_per_week']:.1f}")
    if r.get("avg_pace_min_per_mile"):
        mins = int(r["avg_pace_min_per_mile"])
        secs = int((r["avg_pace_min_per_mile"] - mins) * 60)
        c4.metric("Avg Pace", f"{mins}:{secs:02d}/mi")

    pct = float(r["miles_progress_pct"])
    st.progress(min(int(pct), 100), text=f"{pct:.1f}% of annual goal")
else:
    st.info("No running data. Run `python run_pipelines.py --only strava`.")

# Weekly mileage chart
weekly = safe_query("""
    SELECT
        strftime(start_date, '%Y-W%W') as week,
        sum(distance_miles) as miles,
        count(*) as runs
    FROM strava.activities
    WHERE is_run = true AND year = 2026
    GROUP BY week
    ORDER BY week
""")

if weekly is not None and not weekly.empty:
    st.markdown("**Weekly Miles**")
    st.bar_chart(weekly.set_index("week")["miles"], use_container_width=True)

# Recent runs
recent_runs = safe_query("""
    SELECT
        start_date::date as date,
        name,
        round(distance_miles, 2) as miles,
        printf('%d:%02d', cast(moving_time_s/60 as int), cast(moving_time_s%60 as int)) as duration,
        round(moving_time_s / 60.0 / nullif(distance_miles, 0), 2) as pace_min_per_mile
    FROM strava.activities
    WHERE is_run = true AND year = 2026
    ORDER BY start_date DESC
    LIMIT 10
""")

if recent_runs is not None and not recent_runs.empty:
    st.markdown("**Recent Runs**")
    st.dataframe(recent_runs, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# CrossFit / SugarWOD
# ---------------------------------------------------------------------------

st.divider()
st.subheader("🏋️ CrossFit")

fitness_summary = safe_query("""
    SELECT * FROM main_marts.mart_goal_progress
    WHERE domain = 'fitness' AND goal_key = 'crossfit_classes'
""")

if fitness_summary is not None and not fitness_summary.empty:
    row = fitness_summary.iloc[0]
    current = row.get("current_value") or 0
    target = row.get("target_numeric") or 160
    pct = float(row.get("progress_percent") or 0)
    c1, c2 = st.columns(2)
    c1.metric("Classes YTD", int(current), f"goal: {int(target)}")
    c2.metric("Progress", f"{pct:.1f}%")
    st.progress(min(int(pct), 100))
else:
    st.info("No CrossFit data. Import SugarWOD CSV via `scripts/import_sugarwod_csv.py`.")
