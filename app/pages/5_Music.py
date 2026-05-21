"""
Music page — Spotify daily10 playlist + streaming stats.
"""

import json
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[2]

DAILY10_LATEST   = ROOT / "data" / "spotify" / "processed" / "daily10_latest.json"
DAILY10_AUDIT    = ROOT / "data" / "spotify" / "processed" / "daily10_audit.csv"
STREAMS_CLEAN    = ROOT / "data" / "spotify" / "processed" / "streams_clean.csv"
SPOTIFY_SUMMARY  = ROOT / "data" / "spotify" / "metrics" / f"spotify_summary_{date.today().year}.csv"

st.set_page_config(page_title="Music · Life OS", page_icon="🎵", layout="wide")
st.title("🎵 Music")
st.caption("Spotify · 2026")

# ---------------------------------------------------------------------------
# Daily 10
# ---------------------------------------------------------------------------

st.subheader("🎲 Daily 10")
st.caption("5 from your top 500 · 5 unheard Tewnidge artists")

if DAILY10_LATEST.exists():
    latest = json.loads(DAILY10_LATEST.read_text())
    playlist_date = latest.get("date", "")
    playlist_id   = latest.get("playlist_id", "")

    today_str = date.today().isoformat()
    is_fresh  = playlist_date == today_str

    col1, col2 = st.columns([2, 1])
    with col1:
        if playlist_id:
            embed_url = f"https://open.spotify.com/embed/playlist/{playlist_id}?utm_source=generator&theme=0"
            st.components.v1.iframe(embed_url, height=380)
    with col2:
        st.metric("Playlist date", playlist_date)
        if is_fresh:
            st.success("✓ Today's playlist is ready")
        else:
            st.warning(f"Last generated: {playlist_date}")
            st.caption("Run `python scripts/spotify_daily10_playlist.py` to refresh.")
        if playlist_id:
            st.markdown(f"[Open in Spotify](https://open.spotify.com/playlist/{playlist_id})")
else:
    st.info("No Daily 10 playlist yet. Run:\n```bash\npython scripts/spotify_daily10_playlist.py\n```")

# ---------------------------------------------------------------------------
# Playlist audit log
# ---------------------------------------------------------------------------

st.divider()
st.subheader("📋 Playlist History")

if DAILY10_AUDIT.exists():
    audit = pd.read_csv(DAILY10_AUDIT)
    audit.columns = [c.strip() for c in audit.columns]

    c1, c2 = st.columns(2)
    c1.metric("Playlists Generated", audit["date"].nunique() if "date" in audit.columns else 0)
    c2.metric("Total Tracks Queued", len(audit))

    if "bucket" in audit.columns:
        st.markdown("**Bucket Breakdown**")
        bucket_counts = (
            audit.groupby("bucket").size().reset_index(name="count")
            .sort_values("count", ascending=False)
        )
        bucket_counts["bucket"] = bucket_counts["bucket"].str.replace(
            "A_top500_random", "A · Top 500 Random", regex=False
        ).str.replace(
            "B_tewnidge_artist_unheard_not_on_tewnidge", "B · Tewnidge Unheard", regex=False
        )
        st.dataframe(bucket_counts, use_container_width=True, hide_index=True)

    with st.expander("Full audit log"):
        st.dataframe(audit.sort_values("date", ascending=False), use_container_width=True, hide_index=True)
else:
    st.info("No audit log yet — appears after first playlist generation.")

# ---------------------------------------------------------------------------
# Streaming stats
# ---------------------------------------------------------------------------

st.divider()
st.subheader("📊 Streaming Stats · 2026")

if SPOTIFY_SUMMARY.exists():
    summary = pd.read_csv(SPOTIFY_SUMMARY).iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Minutes Streamed", f"{int(float(summary.get('spotify_minutes_ytd', 0))):,}")
    c2.metric("Days Listened", int(float(summary.get("spotify_days_listened_ytd", 0))))
    c3.metric("Unique Artists", int(float(summary.get("spotify_unique_artists_ytd", 0))))
    c4.metric("Unique Tracks",  int(float(summary.get("spotify_unique_tracks_ytd", 0))))

    goal   = float(summary.get("spotify_goal_minutes", 50000) or 50000)
    actual = float(summary.get("spotify_minutes_ytd", 0) or 0)
    pct    = round(actual / goal * 100, 1) if goal else 0
    st.progress(min(int(pct), 100), text=f"{pct:.1f}% of {int(goal):,} min annual goal")

    top_artist = summary.get("spotify_top_artist_ytd", "")
    top_track  = summary.get("spotify_top_track_ytd", "")
    if top_artist or top_track:
        st.divider()
        ta_col, tt_col = st.columns(2)
        if top_artist:
            ta_col.markdown(f"**🎤 Top Artist**  \n{top_artist}")
        if top_track:
            tt_col.markdown(f"**🎵 Top Track**  \n{top_track}")

elif STREAMS_CLEAN.exists():
    st.info("Streams ingested. Run `python scripts/spotify_metrics.py` to compute stats.")
else:
    st.info(
        "Streaming history export pending from Spotify.\n\n"
        "Once received, drop JSON files in `data/spotify/raw/streaming_history/` and run:\n"
        "```bash\npython scripts/spotify_ingest_streaming.py\npython scripts/spotify_metrics.py\n```"
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Minutes Streamed", "—", "export pending")
    c2.metric("Days Listened",    "—")
    c3.metric("Unique Artists",   "—")
    c4.metric("Unique Tracks",    "—")
    st.progress(0, text="0% of 50,000 min annual goal")