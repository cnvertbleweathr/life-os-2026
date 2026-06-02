"""
Sports page — Today's streams, team news, and Degenerates Corner.
"""

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import requests
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

sys.path.insert(0, str(ROOT / "app"))
from ons_theme import apply_theme, section_header

STREAMS_PATH = ROOT / "data" / "streams" / "today.json"
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

MY_TEAMS = [
    {"name": "Orlando Magic",         "query": "Orlando Magic NBA",          "emoji": "🏀"},
    {"name": "Tampa Bay Buccaneers",  "query": "Tampa Bay Buccaneers NFL",   "emoji": "🏈"},
    {"name": "Orlando City SC",       "query": "Orlando City Soccer MLS",    "emoji": "⚽"},
    {"name": "Miami Marlins",         "query": "Miami Marlins MLB",          "emoji": "⚾"},
    {"name": "Florida Panthers",      "query": "Florida Panthers NHL",       "emoji": "🏒"},
    {"name": "Colorado Avalanche",    "query": "Colorado Avalanche NHL",     "emoji": "🏒"},
    {"name": "Denver Nuggets",        "query": "Denver Nuggets NBA",         "emoji": "🏀"},
    {"name": "Colorado Rockies",      "query": "Colorado Rockies MLB",       "emoji": "⚾"},
]

st.set_page_config(page_title="Sports · ONS", page_icon="🏟️", layout="wide")
apply_theme()
st.title("🏟️ Sports")
st.caption("Streams · News · Degenerates Corner")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@st.cache_data(ttl=1800)  # 30 min cache
def fetch_team_news(query: str, api_key: str) -> list[dict]:
    if not api_key:
        return []
    try:
        r = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "apiKey": api_key,
                "pageSize": 3,
                "sortBy": "publishedAt",
                "language": "en",
            },
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("articles", [])
    except Exception:
        return []


@st.cache_data(ttl=300)
def load_streams() -> dict | None:
    if not STREAMS_PATH.exists():
        return None
    try:
        return json.loads(STREAMS_PATH.read_text())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Today's Streams
# ---------------------------------------------------------------------------

section_header("📺 Today's Streams")

streams_data = load_streams()

if streams_data is None:
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

    if my_teams:
        st.markdown("**🏆 Your Teams**")
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

    if top5:
        st.markdown("**🔥 Top 5 Today**")
        for match in top5:
            live_badge = " 🔴 LIVE" if match.get("is_live") else f" · {match.get('kickoff_local', '')}"
            cat = match.get("category", "").replace("-", " ").title()
            st.markdown(
                f"{cat} — **{match.get('title', '')}**{live_badge} "
                f"[▶ Watch]({match.get('watch_url', '')})"
            )

    if popular:
        with st.expander(f"🌍 All Popular Matches Today ({len(popular)})", expanded=False):
            for match in popular:
                live_badge = " 🔴 LIVE" if match.get("is_live") else f" · {match.get('kickoff_local', '')}"
                cat = match.get("category", "").replace("-", " ").title()
                st.markdown(
                    f"**{match.get('title', '')}** — {cat}{live_badge} "
                    f"[▶ Watch]({match.get('watch_url', '')})"
                )


# ------
# Team News
# ---------------------------------------------------------------------------

section_header("📰 Team News")

if not NEWS_API_KEY:
    st.caption("Add `NEWS_API_KEY` to your `.env` to enable team news.")
else:
    selected_team = st.selectbox(
        "Select team",
        options=[t["name"] for t in MY_TEAMS],
        index=0,
    )

    team_cfg = next(t for t in MY_TEAMS if t["name"] == selected_team)

    with st.spinner(f"Fetching {selected_team} news..."):
        articles = fetch_team_news(team_cfg["query"], NEWS_API_KEY)

    if articles:
        for article in articles:
            col_img, col_text = st.columns([1, 3])
            with col_img:
                img = article.get("urlToImage")
                if img:
                    st.image(img, width="stretch")
                else:
                    st.markdown(f"### {team_cfg['emoji']}")
            with col_text:
                title   = article.get("title", "")
                source  = article.get("source", {}).get("name", "")
                url     = article.get("url", "")
                pub     = article.get("publishedAt", "")
                desc    = article.get("description", "")

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


# ------
# Degenerates Corner
# ---------------------------------------------------------------------------

section_header("🎲 Degenerates Corner")
st.markdown("**Today's Bets of the Day**")

st.info(
    "CFB betting analysis is ready — run `python scripts/cfb_backtest.py` "
    "and `python scripts/pregame_lookup.py` to generate picks.\n\n"
    "NFL and MLB analysis coming soon."
)

# Placeholder bet card structure — will be populated once pick generation is wired in
degens_path = ROOT / "data" / "bets" / "todays_picks.json"

if degens_path.exists():
    try:
        picks = json.loads(degens_path.read_text())
        for pick in picks:
            confidence = pick.get("confidence", 0)
            stars = "⭐" * min(int(confidence / 20), 5)
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.markdown(f"**{pick.get('matchup', '')}**  \n{pick.get('bet', '')}")
                with col2:
                    st.markdown(f"**{pick.get('line', '')}**  \n{pick.get('sport', '')}")
                with col3:
                    st.markdown(f"{stars}  \n{pick.get('edge', '')}")
    except Exception:
        st.caption("Could not load picks.")
else:
    st.markdown("""
    | Sport | Matchup | Bet | Edge | Confidence |
    |-------|---------|-----|------|------------|
    | CFB 🏈 | *Season starts Aug 2026* | — | — | — |
    | NFL 🏈 | *Coming soon* | — | — | — |
    | MLB ⚾ | *Coming soon* | — | — | — |
    """)
    st.caption("Pick generation will populate here once analysis pipelines are wired in.")
