"""
ONS — Home page. Single-screen layout for 1920×1080.

Row 1: Next 30 Days | Daily 10 embed | Today's WOD
Row 2: Your Teams   | Top 5 Today    | Goals at a glance
"""

import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import requests as _req
import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

sys.path.insert(0, str(ROOT / "app"))
from ons_theme import apply_theme, section_header

EVENTS_CSV   = ROOT / "data" / "calendar" / "processed" / "events_clean_2026.csv"
STREAMS_PATH = ROOT / "data" / "streams" / "today.json"
LOGO_PATH    = ROOT / "app" / "static" / "ons_logo.png"
PH_LOGO_PATH = ROOT / "app" / "static" / "parkhill_logo.png"
DB_PATH      = str(ROOT / "data" / "warehouse" / "ons.duckdb")
WOD_PATH     = ROOT / "data" / "fitness" / "wod_today.json"
DAILY10_PATH = ROOT / "data" / "spotify" / "processed" / "daily10_latest.json"

st.set_page_config(
    page_title="ONS",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()

st.markdown("""
<style>
  .block-container { padding-top: 0.75rem !important; padding-bottom: 0 !important; }
  .ons-section-header { margin: 0.4rem 0 0.3rem !important; }
  [data-testid="stMetricValue"] { font-size: 1.4rem !important; }
  [data-testid="stMetricLabel"] { font-size: 0.6rem !important; }
  [data-testid="stProgressBar"] > div { height: 4px !important; }
</style>
""", unsafe_allow_html=True)

today = date.today()


# ─────────────────────────────────────────────────────────────────────────────
# Data loaders
# ─────────────────────────────────────────────────────────────────────────────

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


@st.cache_data(ttl=600)
def load_wod() -> dict:
    if not WOD_PATH.exists():
        return {}
    try:
        return json.loads(WOD_PATH.read_text())
    except Exception:
        return {}


@st.cache_data(ttl=3600)
def load_daily10() -> dict:
    if not DAILY10_PATH.exists():
        return {}
    try:
        return json.loads(DAILY10_PATH.read_text())
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
wod          = load_wod()
daily10      = load_daily10()

month_events = events[
    (events["start_date"] >= today) &
    (events["start_date"] <= today + timedelta(days=30))
].sort_values("start_date") if not events.empty else pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH))
    st.caption(today.strftime("%A, %B %d, %Y"))


# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(
    f"<h1 style='margin-bottom:0.1rem;padding-bottom:0.2rem'>"
    f"🧭 Operating Narcisystem"
    f"<span style='font-family:Josefin Sans,sans-serif;font-size:0.7rem;"
    f"letter-spacing:4px;color:#A9B2AC;text-transform:uppercase;"
    f"margin-left:1.5rem;vertical-align:middle'>"
    f"{today.strftime('%A, %B %d, %Y')}</span></h1>",
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────────────────────────────────────
# ROW 1 — Next 30 Days | Daily 10 | Today's WOD
# ─────────────────────────────────────────────────────────────────────────────

col_cal, col_d10, col_wod = st.columns([2, 2, 2], gap="medium")

# ── Next 30 Days ─────────────────────────────────────────────────────────────
with col_cal:
    section_header("📅 Next 30 Days")
    if month_events.empty:
        st.caption("No upcoming events.")
    else:
        me = month_events.copy()
        me["week_start"] = me["start_date"].apply(
            lambda d: pd.Timestamp(d) - timedelta(days=pd.Timestamp(d).weekday())
        )
        lines = []
        current_week = None
        for _, row in me.iterrows():
            week = row["week_start"]
            if week != current_week:
                current_week = week
                wk_label = pd.Timestamp(week).strftime("%b %d").upper()
                lines.append(
                    f"<div style='color:#0B5324;font-size:0.6rem;letter-spacing:2px;"
                    f"font-family:Josefin Sans,sans-serif;margin-top:0.35rem'>"
                    f"WK OF {wk_label}</div>"
                )
            emoji = classify_event(row["summary"])
            day   = pd.Timestamp(row["start_date"]).strftime("%a %d")
            lines.append(
                f"<div style='font-size:0.73rem;padding:0.08rem 0 0.08rem 0.5rem;"
                f"border-left:1px solid rgba(11,83,36,0.3);line-height:1.3'>"
                f"<span style='color:#A9B2AC;font-size:0.66rem'>{day}</span> "
                f"{emoji} {row['summary']}</div>"
            )
        st.markdown(
            "<div style='max-height:380px;overflow-y:auto;padding-right:4px'>"
            + "".join(lines) + "</div>",
            unsafe_allow_html=True,
        )

# ── Daily 10 ─────────────────────────────────────────────────────────────────
with col_d10:
    section_header("🎵 Daily 10")
    playlist_id = daily10.get("playlist_id", "")
    if playlist_id:
        st.components.v1.iframe(
            f"https://open.spotify.com/embed/playlist/{playlist_id}"
            f"?utm_source=generator&theme=0",
            height=380,
        )
    else:
        st.caption("No Daily 10 yet. Run daily sync.")

# ── Today's WOD ──────────────────────────────────────────────────────────────
with col_wod:
    section_header("💪 Today's WOD")
    if wod.get("fetched_ok") and wod.get("text"):
        if PH_LOGO_PATH.exists():
            st.image(str(PH_LOGO_PATH), width=120)
        wod_text = wod["text"]
        sections = re.split(r'\b([A-Z])\.\s+', wod_text)
        if len(sections) > 1:
            i = 1
            while i < len(sections) - 1:
                letter  = sections[i]
                content = re.sub(r'https?://\S+', '', sections[i + 1]).strip()
                st.markdown(
                    f"<div style='margin:0.25rem 0;font-size:0.78rem;line-height:1.4'>"
                    f"<span style='color:#0B5324;font-weight:bold'>{letter}.</span> "
                    f"{content}</div>",
                    unsafe_allow_html=True,
                )
                i += 2
        else:
            clean = re.sub(r'https?://\S+', '', wod_text).strip()
            st.markdown(
                f"<div style='font-size:0.78rem;line-height:1.45'>{clean[:400]}</div>",
                unsafe_allow_html=True,
            )
        if wod.get("date") != today.isoformat():
            st.caption(f"⚠️ Showing {wod.get('date')} — today's WOD not yet fetched")
    elif wod:
        st.caption(f"WOD fetch failed: {wod.get('error', 'unknown')}")
        st.caption("Run `python scripts/fetch_wod.py`")
    else:
        st.caption("No WOD yet. Run daily sync.")


# ─────────────────────────────────────────────────────────────────────────────
# ROW 2 — Your Teams | Top 5 Today | Goals
# ─────────────────────────────────────────────────────────────────────────────

col_teams, col_top5, col_goals = st.columns([2, 2, 2], gap="medium")

# ── Your Teams ───────────────────────────────────────────────────────────────
with col_teams:
    section_header("🏆 Your Teams")
    my_teams = streams_data.get("my_teams", [])
    if my_teams:
        for match in my_teams[:4]:
            live  = match.get("is_live")
            badge = "🔴 LIVE" if live else match.get("kickoff_local", "")
            st.markdown(
                f"<div style='background:#373D39;border-left:2px solid #0B5324;"
                f"padding:0.25rem 0.6rem;margin:0.15rem 0;font-size:0.74rem'>"
                f"<b>{match.get('team_label','')}</b> "
                f"<span style='color:#A9B2AC;font-size:0.66rem'>{match.get('title','')}</span><br>"
                f"<span style='color:#1a7a38;font-size:0.65rem'>{badge} · "
                f"<a href='{match.get('watch_url','')}' target='_blank' "
                f"style='color:#1a7a38'>▶ Watch</a></span>"
                f"</div>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("No team games today.")

# ── Top 5 Today ──────────────────────────────────────────────────────────────
with col_top5:
    section_header("🔥 Top 5 Today")
    top5 = streams_data.get("top5", [])
    if top5:
        for match in top5[:5]:
            live = "🔴 LIVE" if match.get("is_live") else match.get("kickoff_local", "")
            cat  = match.get("category", "").replace("-", " ").title()
            st.markdown(
                f"<div style='background:#373D39;border-left:2px solid #404740;"
                f"padding:0.25rem 0.6rem;margin:0.15rem 0;font-size:0.74rem'>"
                f"<b>{match.get('title','')}</b> "
                f"<span style='color:#A9B2AC;font-size:0.65rem'>{cat}</span><br>"
                f"<span style='color:#1a7a38;font-size:0.65rem'>{live} · "
                f"<a href='{match.get('watch_url','')}' target='_blank' "
                f"style='color:#1a7a38'>▶ Watch</a></span>"
                f"</div>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("No streams data. Run daily sync.")

# ── Goals at a glance ────────────────────────────────────────────────────────
with col_goals:
    section_header("🎯 Goals · 2026")
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        goal_progress = con.execute("""
            SELECT domain, goal_key, current_value, target_numeric, progress_percent
            FROM main_marts.mart_goal_progress
            WHERE progress_percent IS NOT NULL
              AND target_numeric IS NOT NULL
              AND target_numeric > 0
            ORDER BY domain, progress_percent DESC
        """).df()
        con.close()

        if not goal_progress.empty:
            for domain in goal_progress["domain"].unique():
                st.markdown(
                    f"<div style='color:#0B5324;font-family:Josefin Sans,sans-serif;"
                    f"font-size:0.6rem;letter-spacing:3px;text-transform:uppercase;"
                    f"margin:0.5rem 0 0.2rem;border-bottom:1px solid rgba(11,83,36,0.4);"
                    f"padding-bottom:0.2rem'>{domain}</div>",
                    unsafe_allow_html=True,
                )
                for _, row in goal_progress[goal_progress["domain"] == domain].iterrows():
                    label = row["goal_key"].replace("_", " ").title()
                    pct   = float(row["progress_percent"])
                    cur   = row.get("current_value")
                    tgt   = row.get("target_numeric")
                    nums  = f"{cur:.0f}/{tgt:.0f}" if cur == cur and tgt == tgt else ""
                    color = "#0B5324" if pct < 50 else "#D97706" if pct < 80 else "#39ff6e"
                    st.markdown(
                        f"<div style='margin-bottom:0.3rem'>"
                        f"<div style='display:flex;justify-content:space-between;"
                        f"font-size:0.68rem;color:#A9B2AC;margin-bottom:0.1rem'>"
                        f"<span>{label}</span>"
                        f"<span style='color:{color}'>{nums} · {pct:.0f}%</span></div>"
                        f"<div style='background:#373D39;height:3px'>"
                        f"<div style='width:{min(pct,100):.0f}%;height:3px;background:{color}'>"
                        f"</div></div></div>",
                        unsafe_allow_html=True,
                    )
        else:
            st.caption("No goal data. Run `dbt run`.")
    except Exception:
        st.caption("Run `dbt run` to populate goals.")
