"""
Habits page — checkboxes left, motivational quote right. History below.
"""

import json
import random
import sys
import requests as _req
from datetime import datetime, date
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
from ons_theme import apply_theme
apply_theme()

LOG_PATH = ROOT / "data" / "habits" / "habits_log.jsonl"
DB_PATH  = str(ROOT / "data" / "warehouse" / "ons.duckdb")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="Habits · ONS", page_icon="✅", layout="wide")
st.title("✅ Habits")
st.caption("Check off what you did today. No app. No BS.")

HABITS: dict[str, str] = {
    "meditation":          "🧘 Meditation",
    "pushups_100":         "💪 100 Pushups",
    "nonfiction_pages_10": "📖 10 Nonfiction Pages",
    "fiction_pages_10":    "📚 10 Fiction Pages",
}

# Fallback quotes — rotates daily by day-of-year so it's consistent within a day
FALLBACK_QUOTES = [
    ("The secret of getting ahead is getting started.", "Mark Twain"),
    ("It does not matter how slowly you go as long as you do not stop.", "Confucius"),
    ("Our greatest glory is not in never falling, but in rising every time we fall.", "Confucius"),
    ("Believe you can and you're halfway there.", "Theodore Roosevelt"),
    ("You miss 100% of the shots you don't take.", "Wayne Gretzky"),
    ("Whether you think you can or you think you can't, you're right.", "Henry Ford"),
    ("The only way to do great work is to love what you do.", "Steve Jobs"),
    ("In the middle of every difficulty lies opportunity.", "Albert Einstein"),
    ("It's not whether you get knocked down, it's whether you get up.", "Vince Lombardi"),
    ("Success is not final, failure is not fatal: it is the courage to continue that counts.", "Winston Churchill"),
    ("Don't watch the clock; do what it does. Keep going.", "Sam Levenson"),
    ("Hard work beats talent when talent doesn't work hard.", "Tim Notke"),
    ("I am not a product of my circumstances. I am a product of my decisions.", "Stephen Covey"),
    ("Either you run the day or the day runs you.", "Jim Rohn"),
    ("The man who has confidence in himself gains the confidence of others.", "Hasidic Proverb"),
    ("You don't have to be great to start, but you have to start to be great.", "Zig Ziglar"),
    ("Motivation is what gets you started. Habit is what keeps you going.", "Jim Ryun"),
    ("Champions keep playing until they get it right.", "Billie Jean King"),
    ("Action is the foundational key to all success.", "Pablo Picasso"),
    ("The difference between ordinary and extraordinary is that little extra.", "Jimmy Johnson"),
    ("Small daily improvements are the key to staggering long-term results.", "Robin Sharma"),
    ("We are what we repeatedly do. Excellence, then, is not an act, but a habit.", "Aristotle"),
    ("Do one thing every day that scares you.", "Eleanor Roosevelt"),
    ("Start where you are. Use what you have. Do what you can.", "Arthur Ashe"),
    ("Discipline is the bridge between goals and accomplishment.", "Jim Rohn"),
    ("Energy and persistence conquer all things.", "Benjamin Franklin"),
    ("The only limit to our realization of tomorrow is our doubts of today.", "Franklin D. Roosevelt"),
    ("Strength does not come from physical capacity. It comes from an indomitable will.", "Mahatma Gandhi"),
    ("Tough times never last, but tough people do.", "Robert H. Schuller"),
    ("Push yourself, because no one else is going to do it for you.", "Anonymous"),
    ("Wake up with determination. Go to bed with satisfaction.", "Anonymous"),
    ("You've got to get up every morning with determination if you're going to go to bed with satisfaction.", "George Lorimer"),
]


@st.cache_data(ttl=86400)
def get_quote() -> tuple[str, str]:
    """Fetch from zenquotes; fall back to local list."""
    try:
        r = _req.get("https://zenquotes.io/api/today", timeout=8)
        if r.status_code == 200:
            data = r.json()
            if data:
                return data[0]["q"], data[0]["a"]
    except Exception:
        pass
    # Deterministic daily rotation through fallback list
    idx = date.today().timetuple().tm_yday % len(FALLBACK_QUOTES)
    return FALLBACK_QUOTES[idx]


today_str = date.today().isoformat()


def load_today() -> dict:
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
    entry = {
        "date": today_str,
        "logged_at": datetime.now().isoformat(timespec="seconds"),
        **values,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def safe_query(sql: str) -> pd.DataFrame | None:
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        df  = con.execute(sql).df()
        con.close()
        return df
    except Exception:
        return None


existing   = load_today()
done_today = sum(bool(existing.get(k, False)) for k in HABITS)

# ─────────────────────────────────────────────────────────────────────────────
# ROW 1: Checkboxes | Quote
# ─────────────────────────────────────────────────────────────────────────────

st.subheader(f"Today — {today_str}")

col_habits, col_quote = st.columns(2, gap="large")

with col_habits:
    with st.form("habit_form"):
        checked: dict[str, bool] = {}
        for i, (key, label) in enumerate(HABITS.items()):
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

    existing   = load_today()
    done_today = sum(bool(existing.get(k, False)) for k in HABITS)

    if done_today == len(HABITS):
        st.success("🔥 Perfect day — all habits done!", icon=":material/check_circle:")
    else:
        # Mini progress bar
        pct = int(done_today / len(HABITS) * 100)
        st.progress(pct, text=f"{done_today}/{len(HABITS)} done today")

with col_quote:
    quote_text, quote_author = get_quote()
    st.markdown(
        f"<div style='background:#373D39;border:1px solid #434A45;"
        f"border-left:4px solid #0B5324;border-radius:6px;"
        f"padding:1.8rem 1.6rem;height:100%;box-sizing:border-box;"
        f"display:flex;flex-direction:column;justify-content:center'>"
        f"<div style='font-size:1.05rem;line-height:1.65;color:#F5EFEB;"
        f"font-weight:400;font-style:italic;margin-bottom:1rem'>"
        f"&ldquo;{quote_text}&rdquo;</div>"
        f"<div style='font-size:0.75rem;font-weight:600;letter-spacing:1px;"
        f"text-transform:uppercase;color:#A9B2AC'>— {quote_author}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# STREAKS
# ─────────────────────────────────────────────────────────────────────────────

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
                st.metric(label=label, value=f"{current} days",
                          delta=f"best: {longest}", delta_color="off", border=True)

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# HISTORY
# ─────────────────────────────────────────────────────────────────────────────

st.subheader("📅 History")

performance = safe_query("""
    SELECT log_date, meditation, pushups_100, nonfiction_pages_10, fiction_pages_10,
           habits_completed_count, daily_completion_pct
    FROM main_marts.mart_habit_performance
    WHERE log_date >= (current_date - interval 60 day)::varchar
    ORDER BY log_date DESC
""")

if performance is not None and not performance.empty:
    st.markdown("**Last 60 Days**")
    display_df = performance.rename(columns={
        "log_date": "Date", "meditation": "🧘", "pushups_100": "💪",
        "nonfiction_pages_10": "📖", "fiction_pages_10": "📚",
        "habits_completed_count": "Done", "daily_completion_pct": "% Complete",
    })
    st.dataframe(
        display_df, use_container_width=True, hide_index=True,
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
    st.caption("No history yet. Log a few days, run the habits pipeline, then `dbt run`.")

# YTD summary
summary = safe_query("""
    SELECT habit, done_days, days_observed, completion_rate_pct
    FROM habits.habit_summary
    WHERE year = year(current_date)
""")

if summary is not None and not summary.empty:
    st.subheader("📊 YTD Completion Rates")
    for _, row in summary.iterrows():
        habit_key = row["habit"]
        label = HABITS.get(habit_key, habit_key)
        pct   = float(row["completion_rate_pct"])
        done  = int(row["done_days"])
        obs   = int(row["days_observed"])
        st.progress(min(int(pct), 100), text=f"{label} — {done}/{obs} days ({pct:.1f}%)")

with st.expander("ℹ️ How this works", expanded=False):
    st.markdown("""
    Checkboxes write to **`data/habits/habits_log.jsonl`** (local, append-only).
    Run `python run_pipelines.py --only habits && dbt run` or let daily sync handle it.
    """)
