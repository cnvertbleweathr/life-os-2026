"""
Life OS — Home page / Daily Digest.

First page opened. Shows today's events, next 7 days, next 30 days,
and an AI-generated digest that flags risks, conflicts, and things
you shouldn't forget.
"""

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
EVENTS_CSV = ROOT / "data" / "calendar" / "processed" / f"events_clean_2026.csv"
DB_PATH = str(ROOT / "data" / "warehouse" / "lifeos.duckdb")

st.set_page_config(
    page_title="Life OS",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🧭 Life OS")
st.caption(f"{date.today().strftime('%A, %B %d, %Y')}")


@st.cache_data(ttl=300)
def load_events() -> pd.DataFrame | None:
    if not EVENTS_CSV.exists():
        return None
    df = pd.read_csv(EVENTS_CSV)
    df["summary"] = df["summary"].fillna("").astype(str)
    df["description"] = df["description"].fillna("").astype(str)
    df["location"] = df["location"].fillna("").astype(str)

    def parse_dt(s):
        if not isinstance(s, str) or not s.strip():
            return pd.NaT
        try:
            from dateutil.parser import isoparse
            dt = isoparse(s.strip())
            return dt.date() if hasattr(dt, "date") else dt
        except Exception:
            return pd.NaT

    df["start_date"] = df["start"].apply(parse_dt)
    df = df.dropna(subset=["start_date"])
    return df


def classify_event(summary: str) -> tuple[str, str]:
    s = summary.lower()
    if any(w in s for w in ["birthday", "bday", "b-day"]):
        return "🎂", "birthday"
    if any(w in s for w in ["interview", "hiring", "recruiter", "offer"]):
        return "💼", "interview"
    if any(w in s for w in ["flight", "travel", "trip", "hotel", "airbnb", "depart", "arrive", "airport"]):
        return "✈️", "travel"
    if any(w in s for w in ["doctor", "dentist", "appointment", "dr.", "clinic", "therapy", "medical"]):
        return "🏥", "appointment"
    if any(w in s for w in ["date night", "anniversary", "dinner"]):
        return "❤️", "personal"
    if any(w in s for w in ["deadline", "due", "submit", "review", "presentation"]):
        return "⚠️", "deadline"
    if any(w in s for w in ["crossfit", "gym", "workout", "run", "wod"]):
        return "💪", "fitness"
    if any(w in s for w in ["holiday", "vacation", "pto", "off"]):
        return "🏖️", "time off"
    return "📅", "event"


events = load_events()
today = date.today()

if events is None:
    st.warning("No calendar data. Run `python scripts/daily_sync.py --only calendar`.")
    events = pd.DataFrame()

today_events = events[events["start_date"] == today] if not events.empty else pd.DataFrame()
week_events = events[
    (events["start_date"] > today) & (events["start_date"] <= today + timedelta(days=7))
] if not events.empty else pd.DataFrame()
month_events = events[
    (events["start_date"] > today + timedelta(days=7)) & (events["start_date"] <= today + timedelta(days=30))
] if not events.empty else pd.DataFrame()

# ---------------------------------------------------------------------------
# AI Digest
# ---------------------------------------------------------------------------

st.subheader("🤖 Daily Digest")

def build_event_list(df: pd.DataFrame, limit=40) -> str:
    lines = []
    for _, row in df.head(limit).iterrows():
        lines.append(f"- {row['start_date']} | {row['summary']}" + (f" @ {row['location']}" if row['location'] else ""))
    return "\n".join(lines) if lines else "None"

upcoming_text = build_event_list(
    events[events["start_date"] >= today].sort_values("start_date")
)

digest_prompt = f"""You are a sharp personal assistant reviewing someone's calendar for the next 30 days.
Today is {today.strftime('%A, %B %d, %Y')}.

Here are their upcoming events:
{upcoming_text}

Give a concise daily digest in bullet points. Cover:
- Anything happening TODAY
- Key things in the next 7 days to be aware of
- Anything in the next 30 days that needs prep or attention (birthdays to remember, travel, deadlines, conflicts)
- Any risks or things they might be about to screw up

Be direct and specific. Use the actual event names. Flag birthdays, interviews, travel, and back-to-back conflicts.
No preamble. Just bullets. Max 15 bullets total."""

if not events.empty:
    if "digest_cache" not in st.session_state:
        st.session_state.digest_cache = None
        st.session_state.digest_date = None

    if st.session_state.digest_date != str(today):
        st.session_state.digest_cache = None

    col_refresh, _ = st.columns([1, 4])
    with col_refresh:
        refresh = st.button("🔄 Regenerate", use_container_width=True)

    if refresh or st.session_state.digest_cache is None:
        with st.spinner("Generating digest..."):
            try:
                import requests
                response = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
                    },
                    json={
                        "model": "gpt-4o",
                        "max_tokens": 1000,
                        "messages": [{"role": "user", "content": digest_prompt}],
                    },
                    timeout=30,
                )
                data = response.json()
                digest_text = data["choices"][0]["message"]["content"]
                st.session_state.digest_cache = digest_text
                st.session_state.digest_date = str(today)
            except Exception as e:
                st.session_state.digest_cache = f"_Could not generate digest: {e}_"

    if st.session_state.digest_cache:
        st.markdown(st.session_state.digest_cache)
else:
    st.info("No events loaded — digest unavailable.")

st.divider()

# ---------------------------------------------------------------------------
# Today
# ---------------------------------------------------------------------------

st.subheader(f"📅 Today — {today.strftime('%A, %b %d')}")

if today_events.empty:
    st.caption("Nothing scheduled today.")
else:
    for _, row in today_events.iterrows():
        emoji, cat = classify_event(row["summary"])
        time_str = ""
        if not row.get("all_day", True):
            try:
                from dateutil.parser import isoparse
                dt = isoparse(str(row["start"]))
                time_str = f" · {dt.strftime('%I:%M %p').lstrip('0')}"
            except Exception:
                pass
        loc_str = f" · 📍{row['location']}" if row["location"] else ""
        st.markdown(f"{emoji} **{row['summary']}**{time_str}{loc_str}")

st.divider()

# ---------------------------------------------------------------------------
# Next 7 days
# ---------------------------------------------------------------------------

st.subheader("📆 Next 7 Days")

if week_events.empty:
    st.caption("Nothing coming up this week.")
else:
    current_date = None
    for _, row in week_events.sort_values("start_date").iterrows():
        if row["start_date"] != current_date:
            current_date = row["start_date"]
            day_label = pd.Timestamp(current_date).strftime("%A, %b %d")
            st.markdown(f"**{day_label}**")
        emoji, cat = classify_event(row["summary"])
        loc_str = f" · 📍{row['location']}" if row["location"] else ""
        st.markdown(f"&nbsp;&nbsp;&nbsp;{emoji} {row['summary']}{loc_str}")

st.divider()

# ---------------------------------------------------------------------------
# Next 30 days
# ---------------------------------------------------------------------------

st.subheader("🗓️ Next 30 Days")

if month_events.empty:
    st.caption("Nothing on the horizon.")
else:
    month_events = month_events.copy()
    month_events["week_start"] = month_events["start_date"].apply(
        lambda d: pd.Timestamp(d) - timedelta(days=pd.Timestamp(d).weekday())
    )

    for week, group in month_events.groupby("week_start"):
        week_label = pd.Timestamp(week).strftime("Week of %b %d")
        with st.expander(week_label, expanded=True):
            for _, row in group.sort_values("start_date").iterrows():
                emoji, cat = classify_event(row["summary"])
                day = pd.Timestamp(row["start_date"]).strftime("%a %d")
                loc_str = f" · 📍{row['location']}" if row["location"] else ""
                st.markdown(f"{emoji} **{day}** — {row['summary']}{loc_str}")

st.divider()

# ---------------------------------------------------------------------------
# Goals scoreboard
# ---------------------------------------------------------------------------

st.subheader("🎯 Goals · 2026")

try:
    import duckdb
    con = duckdb.connect(DB_PATH, read_only=True)
    goal_progress = con.execute("""
        SELECT domain, goal_key, target_numeric, current_value, progress_percent
        FROM main_marts.mart_goal_progress
        WHERE progress_percent IS NOT NULL
        ORDER BY domain, progress_percent DESC
    """).df()
    con.close()

    if not goal_progress.empty:
        domains = goal_progress["domain"].unique()
        cols = st.columns(len(domains))
        for col, domain in zip(cols, domains):
            with col:
                st.markdown(f"**{domain.title()}**")
                subset = goal_progress[goal_progress["domain"] == domain]
                for _, row in subset.iterrows():
                    label = row["goal_key"].replace("_", " ").title()
                    pct = float(row["progress_percent"])
                    st.progress(min(int(pct), 100), text=f"{label} {pct:.0f}%")
except Exception:
    st.info("Run `dbt run` to populate goal progress.")

st.sidebar.success("Navigate using the pages above.")