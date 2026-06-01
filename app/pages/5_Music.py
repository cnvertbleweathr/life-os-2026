"""
Music page — Spotify streaming stats + Daily 10 playlist + Music News.
"""

import json
import os
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests as _req
import streamlit as st
from dotenv import load_dotenv

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))
from ons_theme import apply_theme
apply_theme()

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

STREAMS_CLEAN   = ROOT / "data" / "spotify" / "processed" / "streams_clean.csv"
SPOTIFY_SUMMARY = ROOT / "data" / "spotify" / "metrics" / f"spotify_summary_{date.today().year}.csv"
DAILY10_LATEST  = ROOT / "data" / "spotify" / "processed" / "daily10_latest.json"

st.set_page_config(page_title="Music · Operating Narcisystem", page_icon="🎵", layout="wide")
st.title("🎵 Music")
st.caption("Spotify · 2026")

YEAR = 2026


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

@st.cache_data(ttl=600)
def load_streams() -> pd.DataFrame | None:
    if not STREAMS_CLEAN.exists():
        return None
    df = pd.read_csv(STREAMS_CLEAN)
    played_col = "played_at_utc" if "played_at_utc" in df.columns else "played_at"
    df[played_col] = pd.to_datetime(df[played_col], errors="coerce", utc=True)
    df = df.dropna(subset=[played_col])
    df["minutes"] = pd.to_numeric(df["ms_played"], errors="coerce").fillna(0) / 60000
    df["date"] = df[played_col].dt.date
    df["month"] = df[played_col].dt.strftime("%Y-%m")
    df["hour"] = df[played_col].dt.hour
    return df[df[played_col].dt.year == YEAR].copy()


df = load_streams()

summary = None
if SPOTIFY_SUMMARY.exists():
    summary = pd.read_csv(SPOTIFY_SUMMARY).iloc[0]


# ---------------------------------------------------------------------------
# Daily 10  (TOP of page)
# ---------------------------------------------------------------------------

st.subheader("🎲 Daily 10")

@st.cache_data(ttl=3600)
def fetch_spotify_playlist_description(playlist_id: str) -> str:
    """Fetch playlist description live from Spotify API using client credentials."""
    client_id     = os.getenv("SPOTIFY_CLIENT_ID", "")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return ""
    try:
        import base64
        token_resp = __import__("requests").post(
            "https://accounts.spotify.com/api/token",
            headers={"Authorization": "Basic " + base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()},
            data={"grant_type": "client_credentials"},
            timeout=10,
        )
        token_resp.raise_for_status()
        token = token_resp.json().get("access_token", "")
        if not token:
            return ""
        pl_resp = __import__("requests").get(
            f"https://api.spotify.com/v1/playlists/{playlist_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"fields": "description"},
            timeout=10,
        )
        pl_resp.raise_for_status()
        return pl_resp.json().get("description", "") or ""
    except Exception:
        return ""


if DAILY10_LATEST.exists():
    latest = json.loads(DAILY10_LATEST.read_text())
    playlist_id      = latest.get("playlist_id", "")
    playlist_date    = latest.get("date", "")
    description      = latest.get("description_full") or latest.get("description", "")
    tewnidge_artists = latest.get("tewnidge_artists", [])
    is_fresh = playlist_date == date.today().isoformat()

    # If description wasn't persisted to JSON yet, pull it live from Spotify
    if not description and playlist_id:
        description = fetch_spotify_playlist_description(playlist_id)

    col_embed, col_info = st.columns([2, 1])

    with col_embed:
        if playlist_id:
            st.components.v1.iframe(
                f"https://open.spotify.com/embed/playlist/{playlist_id}?utm_source=generator&theme=0",
                height=400,
            )
            st.markdown(f"[🔗 Open in Spotify](https://open.spotify.com/playlist/{playlist_id})")

    with col_info:
        if description:
            st.markdown(
                f"""
                <div style="
                    background: rgba(255,255,255,0.05);
                    border: 1px solid rgba(255,255,255,0.12);
                    border-radius: 8px;
                    padding: 16px 18px;
                    font-size: 0.88rem;
                    line-height: 1.55;
                    color: #e0e0e0;
                    box-sizing: border-box;
                ">
                    {description}
                </div>
                """,
                unsafe_allow_html=True,
            )
        elif not is_fresh:
            st.warning(f"Last generated: {playlist_date}")
            st.caption("Run `python scripts/spotify_daily10_playlist.py`")
        else:
            st.caption("No description yet — run `python scripts/spotify_daily10_decorate.py`")

else:
    st.info("No Daily 10 yet. Run `python scripts/spotify_daily10_playlist.py --no-decorate`")

st.divider()


# ---------------------------------------------------------------------------
# Row 1: YTD stats  |  Monthly listening
# ---------------------------------------------------------------------------

if df is not None and not df.empty:
    row1_l, row1_r = st.columns([1, 2])

    with row1_l:
        st.markdown("**📊 Year to Date**")
        if summary is not None:
            total_min  = float(summary.get("spotify_minutes_ytd", 0))
            goal_min   = float(summary.get("spotify_goal_minutes", 50000))
            days_on    = int(float(summary.get("spotify_days_listened_ytd", 0)))
            unique_art = int(float(summary.get("spotify_unique_artists_ytd", 0)))
            unique_trk = int(float(summary.get("spotify_unique_tracks_ytd", 0)))
            top_artist = summary.get("spotify_top_artist_ytd", "")
            pct        = float(summary.get("spotify_progress_pct", 0))

            ma, mb = st.columns(2)
            ma.metric("Minutes", f"{int(total_min):,}", f"{int(total_min/60):,} hrs")
            mb.metric("Days Active", days_on)
            mc, md = st.columns(2)
            mc.metric("Artists", f"{unique_art:,}")
            md.metric("Tracks", f"{unique_trk:,}")
            st.metric("Top Artist", top_artist)
            st.progress(min(int(pct), 100), text=f"{pct:.1f}% of {int(goal_min/1000):.0f}k min goal")
        else:
            st.info("No summary data yet.")

    with row1_r:
        st.markdown("**📈 Monthly Listening**")
        monthly = (
            df.groupby("month")["minutes"]
            .sum()
            .reset_index()
            .sort_values("month")
        )
        monthly["hours"] = (monthly["minutes"] / 60).round(1)

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=monthly["month"],
            y=monthly["hours"],
            marker_color="#1DB954",
            hovertemplate="%{x}<br>%{y:.1f} hrs<extra></extra>",
        ))
        fig.update_layout(
            xaxis_title=None,
            yaxis_title="Hours",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#FAFAFA"),
            margin=dict(l=0, r=0, t=4, b=0),
            height=300,
            xaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
            yaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ---------------------------------------------------------------------------
    # Row 2: Top artists  |  Top tracks
    # ---------------------------------------------------------------------------

    st.subheader("🎤 Top Artists & Tracks · 2026")

    col_a, col_t = st.columns(2)

    with col_a:
        st.markdown("**Top 15 Artists by Minutes**")
        top_artists = (
            df.groupby("artist_name")["minutes"]
            .sum()
            .sort_values(ascending=False)
            .head(15)
            .reset_index()
        )
        top_artists["hours"] = (top_artists["minutes"] / 60).round(1)

        fig_a = go.Figure(go.Bar(
            x=top_artists["hours"],
            y=top_artists["artist_name"],
            orientation="h",
            marker_color="#1DB954",
            hovertemplate="%{y}<br>%{x:.1f} hrs<extra></extra>",
        ))
        fig_a.update_layout(
            xaxis_title="Hours",
            yaxis=dict(autorange="reversed"),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#FAFAFA"),
            margin=dict(l=0, r=0, t=10, b=0),
            height=420,
        )
        st.plotly_chart(fig_a, use_container_width=True)

    with col_t:
        st.markdown("**Top 15 Tracks by Play Count**")
        top_tracks = (
            df.groupby(["track_name", "artist_name"])
            .agg(plays=("minutes", "count"), minutes=("minutes", "sum"))
            .sort_values("plays", ascending=False)
            .head(15)
            .reset_index()
        )

        fig_t = go.Figure(go.Bar(
            x=top_tracks["plays"],
            y=top_tracks["track_name"] + " — " + top_tracks["artist_name"],
            orientation="h",
            marker_color="#1DB954",
            hovertemplate="%{y}<br>%{x} plays<extra></extra>",
        ))
        fig_t.update_layout(
            xaxis_title="Plays",
            yaxis=dict(autorange="reversed"),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#FAFAFA"),
            margin=dict(l=0, r=0, t=10, b=0),
            height=420,
        )
        st.plotly_chart(fig_t, use_container_width=True)

    st.divider()

    # ---------------------------------------------------------------------------
    # Row 3: Heatmap  |  Recent listens
    # ---------------------------------------------------------------------------

    row3_l, row3_r = st.columns([3, 2])

    with row3_l:
        st.markdown("**🕐 When You Listen**")
        df["dow"] = pd.to_datetime(df["date"]).dt.day_name()
        heatmap_data = df.groupby(["dow", "hour"])["minutes"].sum().reset_index()

        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        pivot = heatmap_data.pivot(index="dow", columns="hour", values="minutes").reindex(day_order).fillna(0)

        fig_h = go.Figure(go.Heatmap(
            z=pivot.values,
            x=[f"{h:02d}:00" for h in pivot.columns],
            y=pivot.index.tolist(),
            colorscale=[[0, "#1a1a2e"], [0.5, "#1DB954"], [1.0, "#ffffff"]],
            hovertemplate="%{y} %{x}<br>%{z:.0f} min<extra></extra>",
        ))
        fig_h.update_layout(
            xaxis_title="Hour of Day",
            yaxis_title=None,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#FAFAFA"),
            margin=dict(l=0, r=0, t=4, b=0),
            height=280,
        )
        st.plotly_chart(fig_h, use_container_width=True)

    with row3_r:
        st.markdown("**🕓 Recent Listens**")
        recent = (
            df.sort_values("date", ascending=False)
            .head(20)[["date", "artist_name", "track_name", "minutes"]]
            .rename(columns={"date": "Date", "artist_name": "Artist", "track_name": "Track", "minutes": "Min"})
        )
        recent["Min"] = recent["Min"].round(1)
        st.dataframe(recent, use_container_width=True, hide_index=True, height=280)

else:
    st.info(
        "Streaming history not loaded. Copy your Spotify JSON files to "
        "`data/spotify/raw/streaming_history/` and run:\n"
        "```bash\npython scripts/spotify_ingest_streaming.py\npython scripts/spotify_metrics.py\n```"
    )
st.divider()


# ---------------------------------------------------------------------------
# Music News  (NewsAPI — same pattern as Sports/Home)
# ---------------------------------------------------------------------------

st.subheader("📰 Music News")

NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")


def fetch_music_news_headlines(api_key: str, page_size: int = 6) -> list[dict]:
    """Reliable baseline — entertainment top headlines."""
    if not api_key:
        return []
    try:
        r = _req.get(
            "https://newsapi.org/v2/top-headlines",
            params={"category": "entertainment", "country": "us",
                    "apiKey": api_key, "pageSize": page_size},
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("articles", [])
    except Exception:
        return []


def render_news_articles(articles: list[dict]) -> None:
    for article in articles:
        col_img, col_text = st.columns([1, 3])
        with col_img:
            img = article.get("urlToImage")
            if img:
                st.image(img, use_container_width=True)
            else:
                st.markdown("🎵")
        with col_text:
            title  = article.get("title", "")
            source = article.get("source", {}).get("name", "")
            url    = article.get("url", "")
            pub    = article.get("publishedAt", "")
            desc   = article.get("description", "")
            pub_fmt = ""
            if pub:
                try:
                    pub_fmt = datetime.fromisoformat(pub.replace("Z", "+00:00")).astimezone().strftime("%b %d, %I:%M %p")
                except Exception:
                    pub_fmt = pub[:10]
            st.markdown(f"**[{title}]({url})**")
            st.caption(f"{source} · {pub_fmt}")
            if desc:
                st.markdown(f"_{desc[:200]}_")
        st.divider()


if not NEWS_API_KEY:
    st.info("Add `NEWS_API_KEY` to your `.env` to enable music news.")
else:
    with st.spinner("Fetching music news…"):
        articles = fetch_music_news_headlines(NEWS_API_KEY, page_size=8)

    if articles:
        render_news_articles(articles)
    else:
        st.caption("No recent music news found.")
