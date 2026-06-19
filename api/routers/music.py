"""
/api/music — Daily 10 playlist, streaming stats, YTD summary, music news.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Request

from api.deps import get_db, query, query_one

router          = APIRouter()
ROOT            = Path(__file__).resolve().parents[2]
DAILY10_PATH    = ROOT / "data" / "spotify" / "processed" / "daily10_latest.json"
STREAMS_CLEAN   = ROOT / "data" / "spotify" / "processed" / "streams_clean.csv"
SPOTIFY_SUMMARY = ROOT / "data" / "spotify" / "metrics" / f"spotify_summary_{date.today().year}.csv"


@router.get("/daily10")
async def daily10():
    """Today's Daily 10 playlist metadata."""
    if not DAILY10_PATH.exists():
        return {"available": False}
    try:
        data = json.loads(DAILY10_PATH.read_text())
        return {"available": True, **data}
    except Exception:
        return {"available": False}


@router.get("/summary")
async def music_summary():
    """YTD Spotify listening summary from CSV metrics."""
    if not SPOTIFY_SUMMARY.exists():
        return {}
    try:
        df  = pd.read_csv(SPOTIFY_SUMMARY)
        row = df.iloc[0].where(pd.notna(df.iloc[0]), None).to_dict()
        return {
            "minutes_ytd":       row.get("spotify_minutes_ytd"),
            "goal_minutes":      row.get("spotify_goal_minutes", 50000),
            "days_listened":     row.get("spotify_days_listened_ytd"),
            "unique_artists":    row.get("spotify_unique_artists_ytd"),
            "unique_tracks":     row.get("spotify_unique_tracks_ytd"),
            "top_artist":        row.get("spotify_top_artist_ytd"),
            "progress_pct":      row.get("spotify_progress_pct"),
        }
    except Exception:
        return {}


@router.get("/top-artists")
async def top_artists(limit: int = 20):
    """Top artists by play count YTD from streaming history."""
    if not STREAMS_CLEAN.exists():
        return []
    try:
        df = pd.read_csv(STREAMS_CLEAN)
        df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
        df = df[df["ts"].dt.year == date.today().year]
        top = (
            df.groupby("master_metadata_album_artist_name")["ms_played"]
            .sum()
            .sort_values(ascending=False)
            .head(limit)
            .reset_index()
        )
        top.columns = ["artist", "ms_played"]
        top["minutes"] = (top["ms_played"] / 60000).round(1)
        return top[["artist", "minutes"]].to_dict(orient="records")
    except Exception:
        return []


@router.get("/top-tracks")
async def top_tracks(limit: int = 20):
    """Top tracks by play count YTD."""
    if not STREAMS_CLEAN.exists():
        return []
    try:
        df = pd.read_csv(STREAMS_CLEAN)
        df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
        df = df[df["ts"].dt.year == date.today().year]
        top = (
            df.groupby(["master_metadata_track_name", "master_metadata_album_artist_name"])
            ["ms_played"]
            .sum()
            .sort_values(ascending=False)
            .head(limit)
            .reset_index()
        )
        top.columns = ["track", "artist", "ms_played"]
        top["minutes"] = (top["ms_played"] / 60000).round(1)
        return top[["track", "artist", "minutes"]].to_dict(orient="records")
    except Exception:
        return []


@router.get("/news")
async def music_news():
    """Recent music news via NewsAPI."""
    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        return []
    import httpx
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q":        "music OR album OR concert OR tour",
                    "language": "en",
                    "sortBy":   "publishedAt",
                    "pageSize": 10,
                    "apiKey":   api_key,
                }
            )
            if r.status_code == 200:
                articles = r.json().get("articles", [])
                return [
                    {
                        "title":       a.get("title"),
                        "source":      a.get("source", {}).get("name"),
                        "url":         a.get("url"),
                        "published":   a.get("publishedAt"),
                        "description": a.get("description"),
                    }
                    for a in articles if a.get("title")
                ]
    except Exception:
        pass
    return []
