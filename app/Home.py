"""
Life OS — Home page / Daily Digest.

First page opened. Shows:
  - Today's streams (your teams first, top 5 nationally, all popular)
  - AI-generated daily digest from calendar
  - Today / next 7 days / next 30 days calendar view
  - Goals scoreboard
"""

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
EVENTS_CSV   = ROOT / "data" / "calendar" / "processed" / "events_clean_2026.csv"
STREAMS_PATH = ROOT / "data" / "streams" / "today.json"
DB_PATH      = str(ROOT / "data" / "warehouse" / "lifeos.duckdb")

st.set_page_config(
    page_title="Life OS",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🧭 Life OS")
st.caption(f"{date.today().strftime('%A, %B %d, %Y')}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def load_events() -> pd.DataFrame | None:
    if not EVENTS_CSV.exists():
        return None
    df = pd.read_csv(EVENTS_CSV)
    df["summary"]     = df["summary"].fillna("").astype(str)
    df["description"] = df["description"].fillna("").astype(str)
    df["location"]    = df["location"].fillna("").astype(str)

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
    return df.dropna(subset=["start_date"])


@st.cache_data(ttl=300)
def load_streams() -> dict | None:
    if not STREAMS_PATH.exists():
        return None
    try:
        return json.loads(STREAMS_PATH.read_text())
    except Exception:
        return None


def classify_event(summary: str) -> str:
    s = summary.lower()
    if any(w in s for w in ["birthday", "bday", "b-day"]):      return "🎂"
    if any(w in s for w in ["interview", "hiring", "recruiter"]): return "💼"
    if any(w in s for w in ["flight", "travel", "trip", "hotel", "airport"]): return "✈️"
    if any(w in s for w in ["doctor", "dentist", "clinic", "therapy"]): return "🏥"
    if any(w in s for w in ["date night", "anniversary", "dinner"]): return "❤️"
    if any(w in s for w in ["deadline", "due", "submit", "presentation"]): return "⚠️"
    if any(w in s for w in ["crossfit", "gym", "workout", "wod"]): return "💪"
    if any(w in s for w in ["holiday", "vacation", "pto"]):      return "🏖️"
    return "📅"


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

events = load_events()
today  = date.today()

if events is None:
    events = pd.DataFrame()

today_events = events[events["start_date"] == today] if not events.empty else pd.DataFrame()
week_events  = events[
    (events["start_date"] > today) & (events["start_date"] <= today + timedelta(days=7))
] if not events.empty else pd.DataFrame()
month_events = events[
    (events["start_date"] > today + timedelta(days=7)) & (events["start_date"] <= today + timedelta(days=30))
] if not events.empty else pd.DataFrame()


# ---------------------------------------------------------------------------
# 1. Streams
# ---------------------------------------------------------------------------

st.subheader("📺 Today's Streams")

streams_data = load_streams()

if streams_data is None:
    st.info("No stream data yet. Run `python scripts/fetch_streams.py` or `python scripts/daily_sync.py`.")
else:
    fetched_at = streams_data.get("fetched_at", "")
    if fetched_at:
        try:
            ft = datetime.fromisoformat(fetched_at).astimezone()
            st.caption(f"Updated {ft.strftime('%I:%M %p')}")
        except Exception:
            pass

    my_teams = streams_data.get("my_teams", [])
    top5     = streams_data.get("top5", [])
    popular  = streams_data.get("popular", [])

    # Your teams
    st.markdown("**🏆 Your Teams**")
    if my_teams:
        cols = st.columns(min(len(my_teams), 3))
        for i, match in enumerate(my_teams):
            with cols[i % 3]:
                live_badge = " 🔴" if match.get("is_live") else ""
                time_str   = match.get("kickoff_local", "TBD")
                st.markdown(
                    f"**{match.get('team_label', '')}**{live_badge}  \n"
                    f"{match.get('title', '')}  \n"
                    f"{'🔴 LIVE' if match.get('is_live') else time_str}  \n"
                    f"[▶ Watch]({match.get('watch_url', '')})"
                )
    else:
        st.caption("None of your teams are playing today.")

    # Top 5 nationally prominent
    if top5:
        st.markdown("**🔥 Top 5 Today**")
        for match in top5:
            live_badge = " 🔴 LIVE" if match.get("is_live") else f" · {match.get('kickoff_local', '')}"
            cat = match.get("category", "").replace("-", " ").title()
            st.markdown(
                f"{cat} — **{match.get('title', '')}**{live_badge} "
                f"[▶ Watch]({match.get('watch_url', '')})"
            )

    # All popular — collapsed
    if popular:
        with st.expander(f"🌍 All Popular Matches Today ({len(popular)})", expanded=False):
            for match in popular:
                live_badge = " 🔴 LIVE" if match.get("is_live") else f" · {match.get('kickoff_local', '')}"
                cat = match.get("category", "").replace("-", " ").title()
                st.markdown(
                    f"**{match.get('title', '')}** — {cat}{live_badge} "
                    f"[▶ Watch]({match.get('watch_url', '')})"
                )

# ---------------------------------------------------------------------------
# My artist show alerts
# ---------------------------------------------------------------------------

MY_SHOWS_PATH = ROOT / "data" / "shows" / "my_artist_shows.json"
if MY_SHOWS_PATH.exists():
    try:
        my_shows_data = json.loads(MY_SHOWS_PATH.read_text())
        my_shows_list = my_shows_data.get("shows", [])
        if my_shows_list:
            st.subheader("⭐ Your Artists Have Shows Coming Up")
            for show in my_shows_list[:5]:  # cap at 5 on home page
                ticket_link = f" · [🎟 Tickets]({show['event_url']})" if show.get("event_url") else ""
                st.success(
                    f"**{show['artist']}** — {show['title']}  \n"
                    f"📍 {show['venue']} · {show['date_str']} at {show['time_str']}{ticket_link}"
                )
            if len(my_shows_list) > 5:
                st.caption(f"+ {len(my_shows_list) - 5} more on the Shows page.")
    except Exception:
        pass

st.divider()

# ---------------------------------------------------------------------------
# 2. AI Daily Digest
# ---------------------------------------------------------------------------

st.subheader("🤖 Daily Digest")

def build_event_list(df: pd.DataFrame, limit: int = 40) -> str:
    lines = []
    for _, row in df.head(limit).iterrows():
        line = f"- {row['start_date']} | {row['summary']}"
        if row["location"]:
            line += f" @ {row['location']}"
        lines.append(line)
    return "\n".join(lines) if lines else "None"

upcoming_text = build_event_list(
    events[events["start_date"] >= today].sort_values("start_date")
) if not events.empty else "No calendar data available."

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

if "digest_cache" not in st.session_state:
    st.session_state.digest_cache = None
    st.session_state.digest_date  = None

if st.session_state.digest_date != str(today):
    st.session_state.digest_cache = None

col_refresh, _ = st.columns([1, 4])
with col_refresh:
    refresh = st.button("🔄 Regenerate", use_container_width=True)

if refresh or st.session_state.digest_cache is None:
    with st.spinner("Generating digest..."):
        try:
            import requests as _req
            response = _req.post(
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
            st.session_state.digest_cache = data["choices"][0]["message"]["content"]
            st.session_state.digest_date  = str(today)
        except Exception as e:
            st.session_state.digest_cache = f"_Could not generate digest: {e}_"

if st.session_state.digest_cache:
    st.markdown(st.session_state.digest_cache)

st.divider()

# ---------------------------------------------------------------------------
# 3. Today
# ---------------------------------------------------------------------------

st.subheader(f"📅 Today — {today.strftime('%A, %b %d')}")

if today_events.empty:
    st.caption("Nothing scheduled today.")
else:
    for _, row in today_events.iterrows():
        emoji = classify_event(row["summary"])
        time_str = ""
        if str(row.get("all_day", "True")).lower() != "true":
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
# 4. Next 7 days
# ---------------------------------------------------------------------------

st.subheader("📆 Next 7 Days")

if week_events.empty:
    st.caption("Nothing coming up this week.")
else:
    current_day = None
    for _, row in week_events.sort_values("start_date").iterrows():
        if row["start_date"] != current_day:
            current_day = row["start_date"]
            st.markdown(f"**{pd.Timestamp(current_day).strftime('%A, %b %d')}**")
        emoji   = classify_event(row["summary"])
        loc_str = f" · 📍{row['location']}" if row["location"] else ""
        st.markdown(f"&nbsp;&nbsp;&nbsp;{emoji} {row['summary']}{loc_str}")

st.divider()

# ---------------------------------------------------------------------------
# 5. Next 30 days
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
        with st.expander(pd.Timestamp(week).strftime("Week of %b %d"), expanded=True):
            for _, row in group.sort_values("start_date").iterrows():
                emoji   = classify_event(row["summary"])
                day     = pd.Timestamp(row["start_date"]).strftime("%a %d")
                loc_str = f" · 📍{row['location']}" if row["location"] else ""
                st.markdown(f"{emoji} **{day}** — {row['summary']}{loc_str}")

st.divider()

# ---------------------------------------------------------------------------
# 6. Goals scoreboard
# ---------------------------------------------------------------------------

st.subheader("🎯 Goals · 2026")

try:
    import duckdb
    con = duckdb.connect(DB_PATH, read_only=True)
    goal_progress = con.execute("""
        SELECT domain, goal_key, current_value, target_numeric, progress_percent
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
                for _, row in goal_progress[goal_progress["domain"] == domain].iterrows():
                    label = row["goal_key"].replace("_", " ").title()
                    pct   = float(row["progress_percent"])
                    st.progress(min(int(pct), 100), text=f"{label} {pct:.0f}%")
except Exception:
    st.info("Run `dbt run` to populate goal progress.")

st.sidebar.success("Navigate using the pages above.")
