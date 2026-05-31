"""
Habits page — log today's habits via checkboxes, view history.

Writing to data/habits/habits_log.jsonl (append-only JSONL).
Run `python run_pipelines.py --only habits` to push into DuckDB.
"""

import json
import streamlit as st
import duckdb
import pandas as pd
from datetime import datetime, date
from pathlib import Path

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))
from ons_theme import apply_theme
apply_theme()

ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = ROOT / "data" / "habits" / "habits_log.jsonl"
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="Habits · Operating Narcisystem", page_icon="✅", layout="wide")

st.title("✅ Habits")
st.caption("Check off what you did today. No app. No BS.")

# ---------------------------------------------------------------------------
# Habit config
# ---------------------------------------------------------------------------

HABITS: dict[str, str] = {
    "meditation": "🧘 Meditation",
    "pushups_100": "💪 100 Pushups",
    "nonfiction_pages_10": "📖 10 Nonfiction Pages",
    "fiction_pages_10": "📚 10 Fiction Pages",
}

# ---------------------------------------------------------------------------
# Load today's existing log entry (if any)
# ---------------------------------------------------------------------------

today_str = date.today().isoformat()  # YYYY-MM-DD


def load_today() -> dict:
    """Return the most recent log entry for today, or empty dict."""
    if not LOG_PATH.exists():
        return {}
    with LOG_PATH.open("r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]
    for line in reversed(lines):
        try:
            row = json.loads(line)
            if row.get("date") == today_str:
                return row
        except json.JSONDecodeError:
            continue
    return {}


def save_today(values: dict[str, bool]) -> None:
    """Append (or overwrite-by-append) today's entry."""
    entry = {
        "date": today_str,
        "logged_at": datetime.now().isoformat(timespec="seconds"),
        **values,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Today's log form
# ---------------------------------------------------------------------------

existing = load_today()

st.subheader(f"Today — {today_str}")

with st.form("habit_form"):
    checked: dict[str, bool] = {}
    cols = st.columns(2)
    for i, (key, label) in enumerate(HABITS.items()):
        with cols[i % 2]:
            checked[key] = st.checkbox(
                label,
                value=bool(existing.get(key, False)),
                key=f"habit_{key}",
            )

    submitted = st.form_submit_button("💾 Save", type="primary", use_container_width=True)
    if submitted:
        save_today(checked)
        done_count = sum(checked.values())
        st.success(f"Saved! {done_count}/{len(HABITS)} habits completed today.")
        st.rerun()

# Re-read after potential save
existing = load_today()
done_today = sum(bool(existing.get(k, False)) for k in HABITS)

# Quick status pills
if done_today == len(HABITS):
    st.success("🔥 Perfect day — all habits done!")
elif done_today > 0:
    st.info(f"{done_today}/{len(HABITS)} done today")
else:
    st.warning("Nothing logged yet today.")

# ---------------------------------------------------------------------------
# Pipeline reminder
# ---------------------------------------------------------------------------

with st.expander("ℹ️ How this works", expanded=False):
    st.markdown("""
    Checkboxes write to **`data/habits/habits_log.jsonl`** (local, append-only).

    To push into DuckDB and update dbt marts, run:
    ```bash
    python run_pipelines.py --only habits
    dbt run --select mart_habit_performance mart_habit_streaks
    ```
    Or just let the daily sync handle it.
    """)

# ---------------------------------------------------------------------------
# History from DuckDB (if available)
# ---------------------------------------------------------------------------

st.divider()
st.subheader("📅 History")


def safe_query(sql: str, params=None) -> pd.DataFrame | None:
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        df = con.execute(sql, params or []).df()
        con.close()
        return df
    except Exception:
        return None


# Streaks
streaks = safe_query("SELECT * FROM main_marts.mart_habit_streaks ORDER BY habit")
if streaks is not None and not streaks.empty:
    st.markdown("**Current Streaks**")
    scols = st.columns(len(HABITS))
    for col, (key, label) in zip(scols, HABITS.items()):
        row = streaks[streaks["habit"] == key]
        if not row.empty:
            current = int(row.iloc[0]["current_streak"])
            longest = int(row.iloc[0]["longest_streak"])
            with col:
                st.metric(
                    label=label,
                    value=f"{current} days",
                    delta=f"best: {longest}",
                    delta_color="off",
                )

st.divider()

# Completion heatmap (last 60 days)
performance = safe_query("""
    SELECT log_date, meditation, pushups_100, nonfiction_pages_10, fiction_pages_10,
           habits_completed_count, daily_completion_pct
    FROM main_marts.mart_habit_performance
    WHERE log_date >= (current_date - interval 60 day)::varchar
    ORDER BY log_date DESC
""")

if performance is not None and not performance.empty:
    st.markdown("**Last 60 Days**")

    # Rename columns for display
    display_df = performance.rename(columns={
        "log_date": "Date",
        "meditation": "🧘",
        "pushups_100": "💪",
        "nonfiction_pages_10": "📖",
        "fiction_pages_10": "📚",
        "habits_completed_count": "Done",
        "daily_completion_pct": "% Complete",
    })

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "🧘": st.column_config.CheckboxColumn(disabled=True),
            "💪": st.column_config.CheckboxColumn(disabled=True),
            "📖": st.column_config.CheckboxColumn(disabled=True),
            "📚": st.column_config.CheckboxColumn(disabled=True),
            "% Complete": st.column_config.ProgressColumn(
                min_value=0, max_value=100, format="%.0f%%"
            ),
        },
    )
else:
    st.info(
        "No history yet. Log a few days, run the habits pipeline, then `dbt run`. "
        "History will appear here."
    )

# ---------------------------------------------------------------------------
# YTD summary
# ---------------------------------------------------------------------------

summary = safe_query("""
    SELECT habit, done_days, days_observed, completion_rate_pct
    FROM habits.habit_summary
    WHERE year = year(current_date)
""")

if summary is not None and not summary.empty:
    st.divider()
    st.subheader("📊 YTD Completion Rates")

    for _, row in summary.iterrows():
        habit_key = row["habit"]
        label = HABITS.get(habit_key, habit_key)
        pct = float(row["completion_rate_pct"])
        done = int(row["done_days"])
        observed = int(row["days_observed"])
        st.progress(
            min(int(pct), 100),
            text=f"{label} — {done}/{observed} days ({pct:.1f}%)",
        )
