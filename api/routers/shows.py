"""
/api/shows — Denver concerts from AEG + Ticketmaster, artist matching.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, Query

router     = APIRouter()
ROOT       = Path(__file__).resolve().parents[2]
AEG_CSV    = ROOT / "data" / "shows" / "processed" / "denver_events_upcoming.csv"
TM_CSV     = ROOT / "data" / "shows" / "processed" / "denver_events_ticketmaster.csv"
MY_SHOWS   = ROOT / "data" / "shows" / "my_artist_shows.json"
MY_ARTISTS = ROOT / "data" / "spotify" / "processed" / "my_artists.json"


def _load_my_artists() -> set[str]:
    if not MY_ARTISTS.exists():
        return set()
    try:
        artists = json.loads(MY_ARTISTS.read_text())
        return {a.lower() for a in artists if isinstance(a, str) and len(a) >= 4}
    except Exception:
        return set()


def _load_shows() -> pd.DataFrame:
    dfs = []
    for path, source in [(AEG_CSV, "AEG"), (TM_CSV, "Ticketmaster")]:
        if path.exists():
            try:
                df = pd.read_csv(path)
                df["source"] = source
                dfs.append(df)
            except Exception:
                pass
    if not dfs:
        return pd.DataFrame()
    combined = pd.concat(dfs, ignore_index=True)
    # Real column is start_datetime, not date/event_date - combined.get()
    # falling through to None previously produced a single NaT broadcast
    # to every row instead of a real per-row datetime column.
    # start_datetime also mixes naive ("2026-01-01T20:00:00") and
    # offset-aware ("2026-06-20T19:00:00-06:00") strings - same issue as
    # the home.py calendar fix, vectorized to_datetime(utc=True) silently
    # NaTs the offset-aware rows when formats are mixed in one column.
    combined["date"] = combined["start_datetime"].apply(
        lambda x: pd.to_datetime(x, errors="coerce", utc=True)
    )
    if "event_url" in combined.columns and "ticket_url" not in combined.columns:
        combined["ticket_url"] = combined["event_url"]
    today_ts = pd.Timestamp(date.today(), tz="UTC")
    combined = combined[combined["date"] >= today_ts]
    combined = combined.sort_values("date").drop_duplicates(
        subset=["title", "date"], keep="first"
    )
    return combined


@router.get("")
async def shows(
    my_artists_only: bool = Query(False, description="Filter to matched artists only"),
    limit: int = Query(100, le=500),
):
    """Upcoming Denver concerts — optionally filtered to your artists."""
    df         = _load_shows()
    my_artists = _load_my_artists()

    if df.empty:
        return []

    def is_match(title: str) -> bool:
        t = str(title).lower()
        return any(a in t for a in my_artists)

    df["is_my_artist"] = df["title"].apply(is_match)

    if my_artists_only:
        df = df[df["is_my_artist"]]

    df["date_str"] = df["date"].dt.strftime("%Y-%m-%d")

    cols = ["date_str", "title", "venue_name", "ticket_url", "source", "is_my_artist"]
    available = [c for c in cols if c in df.columns]
    from api.deps import _clean
    raw_rows = df[available].head(limit).to_dict(orient="records")
    result = [{k: _clean(v) for k, v in row.items()} for row in raw_rows]

    # Rename date_str → date
    for row in result:
        row["date"] = row.pop("date_str", None)

    return result


@router.get("/my-shows")
async def my_shows():
    """Shows by artists in your Spotify playlists."""
    if not MY_SHOWS.exists():
        return []
    try:
        data = json.loads(MY_SHOWS.read_text())
        return data.get("shows", [])
    except Exception:
        return []


@router.get("/summary")
async def shows_summary():
    """Summary stats: total upcoming, my artist count, next show."""
    df = _load_shows()
    if df.empty:
        return {"total": 0, "my_artist_count": 0, "next_show": None}

    my_artists = _load_my_artists()

    def is_match(title: str) -> bool:
        t = str(title).lower()
        return any(a in t for a in my_artists)

    df["is_my_artist"] = df["title"].apply(is_match)
    next_row = df.iloc[0] if not df.empty else None

    from api.deps import _clean
    return {
        "total":           len(df),
        "my_artist_count": int(df["is_my_artist"].sum()),
        "venues":          int(df["venue_name"].nunique()) if "venue_name" in df.columns else 0,
        "next_show":       {
            "title":  _clean(next_row["title"]) if next_row is not None else None,
            "date":   next_row["date"].strftime("%Y-%m-%d") if next_row is not None and pd.notna(next_row["date"]) else None,
            "venue":  _clean(next_row.get("venue_name")) if next_row is not None else None,
        },
    }
