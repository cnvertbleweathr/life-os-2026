"""
/api/music — Daily 10 playlist, streaming stats, YTD summary, this day in music.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Request

from api.deps import get_db, query, query_one

router          = APIRouter()
ROOT            = Path(__file__).resolve().parents[2]
DAILY10_PATH    = ROOT / "data" / "spotify" / "processed" / "daily10_latest.json"
COVERS_DIR      = ROOT / "data" / "spotify" / "processed" / "covers"
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
        df["played_at"] = pd.to_datetime(df["played_at"], errors="coerce")
        df = df[df["played_at"].dt.year == date.today().year]
        top = (
            df.groupby("artist_name")["ms_played"]
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
        df["played_at"] = pd.to_datetime(df["played_at"], errors="coerce")
        df = df[df["played_at"].dt.year == date.today().year]
        top = (
            df.groupby(["track_name", "artist_name"])["ms_played"]
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


ON_THIS_DAY_CACHE = ROOT / "data" / "music" / "onthisday"

# Wikipedia page descriptions are short and consistent ("American rock band",
# "English singer-songwriter"), so a keyword match on them is a reliable
# music filter. Matched against the page description, not the event text.
_MUSIC_WORDS = (
    "musician", "singer", "songwriter", "rapper", "band", "guitarist",
    "drummer", "bassist", "pianist", "composer", "keyboardist", "vocalist",
    "album", "song", "single by", "record producer", "dj", "conductor",
    "music", "opera", "jazz", "hip hop", "punk", "metal", "rock",
)


_MUSIC_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in _MUSIC_WORDS) + r")s?\b")


def _is_music_page(page: dict) -> bool:
    # Word-boundary match so "husband", "operator", "metallurgist" don't hit
    return bool(_MUSIC_RE.search((page.get("description") or "").lower()))


def _my_artist_names() -> set[str]:
    if not STREAMS_CLEAN.exists():
        return set()
    try:
        names = pd.read_csv(STREAMS_CLEAN, usecols=["artist_name"])["artist_name"].dropna()
        return {n.strip().lower() for n in names.unique() if len(n.strip()) >= 4}
    except Exception:
        return set()


async def _fetch_wiki_onthisday(today: date) -> dict:
    """Wikipedia's On This Day feed, cached to disk once per calendar day."""
    ON_THIS_DAY_CACHE.mkdir(parents=True, exist_ok=True)
    cache = ON_THIS_DAY_CACHE / f"{today:%m-%d}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    import httpx
    url = f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/all/{today:%m}/{today:%d}"
    async with httpx.AsyncClient(timeout=10, headers={
        "User-Agent": "ONS-personal-dashboard/1.0 (github.com/cnvertbleweathr/life-os-2026)",
    }) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
    cache.write_text(json.dumps(data))
    return data


@router.get("/on-this-day")
async def on_this_day(limit: int = 8):
    """Music events, births and deaths on today's date (Wikipedia), plus what
    you were listening to on this date in previous years (streams_clean)."""
    today = date.today()
    out: dict = {"date": today.isoformat(), "events": [], "history": [], "error": None}

    try:
        data = await _fetch_wiki_onthisday(today)
        mine = _my_artist_names()
        seen: set[str] = set()
        kinds = {"selected": "event", "events": "event", "births": "born", "deaths": "died"}
        for key, kind in kinds.items():
            for item in data.get(key, []):
                pages = [p for p in item.get("pages", []) if _is_music_page(p)]
                if not pages or item.get("text") in seen:
                    continue
                seen.add(item.get("text"))
                page = pages[0]
                title = page.get("normalizedtitle") or page.get("title", "").replace("_", " ")
                base = title.split(" (")[0].strip().lower()
                out["events"].append({
                    "year": item.get("year"),
                    "kind": kind,
                    "text": item.get("text"),
                    "subject": title,
                    "url": (page.get("content_urls") or {}).get("desktop", {}).get("page"),
                    "is_my_artist": base in mine,
                })
        # Your artists first, then a spread across eras (newest first)
        out["events"].sort(key=lambda e: (not e["is_my_artist"], -(e["year"] or 0)))
        out["events"] = out["events"][:limit]
    except Exception as e:
        out["error"] = str(e)

    if STREAMS_CLEAN.exists():
        try:
            df = pd.read_csv(STREAMS_CLEAN, usecols=["artist_name", "ms_played", "played_at"])
            df["played_at"] = pd.to_datetime(df["played_at"], errors="coerce")
            df = df[(df["played_at"].dt.month == today.month)
                    & (df["played_at"].dt.day == today.day)
                    & (df["played_at"].dt.year < today.year)]
            for yr, g in df.groupby(df["played_at"].dt.year):
                top = g.groupby("artist_name")["ms_played"].sum().sort_values(ascending=False).head(3)
                out["history"].append({
                    "year": int(yr),
                    "minutes": round(g["ms_played"].sum() / 60000),
                    "top_artists": top.index.tolist(),
                })
            out["history"].sort(key=lambda h: -h["year"])
        except Exception:
            pass

    return out


@router.get("/daily10/cover")
async def daily10_cover():
    today_str = date.today().strftime("%Y-%m-%d")
    cover_path = COVERS_DIR / f"{today_str}.jpg"
    if not cover_path.exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No cover saved for today yet")
    from fastapi.responses import FileResponse
    return FileResponse(cover_path, media_type="image/jpeg")
