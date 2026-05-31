"""
ONS — Home page.

Layout:
  Sidebar: logo (top) + news ticker (US/Sports/Business/Tech/Science)
  Main: header | streams | digest | calendar | goals
"""

import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import requests as _req
import streamlit as st
from dotenv import load_dotenv

ROOT          = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

EVENTS_CSV    = ROOT / "data" / "calendar" / "processed" / "events_clean_2026.csv"
STREAMS_PATH  = ROOT / "data" / "streams" / "today.json"
MY_SHOWS_PATH = ROOT / "data" / "shows" / "my_artist_shows.json"
LOGO_PATH     = ROOT / "app" / "static" / "ons_logo.png"
DB_PATH       = str(ROOT / "data" / "warehouse" / "ons.duckdb")

sys.path.insert(0, str(ROOT / "app"))
from ons_theme import apply_theme, section_header

st.set_page_config(
    page_title="ONS",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()

today = date.today()
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

NEWS_CATEGORIES = [
    {"label": "🇺🇸 US News",  "category": "general",  "country": "us", "q": None},
    {"label": "🏟️ Sports",    "category": "sports",   "country": "us", "q": None},
    {"label": "💼 Business",  "category": "business", "country": "us", "q": None},
    {"label": "💻 Tech",      "category": "technology","country": "us", "q": None},
    {"label": "🔬 Science",   "category": "science",  "country": "us", "q": None},
]


# ─────────────────────────────────────────────────────────────────────────────
# Data loaders
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=1800)
def fetch_news(category: str, country: str = "us") -> list[dict]:
    if not NEWS_API_KEY:
        return []
    try:
        r = _req.get(
            "https://newsapi.org/v2/top-headlines",
            params={"category": category, "country": country,
                    "apiKey": NEWS_API_KEY, "pageSize": 8},
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("articles", [])
    except Exception:
        return []


@st.cache_data(ttl=300)
def load_events() -> pd.DataFrame:
    if not EVENTS_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(EVENTS_CSV)
    df["summary"]  = df["summary"].fillna("").astype(str)
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
    return df.dropna(subset=["start_date"])


@st.cache_data(ttl=300)
def load_streams() -> dict:
    if not STREAMS_PATH.exists():
        return {}
    try:
        return json.loads(STREAMS_PATH.read_text())
    except Exception:
        return {}


def classify_event(s: str) -> str:
    s = s.lower()
    if any(w in s for w in ["birthday", "bday"]):            return "🎂"
    if any(w in s for w in ["interview", "hiring"]):         return "💼"
    if any(w in s for w in ["flight", "travel", "airport"]): return "✈️"
    if any(w in s for w in ["doctor", "dentist", "clinic"]): return "🏥"
    if any(w in s for w in ["date night", "anniversary"]):   return "❤️"
    if any(w in s for w in ["deadline", "due", "submit"]):   return "⚠️"
    if any(w in s for w in ["crossfit", "gym", "wod"]):      return "💪"
    if any(w in s for w in ["vacation", "pto"]):             return "🏖️"
    return "📅"


# ─────────────────────────────────────────────────────────────────────────────
# Load data
# ─────────────────────────────────────────────────────────────────────────────

events       = load_events()
streams_data = load_streams()

today_events = events[events["start_date"] == today] if not events.empty else pd.DataFrame()
week_events  = events[
    (events["start_date"] > today) &
    (events["start_date"] <= today + timedelta(days=7))
] if not events.empty else pd.DataFrame()
month_events = events[
    (events["start_date"] > today + timedelta(days=7)) &
    (events["start_date"] <= today + timedelta(days=30))
] if not events.empty else pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR — Logo + News Ticker
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.caption(today.strftime("%A, %B %d, %Y"))
    st.divider()
    
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), use_container_width=True)
    
    st.divider()
    # ... rest of sidebar

    # News ticker — tab per category
    if NEWS_API_KEY:
        st.markdown(
            "<div style='font-family:Josefin Sans,sans-serif;font-size:0.65rem;"
            "letter-spacing:4px;color:#a09880;text-transform:uppercase;"
            "margin-bottom:0.5rem'>📡 NEWS TICKER</div>",
            unsafe_allow_html=True,
        )

        selected_cat = st.selectbox(
            "Category",
            options=[c["label"] for c in NEWS_CATEGORIES],
            label_visibility="collapsed",
        )

        cat_cfg = next(c for c in NEWS_CATEGORIES if c["label"] == selected_cat)
        articles = fetch_news(cat_cfg["category"], cat_cfg["country"])

        if articles:
            for article in articles:
                title  = article.get("title", "")
                url    = article.get("url", "")
                source = article.get("source", {}).get("name", "")
                pub    = article.get("publishedAt", "")
                pub_fmt = ""
                if pub:
                    try:
                        pub_fmt = datetime.fromisoformat(
                            pub.replace("Z", "+00:00")
                        ).astimezone().strftime("%-I:%M %p")
                    except Exception:
                        pub_fmt = pub[:10]

                if title and "[Removed]" not in title:
                    st.markdown(
                        f"<div style='border-left:2px solid #c8501a;"
                        f"padding:0.4rem 0.6rem;margin:0.4rem 0;"
                        f"background:#0a2a36'>"
                        f"<a href='{url}' target='_blank' style='color:#e8dcc8;"
                        f"text-decoration:none;font-size:0.78rem;line-height:1.4'>"
                        f"{title}</a>"
                        f"<div style='color:#a09880;font-size:0.65rem;"
                        f"margin-top:0.2rem'>{source} · {pub_fmt}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
        else:
            st.caption("No headlines available.")
    else:
        st.caption("Add NEWS_API_KEY to .env for news ticker.")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — Header
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(
    f"<h1 style='margin-bottom:0'>🧭 Operating Narcisystem</h1>"
    f"<p style='color:#a09880;font-family:Josefin Sans,sans-serif;"
    f"letter-spacing:4px;font-size:0.7rem;text-transform:uppercase;"
    f"margin-top:0.2rem'>{today.strftime('%A, %B %d, %Y')}</p>",
    unsafe_allow_html=True,
)

st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — Streams
# ─────────────────────────────────────────────────────────────────────────────

section_header("📺 Today's Streams")

my_teams = streams_data.get("my_teams", [])
top5     = streams_data.get("top5", [])
popular  = streams_data.get("popular", [])

if streams_data:
    fetched_at = streams_data.get("fetched_at", "")
    if fetched_at:
        try:
            ft = datetime.fromisoformat(fetched_at).astimezone()
            st.caption(f"Updated {ft.strftime('%I:%M %p')}")
        except Exception:
            pass

    col_teams, col_top5 = st.columns([1, 1], gap="large")

    with col_teams:
        st.markdown(
            "<div style='color:#ffcc44;font-family:Josefin Sans,sans-serif;"
            "font-size:0.7rem;letter-spacing:3px;text-transform:uppercase;"
            "margin-bottom:0.6rem'>🏆 Your Teams</div>",
            unsafe_allow_html=True,
        )
        if my_teams:
            for match in my_teams:
                live      = match.get("is_live")
                badge     = " 🔴 LIVE" if live else match.get("kickoff_local", "")
                st.markdown(
                    f"<div style='background:#0a2a36;border-left:2px solid #c8501a;"
                    f"padding:0.5rem 0.8rem;margin:0.3rem 0'>"
                    f"<div style='font-size:0.8rem'><b>{match.get('team_label','')}</b></div>"
                    f"<div style='font-size:0.75rem;color:#a09880'>{match.get('title','')}</div>"
                    f"<div style='font-size:0.72rem;color:#4db8d4;margin-top:0.2rem'>"
                    f"{badge} · <a href='{match.get('watch_url','')}' target='_blank' "
                    f"style='color:#4db8d4'>▶ Watch</a></div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No team games today.")

    with col_top5:
        st.markdown(
            "<div style='color:#ffcc44;font-family:Josefin Sans,sans-serif;"
            "font-size:0.7rem;letter-spacing:3px;text-transform:uppercase;"
            "margin-bottom:0.6rem'>🔥 Top 5 Today</div>",
            unsafe_allow_html=True,
        )
        if top5:
            for match in top5:
                live = " 🔴 LIVE" if match.get("is_live") else f" · {match.get('kickoff_local','')}"
                cat  = match.get("category","").replace("-"," ").title()
                st.markdown(
                    f"<div style='background:#0a2a36;border-left:2px solid #0e3347;"
                    f"padding:0.5rem 0.8rem;margin:0.3rem 0'>"
                    f"<div style='font-size:0.8rem'><b>{match.get('title','')}</b></div>"
                    f"<div style='font-size:0.72rem;color:#a09880'>{cat}{live}</div>"
                    f"<div style='margin-top:0.2rem'>"
                    f"<a href='{match.get('watch_url','')}' target='_blank' "
                    f"style='color:#4db8d4;font-size:0.72rem'>▶ Watch</a></div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    if popular:
        with st.expander(f"🌍 All Popular Matches Today ({len(popular)})", expanded=False):
            for match in popular:
                live = " 🔴 LIVE" if match.get("is_live") else f" · {match.get('kickoff_local','')}"
                cat  = match.get("category","").replace("-"," ").title()
                st.markdown(
                    f"**{match.get('title','')}** — {cat}{live} "
                    f"[▶ Watch]({match.get('watch_url','')})"
                )
else:
    st.caption("Run `python scripts/daily_sync.py` to populate streams.")

# Artist shows — compact strip below streams
if MY_SHOWS_PATH.exists():
    try:
        shows_data = json.loads(MY_SHOWS_PATH.read_text())
        shows_list = shows_data.get("shows", [])
        if shows_list:
            st.markdown(
                "<div style='color:#ffcc44;font-family:Josefin Sans,sans-serif;"
                "font-size:0.7rem;letter-spacing:3px;text-transform:uppercase;"
                "margin:0.8rem 0 0.4rem'>⭐ Your Artist Shows Coming Up</div>",
                unsafe_allow_html=True,
            )
            show_cols = st.columns(min(len(shows_list[:4]), 4), gap="small")
            for col, show in zip(show_cols, shows_list[:4]):
                with col:
                    ticket = f"[🎟 Tickets]({show['event_url']})" if show.get("event_url") else ""
                    st.markdown(
                        f"<div style='background:#0a2a36;border-top:2px solid #ffcc44;"
                        f"padding:0.5rem;font-size:0.75rem'>"
                        f"<b>{show['artist']}</b><br>"
                        f"<span style='color:#a09880;font-size:0.7rem'>{show['title']}</span><br>"
                        f"<span style='color:#4db8d4;font-size:0.68rem'>📍 {show['venue']}</span><br>"
                        f"<span style='color:#a09880;font-size:0.65rem'>{show['date_str']}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    if ticket:
                        st.markdown(ticket)
            if len(shows_list) > 4:
                st.caption(f"+ {len(shows_list)-4} more on the Shows page.")
    except Exception:
        pass

st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — AI Daily Digest
# ─────────────────────────────────────────────────────────────────────────────

section_header("🤖 Daily Digest")

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
) if not events.empty else "No calendar data."

digest_prompt = f"""You are a sharp personal assistant reviewing someone's calendar.
Today is {today.strftime('%A, %B %d, %Y')}.

Upcoming events:
{upcoming_text}

Concise bullet digest. Cover:
- Anything TODAY
- Key things next 7 days
- Next 30 days needing prep (birthdays, travel, deadlines)
- Risks / things about to be screwed up

Direct, specific, use actual event names. No preamble. Bullets only. Max 12."""

if "digest_cache" not in st.session_state:
    st.session_state.digest_cache = None
    st.session_state.digest_date  = None

if st.session_state.digest_date != str(today):
    st.session_state.digest_cache = None

col_btn, _ = st.columns([1, 5])
with col_btn:
    if st.button("🔄 Regenerate", use_container_width=True):
        st.session_state.digest_cache = None

if st.session_state.digest_cache is None:
    with st.spinner("Generating digest..."):
        try:
            resp = _req.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
                },
                json={
                    "model": "gpt-4o",
                    "max_tokens": 800,
                    "messages": [{"role": "user", "content": digest_prompt}],
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            st.session_state.digest_cache = data["choices"][0]["message"]["content"]
            st.session_state.digest_date  = str(today)
        except Exception as e:
            st.session_state.digest_cache = f"_Digest unavailable: {e}_"

if st.session_state.digest_cache:
    st.markdown(
        f"<div style='background:#0a2a36;border-left:3px solid #c8501a;"
        f"padding:1.2rem 1.5rem;margin-top:0.5rem;line-height:1.8'>"
        f"{st.session_state.digest_cache.replace(chr(10), '<br>')}"
        f"</div>",
        unsafe_allow_html=True,
    )

st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — Calendar (3 columns)
# ─────────────────────────────────────────────────────────────────────────────

section_header("📅 Calendar")

col_today, col_week, col_month = st.columns([1, 1, 1], gap="medium")

with col_today:
    st.markdown(
        f"<div style='color:#ffcc44;font-family:Josefin Sans,sans-serif;"
        f"font-size:0.7rem;letter-spacing:3px;text-transform:uppercase;"
        f"margin-bottom:0.5rem'>TODAY — {today.strftime('%b %d')}</div>",
        unsafe_allow_html=True,
    )
    if today_events.empty:
        st.caption("Clear.")
    else:
        for _, row in today_events.iterrows():
            emoji    = classify_event(row["summary"])
            time_str = ""
            if str(row.get("all_day", "True")).lower() != "true":
                try:
                    from dateutil.parser import isoparse
                    dt       = isoparse(str(row["start"]))
                    time_str = f"<br><span style='color:#4db8d4;font-size:0.68rem'>⏰ {dt.strftime('%I:%M %p').lstrip('0')}</span>"
                except Exception:
                    pass
            loc = f"<br><span style='color:#a09880;font-size:0.68rem'>📍 {row['location']}</span>" if row["location"] else ""
            st.markdown(
                f"<div style='background:#0a2a36;border-left:2px solid #c8501a;"
                f"padding:0.6rem 0.8rem;margin:0.4rem 0;font-size:0.82rem'>"
                f"{emoji} <b>{row['summary']}</b>{time_str}{loc}</div>",
                unsafe_allow_html=True,
            )

with col_week:
    st.markdown(
        "<div style='color:#ffcc44;font-family:Josefin Sans,sans-serif;"
        "font-size:0.7rem;letter-spacing:3px;text-transform:uppercase;"
        "margin-bottom:0.5rem'>NEXT 7 DAYS</div>",
        unsafe_allow_html=True,
    )
    if week_events.empty:
        st.caption("Nothing coming up.")
    else:
        current_day = None
        for _, row in week_events.sort_values("start_date").iterrows():
            if row["start_date"] != current_day:
                current_day = row["start_date"]
                st.markdown(
                    f"<div style='color:#c8501a;font-size:0.68rem;"
                    f"letter-spacing:2px;margin-top:0.6rem;font-family:Josefin Sans,sans-serif'>"
                    f"{pd.Timestamp(current_day).strftime('%A %b %d').upper()}</div>",
                    unsafe_allow_html=True,
                )
            emoji = classify_event(row["summary"])
            st.markdown(
                f"<div style='font-size:0.8rem;padding:0.2rem 0 0.2rem 0.6rem;"
                f"border-left:1px solid rgba(200,80,26,0.4)'>"
                f"{emoji} {row['summary']}</div>",
                unsafe_allow_html=True,
            )

with col_month:
    st.markdown(
        "<div style='color:#ffcc44;font-family:Josefin Sans,sans-serif;"
        "font-size:0.7rem;letter-spacing:3px;text-transform:uppercase;"
        "margin-bottom:0.5rem'>NEXT 30 DAYS</div>",
        unsafe_allow_html=True,
    )
    if month_events.empty:
        st.caption("Nothing on the horizon.")
    else:
        month_events = month_events.copy()
        month_events["week_start"] = month_events["start_date"].apply(
            lambda d: pd.Timestamp(d) - timedelta(days=pd.Timestamp(d).weekday())
        )
        for week, group in month_events.groupby("week_start"):
            st.markdown(
                f"<div style='color:#c8501a;font-size:0.68rem;letter-spacing:2px;"
                f"margin-top:0.6rem;font-family:Josefin Sans,sans-serif'>"
                f"WK OF {pd.Timestamp(week).strftime('%b %d').upper()}</div>",
                unsafe_allow_html=True,
            )
            for _, row in group.sort_values("start_date").iterrows():
                emoji = classify_event(row["summary"])
                day   = pd.Timestamp(row["start_date"]).strftime("%a %d")
                st.markdown(
                    f"<div style='font-size:0.78rem;padding:0.15rem 0 0.15rem 0.6rem;"
                    f"border-left:1px solid rgba(77,184,212,0.25)'>"
                    f"<span style='color:#a09880'>{day}</span> {emoji} {row['summary']}</div>",
                    unsafe_allow_html=True,
                )

st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — Goals scoreboard
# ─────────────────────────────────────────────────────────────────────────────

section_header("🎯 Goals · 2026")

try:
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
        cols    = st.columns(len(domains), gap="medium")
        for col, domain in zip(cols, domains):
            with col:
                st.markdown(
                    f"<div style='color:#c8501a;font-family:Josefin Sans,sans-serif;"
                    f"font-size:0.65rem;letter-spacing:4px;text-transform:uppercase;"
                    f"margin-bottom:0.6rem;border-bottom:1px solid rgba(200,80,26,0.3);"
                    f"padding-bottom:0.3rem'>{domain}</div>",
                    unsafe_allow_html=True,
                )
                for _, row in goal_progress[goal_progress["domain"] == domain].iterrows():
                    label = row["goal_key"].replace("_", " ").title()
                    pct   = float(row["progress_percent"])
                    cur   = row.get("current_value")
                    tgt   = row.get("target_numeric")
                    nums  = f" · {cur:.0f}/{tgt:.0f}" if cur == cur and tgt == tgt else ""
                    color = "#c8501a" if pct < 50 else "#ffcc44" if pct < 80 else "#39ff6e"
                    st.markdown(
                        f"<div style='margin-bottom:0.6rem'>"
                        f"<div style='font-size:0.72rem;color:#a09880;margin-bottom:0.15rem'>"
                        f"{label}{nums}</div>"
                        f"<div style='background:#0a2a36;height:4px'>"
                        f"<div style='width:{min(pct,100):.0f}%;height:4px;background:{color}'>"
                        f"</div></div></div>",
                        unsafe_allow_html=True,
                    )
except Exception:
    st.info("Run `dbt run` to populate goal progress.")
