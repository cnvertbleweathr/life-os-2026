"""
Music page — Spotify streaming stats + Daily 10 playlist.
"""

import json
import os
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]

STREAMS_CLEAN   = ROOT / "data" / "spotify" / "processed" / "streams_clean.csv"
SPOTIFY_SUMMARY = ROOT / "data" / "spotify" / "metrics" / f"spotify_summary_{date.today().year}.csv"
DAILY10_LATEST  = ROOT / "data" / "spotify" / "processed" / "daily10_latest.json"
DAILY10_AUDIT   = ROOT / "data" / "spotify" / "processed" / "daily10_audit.csv"

st.set_page_config(page_title="Music · Life OS", page_icon="🎵", layout="wide")
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
# Top-line metrics
# ---------------------------------------------------------------------------

if summary is not None:
    total_min    = float(summary.get("spotify_minutes_ytd", 0))
    goal_min     = float(summary.get("spotify_goal_minutes", 50000))
    days_on      = int(float(summary.get("spotify_days_listened_ytd", 0)))
    unique_art   = int(float(summary.get("spotify_unique_artists_ytd", 0)))
    unique_trk   = int(float(summary.get("spotify_unique_tracks_ytd", 0)))
    top_artist   = summary.get("spotify_top_artist_ytd", "")
    pct          = float(summary.get("spotify_progress_pct", 0))

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Minutes Streamed", f"{int(total_min):,}", f"{int(total_min/60):,} hrs")
    c2.metric("Days Listened", days_on)
    c3.metric("Unique Artists", f"{unique_art:,}")
    c4.metric("Unique Tracks", f"{unique_trk:,}")
    c5.metric("Top Artist", top_artist)

    st.progress(min(int(pct), 100), text=f"{pct:.1f}% of {int(goal_min):,} min annual goal")

st.divider()

# ---------------------------------------------------------------------------
# Monthly listening trend
# ---------------------------------------------------------------------------

if df is not None and not df.empty:
    st.subheader("📈 Monthly Listening")

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
        margin=dict(l=0, r=0, t=10, b=0),
        xaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
        yaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ---------------------------------------------------------------------------
    # Top artists + top tracks side by side
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
    # Listening heatmap — hour of day x day of week
    # ---------------------------------------------------------------------------

    st.subheader("🕐 When You Listen")

    df["dow"] = pd.to_datetime(df["date"]).dt.day_name()
    heatmap = (
        df.groupby(["dow", "hour"])["minutes"]
        .sum()
        .reset_index()
    )

    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    pivot = heatmap.pivot(index="dow", columns="hour", values="minutes").reindex(day_order).fillna(0)

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
        margin=dict(l=0, r=0, t=10, b=0),
        height=260,
    )
    st.plotly_chart(fig_h, use_container_width=True)

    st.divider()

    # ---------------------------------------------------------------------------
    # Recent listens
    # ---------------------------------------------------------------------------

    with st.expander("🕓 Recent Listens"):
        recent = (
            df.sort_values("date", ascending=False)
            .head(50)[["date", "artist_name", "track_name", "minutes"]]
            .rename(columns={"date": "Date", "artist_name": "Artist", "track_name": "Track", "minutes": "Min"})
        )
        recent["Min"] = recent["Min"].round(1)
        st.dataframe(recent, use_container_width=True, hide_index=True)

else:
    st.info(
        "Streaming history not loaded. Copy your Spotify JSON files to "
        "`data/spotify/raw/streaming_history/` and run:\n"
        "```bash\npython scripts/spotify_ingest_streaming.py\npython scripts/spotify_metrics.py\n```"
    )

st.divider()

# ---------------------------------------------------------------------------
# Daily 10
# ---------------------------------------------------------------------------

st.subheader("🎲 Daily 10")
st.caption("5 from your top 500 · 5 unheard Tewnidge artists")

if DAILY10_LATEST.exists():
    latest = json.loads(DAILY10_LATEST.read_text())
    playlist_id   = latest.get("playlist_id", "")
    playlist_date = latest.get("date", "")
    is_fresh = playlist_date == date.today().isoformat()

    col1, col2 = st.columns([2, 1])
    with col1:
        if playlist_id:
            st.components.v1.iframe(
                f"https://open.spotify.com/embed/playlist/{playlist_id}?utm_source=generator&theme=0",
                height=380,
            )
    with col2:
        st.metric("Playlist date", playlist_date)
        if is_fresh:
            st.success("✓ Today's playlist is ready")
        else:
            st.warning(f"Last generated: {playlist_date}")
            st.caption("Run `python scripts/spotify_daily10_playlist.py --no-decorate`")
        if playlist_id:
            st.markdown(f"[Open in Spotify](https://open.spotify.com/playlist/{playlist_id})")
else:
    st.info("No Daily 10 yet. Run `python scripts/spotify_daily10_playlist.py --no-decorate`")

# Audit log
if DAILY10_AUDIT.exists():
    st.divider()
    st.subheader("📋 Playlist History")
    audit = pd.read_csv(DAILY10_AUDIT)
    audit.columns = [c.strip() for c in audit.columns]
    c1, c2 = st.columns(2)
    c1.metric("Playlists Generated", audit["date"].nunique() if "date" in audit.columns else 0)
    c2.metric("Total Tracks Queued", len(audit))
    with st.expander("Full audit log"):
        st.dataframe(audit.sort_values("date", ascending=False), use_container_width=True, hide_index=True)
