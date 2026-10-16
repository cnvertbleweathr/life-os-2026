"""
/api/music — Daily 10 playlist, streaming stats, YTD summary, artist of the day.
"""

from __future__ import annotations

import json
import os
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


AOTD_CACHE    = ROOT / "data" / "music" / "artist_of_day"
MY_ARTISTS    = ROOT / "data" / "spotify" / "processed" / "my_artists.json"
UA            = {"User-Agent": "ONS-personal-dashboard/1.0 (github.com/cnvertbleweathr/life-os-2026)"}

# Wikipedia descriptions are short and consistent ("American rock band"),
# so this is how we confirm a Wikipedia hit is actually the artist.
_MUSIC_WORDS = (
    "musician", "singer", "songwriter", "rapper", "band", "guitarist",
    "drummer", "bassist", "pianist", "composer", "keyboardist", "vocalist",
    "record producer", "dj", "duo", "group", "music", "jazz", "hip hop",
    "punk", "metal", "rock", "electronic", "producer",
)
_MUSIC_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in _MUSIC_WORDS) + r")s?\b")


def _tewnidge_artists() -> list[str]:
    """Tewnidge playlist artists from sync_playlist_artists.py. Falls back to
    the combined Tewnidge+Deeds list for files written before the split."""
    if not MY_ARTISTS.exists():
        return []
    data = json.loads(MY_ARTISTS.read_text())
    names = data.get("tewnidge") or data.get("artists") or []
    return sorted({n for n in names if isinstance(n, str) and n.strip()})


def _strip_html(text: str) -> str:
    text = re.sub(r"<a [^>]*>Read more on Last\.fm</a>\.?", "", text or "")
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"User-contributed text is available under.*$", "", text, flags=re.S)
    return text.strip()


async def _audiodb(client, name: str) -> dict | None:
    """Premium only. The public key "123" is a demo key that returns Coldplay
    for every search, so it's never used. Set AUDIODB_API_KEY to enable."""
    key = os.getenv("AUDIODB_API_KEY")
    if not key or key == "123":
        return None
    r = await client.get(f"https://www.theaudiodb.com/api/v1/json/{key}/search.php", params={"s": name})
    if r.status_code != 200:
        return None
    artists = (r.json() or {}).get("artists") or []
    a = next((x for x in artists if (x.get("strArtist") or "").lower() == name.lower()), None)
    if not a:
        return None

    def yr(k):
        v = a.get(k)
        return int(v) if v and str(v).isdigit() and int(v) > 0 else None

    site = a.get("strWebsite") or None
    if site and not site.startswith("http"):
        site = "https://" + site
    return {
        "bio": (a.get("strBiography") or a.get("strBiographyEN") or "").strip(),
        "image": a.get("strArtistThumb") or a.get("strArtistFanart") or None,
        "tags": [t for t in (a.get("strGenre"), a.get("strStyle"), a.get("strMood")) if t],
        "country": a.get("strCountry") or None,
        "formed": yr("intFormedYear") or yr("intBornYear"),
        "members": yr("intMembers"),
        "label": a.get("strLabel") or None,
        "website": site,
        "url": f"https://www.theaudiodb.com/artist/{a['idArtist']}" if a.get("idArtist") else None,
    }


async def _lastfm(client, name: str) -> dict | None:
    """Free key (LASTFM_API_KEY). Best coverage of small/indie artists, plus
    tags, listener counts and similar artists. Images are placeholders, so
    the photo comes from Wikipedia/AudioDB instead."""
    key = os.getenv("LASTFM_API_KEY")
    if not key:
        return None
    r = await client.get("https://ws.audioscrobbler.com/2.0/", params={
        "method": "artist.getinfo", "artist": name, "api_key": key,
        "format": "json", "autocorrect": 1,
    })
    if r.status_code != 200:
        return None
    a = (r.json() or {}).get("artist")
    if not a:
        return None
    bio = _strip_html((a.get("bio") or {}).get("content") or (a.get("bio") or {}).get("summary") or "")
    stats = a.get("stats") or {}
    return {
        "bio": bio,
        "tags": [t["name"] for t in (a.get("tags") or {}).get("tag", [])][:5],
        "listeners": int(stats["listeners"]) if str(stats.get("listeners", "")).isdigit() else None,
        "similar": [x["name"] for x in (a.get("similar") or {}).get("artist", [])][:5],
        "url": a.get("url"),
    }


async def _wikipedia(client, name: str) -> dict | None:
    for title in (f"{name} (band)", f"{name} (musician)", name):
        r = await client.get("https://en.wikipedia.org/api/rest_v1/page/summary/" + title.replace(" ", "_"))
        if r.status_code != 200:
            continue
        d = r.json()
        if d.get("type") == "disambiguation" or not _MUSIC_RE.search((d.get("description") or "").lower()):
            continue
        return {
            "bio": d.get("extract") or "",
            "image": (d.get("originalimage") or d.get("thumbnail") or {}).get("source"),
            "description": d.get("description"),
            "url": (d.get("content_urls") or {}).get("desktop", {}).get("page"),
        }
    return None


async def _artist_info(client, name: str) -> dict | None:
    """Merge every source that answers. Bio priority: AudioDB > Last.fm >
    Wikipedia (longest useful one wins ties). None if nobody has a bio."""
    found = {}
    for src, fn in (("TheAudioDB", _audiodb), ("Last.fm", _lastfm), ("Wikipedia", _wikipedia)):
        try:
            hit = await fn(client, name)
        except Exception:
            hit = None
        if hit:
            found[src] = hit
    bio_src = next((s for s in found if len(found[s].get("bio") or "") >= 120), None)
    if not bio_src:
        return None
    merged: dict = {"bio": found[bio_src]["bio"], "bio_source": bio_src,
                    "links": {s: v.get("url") for s, v in found.items() if v.get("url")}}
    for src in found:                       # first non-empty value wins per field
        for k, v in found[src].items():
            if k not in ("bio", "url") and v and not merged.get(k):
                merged[k] = v
    return merged


def _your_stats(name: str) -> dict:
    """What your own Spotify history says about this artist (all years)."""
    if not STREAMS_CLEAN.exists():
        return {}
    try:
        df = pd.read_csv(STREAMS_CLEAN, usecols=["artist_name", "track_name", "ms_played", "played_at"])
        df = df[df["artist_name"].str.lower() == name.lower()]
        if df.empty:
            return {"minutes": 0}
        df["played_at"] = pd.to_datetime(df["played_at"], errors="coerce", utc=True)
        top = df.groupby("track_name")["ms_played"].sum().sort_values(ascending=False)
        return {
            "minutes": round(df["ms_played"].sum() / 60000),
            "plays": int(len(df)),
            "first_played": df["played_at"].min().strftime("%Y-%m-%d"),
            "top_track": top.index[0] if len(top) else None,
        }
    except Exception:
        return {}


def _upcoming_shows(name: str) -> list[dict]:
    try:
        from api.routers.shows import _load_shows
        df = _load_shows()
        if df.empty or len(name) < 4:
            return []
        hit = df[df["title"].str.lower().str.contains(re.escape(name.lower()), na=False)]
        return [
            {"date": d.strftime("%Y-%m-%d"), "title": t, "venue": v, "ticket_url": u}
            for d, t, v, u in zip(hit["date"], hit["title"], hit.get("venue_name", ""), hit.get("ticket_url", ""))
        ][:3]
    except Exception:
        return []


@router.get("/artist-of-the-day")
async def artist_of_the_day(reroll: int = 0):
    """A Tewnidge artist picked deterministically per day (reroll=N picks the
    Nth alternate), with a bio merged from AudioDB / Last.fm / Wikipedia.
    Artists with no bio anywhere are skipped. Cached to disk per day."""
    import random
    import httpx

    today = date.today()
    AOTD_CACHE.mkdir(parents=True, exist_ok=True)
    cache = AOTD_CACHE / f"{today.isoformat()}-{reroll}.json"
    if cache.exists():
        out = json.loads(cache.read_text())
    else:
        pool = _tewnidge_artists()
        if not pool:
            return {"available": False, "reason": "my_artists.json missing — run sync_playlist_artists.py"}
        rng = random.Random(today.toordinal() * 1000 + reroll)
        candidates = rng.sample(pool, k=min(8, len(pool)))
        out = None
        async with httpx.AsyncClient(timeout=10, headers=UA) as client:
            for name in candidates:
                info = await _artist_info(client, name)
                if info:
                    out = {"available": True, "artist": name, "date": today.isoformat(), **info}
                    break
        if out is None:
            return {"available": False, "reason": "No bio found for today's candidates"}
        cache.write_text(json.dumps(out))

    # Personal context is cheap and changes daily, so it's computed fresh, not cached
    out["you"] = _your_stats(out["artist"])
    out["shows"] = _upcoming_shows(out["artist"])
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
