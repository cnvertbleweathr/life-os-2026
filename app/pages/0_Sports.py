"""
Sports page — styled to match Home. Two-column stream cards + news + Degenerates Corner.
"""

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

sys.path.insert(0, str(ROOT / "app"))
from ons_theme import apply_theme, section_header

STREAMS_PATH = ROOT / "data" / "streams" / "today.json"
NEWS_API_KEY  = os.getenv("NEWS_API_KEY", "")

MY_TEAMS = [
    {"name": "Orlando Magic",        "query": "Orlando Magic NBA",         "emoji": "🏀"},
    {"name": "Tampa Bay Buccaneers", "query": "Tampa Bay Buccaneers NFL",  "emoji": "🏈"},
    {"name": "Orlando City SC",      "query": "Orlando City Soccer MLS",   "emoji": "⚽"},
    {"name": "Miami Marlins",        "query": "Miami Marlins MLB",         "emoji": "⚾"},
    {"name": "Florida Panthers",     "query": "Florida Panthers NHL",      "emoji": "🏒"},
    {"name": "Colorado Avalanche",   "query": "Colorado Avalanche NHL",    "emoji": "🏒"},
    {"name": "Denver Nuggets",       "query": "Denver Nuggets NBA",        "emoji": "🏀"},
    {"name": "Colorado Rockies",     "query": "Colorado Rockies MLB",      "emoji": "⚾"},
]

st.set_page_config(page_title="Sports · ONS", page_icon="🏟️", layout="wide")
apply_theme()
st.title("🏟️ Sports")
st.caption("Streams · News · Degenerates Corner")


@st.cache_data(ttl=1800)
def fetch_team_news(query: str, api_key: str) -> list[dict]:
    if not api_key:
        return []
    try:
        r = requests.get(
            "https://newsapi.org/v2/everything",
            params={"q": query, "apiKey": api_key, "pageSize": 3,
                    "sortBy": "publishedAt", "language": "en"},
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("articles", [])
    except Exception:
        return []


@st.cache_data(ttl=300)
def load_streams() -> dict:
    if not STREAMS_PATH.exists():
        return {}
    try:
        return json.loads(STREAMS_PATH.read_text())
    except Exception:
        return {}


def stream_card(match: dict, border_color: str = "#0B5324") -> None:
    live      = match.get("is_live")
    badge     = "🔴 LIVE" if live else match.get("kickoff_local", "")
    badge_clr = "#D97706" if live else "#A9B2AC"
    st.markdown(
        f"<div style='background:#373D39;border:1px solid #434A45;"
        f"border-left:3px solid {border_color};"
        f"padding:0.6rem 0.8rem;margin:0.2rem 0;border-radius:4px'>"
        f"<div style='font-weight:600;font-size:0.85rem;color:#F5EFEB'>"
        f"{match.get('team_label') or match.get('title','')}</div>"
        f"<div style='font-size:0.75rem;color:#A9B2AC;margin:0.1rem 0'>"
        f"{match.get('title','')}</div>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;"
        f"margin-top:0.3rem'>"
        f"<span style='color:{badge_clr};font-size:0.72rem;font-weight:600'>{badge}</span>"
        f"<a href='{match.get('watch_url','')}' target='_blank' "
        f"style='color:#1a7a38;font-size:0.72rem;font-weight:500'>▶ Watch</a>"
        f"</div></div>",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# STREAMS
# ─────────────────────────────────────────────────────────────────────────────

section_header("📺 Today's Streams")

streams_data = load_streams()

if not streams_data:
    st.caption("No stream data. Run `python scripts/daily_sync.py`.")
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

    col_teams, col_top5 = st.columns(2, gap="medium")

    with col_teams:
        st.markdown(
            "<div style='font-size:0.7rem;font-weight:600;letter-spacing:2px;"
            "text-transform:uppercase;color:#A9B2AC;margin-bottom:0.4rem'>"
            "🏆 Your Teams</div>",
            unsafe_allow_html=True,
        )
        if my_teams:
            for match in my_teams:
                stream_card(match, border_color="#0B5324")
        else:
            st.caption("None of your teams are playing today.")

    with col_top5:
        st.markdown(
            "<div style='font-size:0.7rem;font-weight:600;letter-spacing:2px;"
            "text-transform:uppercase;color:#A9B2AC;margin-bottom:0.4rem'>"
            "🔥 Top 5 Today</div>",
            unsafe_allow_html=True,
        )
        if top5:
            for match in top5[:5]:
                stream_card(match, border_color="#404740")
        else:
            st.caption("No top streams today.")

    if popular:
        with st.expander(f"🌍 All Popular Matches Today ({len(popular)})", expanded=False):
            cols = st.columns(2)
            for i, match in enumerate(popular):
                with cols[i % 2]:
                    stream_card(match, border_color="#434A45")


# ─────────────────────────────────────────────────────────────────────────────
# TEAM NEWS
# ─────────────────────────────────────────────────────────────────────────────

section_header("📰 Team News")

if not NEWS_API_KEY:
    st.caption("Add `NEWS_API_KEY` to your `.env` to enable team news.")
else:
    col_sel, _ = st.columns([2, 4])
    with col_sel:
        selected_team = st.selectbox(
            "Select team",
            options=[t["name"] for t in MY_TEAMS],
            label_visibility="collapsed",
        )

    team_cfg = next(t for t in MY_TEAMS if t["name"] == selected_team)

    with st.spinner(f"Fetching {selected_team} news..."):
        articles = fetch_team_news(team_cfg["query"], NEWS_API_KEY)

    if articles:
        for article in articles:
            col_img, col_text = st.columns([1, 4])
            with col_img:
                img = article.get("urlToImage")
                if img:
                    st.image(img, use_container_width=True)
                else:
                    st.markdown(f"### {team_cfg['emoji']}")
            with col_text:
                title  = article.get("title", "")
                source = article.get("source", {}).get("name", "")
                url    = article.get("url", "")
                pub    = article.get("publishedAt", "")
                desc   = article.get("description", "")
                pub_fmt = ""
                if pub:
                    try:
                        pub_fmt = datetime.fromisoformat(
                            pub.replace("Z", "+00:00")
                        ).astimezone().strftime("%b %d, %I:%M %p")
                    except Exception:
                        pub_fmt = pub[:10]
                st.markdown(f"**[{title}]({url})**")
                st.caption(f"{source} · {pub_fmt}")
                if desc:
                    st.markdown(f"_{desc[:200]}_")
            st.space("small")
    else:
        st.caption(f"No recent news found for {selected_team}.")


# ─────────────────────────────────────────────────────────────────────────────
# DEGENERATES CORNER
# ─────────────────────────────────────────────────────────────────────────────

section_header("🎲 Degenerates Corner")

degens_path = ROOT / "data" / "bets" / "todays_picks.json"

if degens_path.exists():
    try:
        picks = json.loads(degens_path.read_text())
        if picks:
            st.caption(f"{len(picks)} qualifying picks this week · sorted by confidence")
            for pick in picks:
                confidence = pick.get("confidence", 0)
                bet_type   = pick.get("bet_type", "EDGE")
                stars      = "⭐" * min(int(confidence / 20), 5)
                ppa_gap    = pick.get("ppa_gap")
                sp_gap     = pick.get("sp_gap")
                week       = pick.get("week", "")
                ou         = pick.get("ou", "")

                border_color = "#0B5324" if bet_type == "EDGE" else "#D97706"
                badge_text   = "EDGE" if bet_type == "EDGE" else "FADE"
                badge_color  = "#0B5324" if bet_type == "EDGE" else "#D97706"

                ppa_str = f"PPA gap: {ppa_gap:+.3f}" if ppa_gap else ""
                sp_str  = f"SP+: {sp_gap:+.1f}" if sp_gap else ""
                stats   = " · ".join(s for s in [ppa_str, sp_str] if s)

                st.markdown(
                    f"<div style='background:#373D39;border:1px solid #434A45;"
                    f"border-left:4px solid {border_color};"
                    f"padding:0.8rem 1rem;margin:0.3rem 0;border-radius:4px'>"
                    f"<div style='display:flex;justify-content:space-between;"
                    f"align-items:flex-start;margin-bottom:0.4rem'>"
                    f"<div>"
                    f"<span style='font-weight:700;font-size:0.9rem;color:#F5EFEB'>"
                    f"{pick.get('matchup','')}</span>"
                    f"<span style='font-size:0.65rem;color:#A9B2AC;margin-left:0.5rem'>"
                    f"Week {week} · O/U {ou}</span>"
                    f"</div>"
                    f"<span style='font-size:0.62rem;font-weight:700;letter-spacing:2px;"
                    f"color:{badge_color};border:1px solid {badge_color};"
                    f"padding:0.1rem 0.4rem'>{badge_text}</span>"
                    f"</div>"
                    f"<div style='font-size:0.85rem;font-weight:600;color:#F5EFEB;"
                    f"margin-bottom:0.3rem'>🎯 {pick.get('bet','')}</div>"
                    f"<div style='display:flex;justify-content:space-between;"
                    f"align-items:center'>"
                    f"<span style='font-size:0.72rem;color:#A9B2AC'>"
                    f"{pick.get('edge','')} · {pick.get('line','')}</span>"
                    f"<span style='font-size:0.85rem'>{stars} "
                    f"<span style='color:#A9B2AC;font-size:0.68rem'>{confidence}%</span></span>"
                    f"</div>"
                    + (f"<div style='font-size:0.68rem;color:#A9B2AC;margin-top:0.2rem'>"
                       f"{stats}</div>" if stats else "") +
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No qualifying picks this week — edges don't meet criteria or off-season.")
    except Exception as e:
        st.caption(f"Could not load picks: {e}")
else:
    col1, col2, col3 = st.columns(3)
    for col, sport, icon, note in [
        (col1, "CFB", "🏈", "Season starts Aug 2026"),
        (col2, "NFL", "🏈", "Coming soon"),
        (col3, "MLB", "⚾", "Coming soon"),
    ]:
        with col:
            st.markdown(
                f"<div style='background:#373D39;border:1px solid #434A45;"
                f"border-top:2px solid #0B5324;border-radius:4px;"
                f"padding:1rem;text-align:center'>"
                f"<div style='font-size:1.5rem'>{icon}</div>"
                f"<div style='font-weight:600;font-size:0.85rem;color:#F5EFEB;"
                f"margin:0.3rem 0'>{sport}</div>"
                f"<div style='font-size:0.75rem;color:#A9B2AC'>{note}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
    st.caption("Pick generation will populate here once analysis pipelines are wired in.")
