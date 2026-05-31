"""
Shows page — Upcoming Denver concerts and events (AEG + Ticketmaster).
Artists from Tewnidge + Deeds playlists are flagged with ⭐.
"""

import json
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))
from ons_theme import apply_theme
apply_theme()

ROOT = Path(__file__).resolve().parents[2]

AEG_CSV      = ROOT / "data" / "shows" / "processed" / "denver_events_upcoming.csv"
TM_CSV       = ROOT / "data" / "shows" / "processed" / "denver_events_ticketmaster.csv"
MY_SHOWS     = ROOT / "data" / "shows" / "my_artist_shows.json"
MY_ARTISTS   = ROOT / "data" / "spotify" / "processed" / "my_artists.json"
DENVER_TZ    = ZoneInfo("America/Denver")

st.set_page_config(page_title="Shows · Operating Narcisystem", page_icon="🎸", layout="wide")
st.title("🎸 Shows")
st.caption("Upcoming Denver concerts & events · ⭐ = your Tewnidge/Deeds artists")


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

@st.cache_data(ttl=600)
def load_my_artists() -> set[str]:
    if not MY_ARTISTS.exists():
        return set()
    data = json.loads(MY_ARTISTS.read_text())
    return {a.lower().strip() for a in data.get("artists", [])}


@st.cache_data(ttl=600)
def load_shows() -> pd.DataFrame:
    dfs = []
    for path, source in [(AEG_CSV, "AEG"), (TM_CSV, "Ticketmaster")]:
        if path.exists():
            df = pd.read_csv(path)
            df["source"] = source
            dfs.append(df)

    if not dfs:
        return pd.DataFrame()

    df = pd.concat(dfs, ignore_index=True)

    for col in ["title", "venue_name", "start_datetime", "event_url", "source"]:
        if col not in df.columns:
            df[col] = ""
    df = df.fillna("")

    def parse_dt(s):
        if not s:
            return pd.NaT
        s = str(s).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=DENVER_TZ)
            return dt.astimezone(DENVER_TZ)
        except Exception:
            return pd.NaT

    df["dt"] = df["start_datetime"].apply(parse_dt)
    df = df.dropna(subset=["dt"])

    now = datetime.now(tz=DENVER_TZ)
    df = df[df["dt"] > now].copy()

    # Dedupe
    seen = set()
    keep = []
    for _, row in df.iterrows():
        url = str(row.get("event_url", "")).strip()
        key = url if url else f"{row['title'].lower().strip()}|{row['venue_name'].lower().strip()}"
        if key not in seen:
            seen.add(key)
            keep.append(row)

    df = pd.DataFrame(keep).sort_values("dt").reset_index(drop=True)
    df["date_str"]  = df["dt"].apply(lambda d: d.strftime("%a, %b %d"))
    df["time_str"]  = df["dt"].apply(lambda d: d.strftime("%I:%M %p").lstrip("0"))
    df["month_str"] = df["dt"].apply(lambda d: d.strftime("%B %Y"))

    return df


my_artists = load_my_artists()
shows = load_shows()


def is_my_artist(title: str) -> bool:
    t = title.lower()
    return any(a in t for a in my_artists)


# ---------------------------------------------------------------------------
# My artist shows alert
# ---------------------------------------------------------------------------

if MY_SHOWS.exists():
    my_shows_data = json.loads(MY_SHOWS.read_text())
    my_shows_list = my_shows_data.get("shows", [])
    if my_shows_list:
        st.subheader("⭐ Your Artists Have Shows Coming Up")
        for show in my_shows_list:
            ticket_link = f" · [🎟 Tickets]({show['event_url']})" if show.get("event_url") else ""
            st.success(
                f"**{show['artist']}** — {show['title']}  \n"
                f"📍 {show['venue']} · {show['date_str']} at {show['time_str']}{ticket_link}"
            )
        st.divider()

if shows.empty:
    st.info(
        "No shows data yet. Run:\n"
        "```bash\npython scripts/daily_sync.py --only aeg_events ticketmaster shows_metrics\n"
        "python scripts/sync_playlist_artists.py\n```"
    )
    st.stop()

# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------

my_artist_count = shows["title"].apply(is_my_artist).sum()
total = len(shows)
next_show = shows.iloc[0]
venues = shows["venue_name"].nunique()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Upcoming Shows", total)
c2.metric("⭐ Your Artists", int(my_artist_count))
c3.metric("Next Show", next_show["date_str"])
c4.metric("Venues", venues)

# Next show callout
st.markdown("---")
star = "⭐ " if is_my_artist(next_show["title"]) else ""
st.markdown(
    f"**Next up:** {star}{next_show['title']}  \n"
    f"📍 {next_show['venue_name']} · {next_show['date_str']} at {next_show['time_str']}  \n"
    + (f"[🎟 Get Tickets]({next_show['event_url']})" if next_show.get("event_url") else "")
)

st.divider()

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

col_v, col_s, col_f, col_search = st.columns([2, 1, 1, 2])

with col_v:
    all_venues = ["All venues"] + sorted(shows["venue_name"].unique().tolist())
    selected_venue = st.selectbox("Venue", all_venues)

with col_s:
    selected_source = st.selectbox("Source", ["All", "AEG", "Ticketmaster"])

with col_f:
    my_only = st.checkbox("⭐ My artists only")

with col_search:
    search = st.text_input("Search", placeholder="Artist or event name...")

filtered = shows.copy()
if selected_venue != "All venues":
    filtered = filtered[filtered["venue_name"] == selected_venue]
if selected_source != "All":
    filtered = filtered[filtered["source"] == selected_source]
if my_only:
    filtered = filtered[filtered["title"].apply(is_my_artist)]
if search:
    filtered = filtered[filtered["title"].str.lower().str.contains(search.lower())]

st.caption(f"Showing {len(filtered)} of {total} upcoming shows")

# ---------------------------------------------------------------------------
# Shows grouped by month
# ---------------------------------------------------------------------------

for month, group in filtered.groupby("month_str", sort=False):
    st.subheader(f"📅 {month}")
    for _, row in group.iterrows():
        star     = "⭐ " if is_my_artist(row["title"]) else ""
        ticket   = f" · [🎟 Tickets]({row['event_url']})" if row.get("event_url") else ""
        venue    = f" · 📍 {row['venue_name']}" if row.get("venue_name") else ""
        src_tag  = f" `{row['source']}`"
        st.markdown(
            f"**{row['date_str']}** at {row['time_str']} — "
            f"{star}**{row['title']}**{venue}{ticket}{src_tag}"
        )
