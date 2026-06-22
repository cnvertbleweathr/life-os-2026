#!/usr/bin/env python3
"""
pipelines/kglw_pipeline.py — King Gizzard & The Lizard Wizard show data.

Ingests from kglw.net API v2 (no auth required):
  - Shows attended (manual log)
  - Full setlists for any show
  - Jam chart entries (notable versions)
  - Show links (YouTube recordings, audio, posters)
  - Song catalog
  - Venue data with lat/long (for the globe)

Tables created:
  kglw.shows           — all shows with venue, date, location, poster
  kglw.setlist_songs   — one row per song per show
  kglw.songs           — song catalog with gap data
  kglw.jamchart        — notable/legendary versions
  kglw.show_links      — YouTube and audio links per show
  kglw.venues          — venues with lat/long for globe
  kglw.attended        — shows you've personally attended (manual)

Usage:
  python pipelines/kglw_pipeline.py                    # full ingest
  python pipelines/kglw_pipeline.py --dry-run          # show what would run
  python pipelines/kglw_pipeline.py --shows-only       # only fetch recent shows
  python pipelines/kglw_pipeline.py --song "Magma"     # fetch one song's history
  python pipelines/kglw_pipeline.py --attended         # refresh attended list

Config:
  Set KGLW_ATTENDED_SHOW_IDS in .env as comma-separated show IDs
  e.g. KGLW_ATTENDED_SHOW_IDS=12345,67890,11111
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import dlt
from dotenv import load_dotenv

ROOT    = Path(__file__).resolve().parents[1]
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")

load_dotenv(ROOT / ".env")

API_BASE    = "https://kglw.net/api/v2"
YT_CHANNEL  = "UCExgBGdGYsIkzMwDj1WjpNA"  # King Gizzard official
SLEEP_S     = 0.2  # polite rate limiting between API calls


def api_get(endpoint: str, params: dict | None = None) -> Any:
    """Fetch from kglw.net API. Returns parsed JSON or None on error."""
    url = f"{API_BASE}/{endpoint}"
    if params:
        qs  = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ons-2026/1.0 (personal use)"}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  ⚠️  API error {endpoint}: {e}")
        return None


# ── DLT resources ─────────────────────────────────────────────────────────────

@dlt.resource(
    name="shows",
    write_disposition="merge",
    primary_key="show_id",
)
def kglw_shows() -> Iterator[dict]:
    """
    All KGLW shows from the API.

    Confirmed (2026-06-20): this endpoint has NO working pagination — it
    returns the complete dataset (1104 shows) in a single response,
    sorted oldest-first, regardless of page/per_page params sent.
    One fetch returns everything; do not loop pages.
    """
    data = api_get("shows")
    if not data or not data.get("data"):
        return

    shows = data["data"]
    for show in shows:
        yield {
            "show_id":       show.get("show_id"),
            "show_date":     show.get("showdate"),
            "show_time":     show.get("showtime"),
            "permalink":     show.get("permalink"),
            "artist_id":     show.get("artist_id"),
            "artist":        show.get("artist"),
            "show_title":    show.get("showtitle"),
            "venue_id":      show.get("venue_id"),
            "venue_name":    show.get("venuename"),
            "location":      show.get("location"),
            "city":          show.get("city"),
            "state":         show.get("state"),
            "country":       show.get("country"),
            "tour_id":       show.get("tour_id"),
            "tour_name":     show.get("tourname"),
            "show_year":     show.get("show_year"),
            "show_month":    show.get("show_month"),
            "show_day":      show.get("show_day"),
            "show_dayname":  show.get("show_dayname"),
            "show_tags":     json.dumps(show.get("show_tags") or []),
            "ingested_at":   datetime.now(timezone.utc).isoformat(),
        }

    print(f"  shows: {len(shows)} ingested")


@dlt.resource(
    name="setlist_songs",
    write_disposition="merge",
    primary_key=["show_id", "set_name", "position"],
)
def kglw_setlists(show_ids: list[int]) -> Iterator[dict]:
    """Setlists for a list of show IDs."""
    total = 0
    for show_id in show_ids:
        data = api_get(f"setlists/show/{show_id}")
        if not data:
            time.sleep(SLEEP_S)
            continue

        setlists = data if isinstance(data, list) else data.get("data", [])
        for sl in setlists:
            set_name = sl.get("label") or sl.get("name") or "Set"
            songs    = sl.get("songs") or []
            for pos, song in enumerate(songs, 1):
                yield {
                    "show_id":     show_id,
                    "set_name":    set_name,
                    "position":    pos,
                    "song_id":     song.get("id"),
                    "song_title":  song.get("title"),
                    "is_bustout":  bool(song.get("is_bustout", False)),
                    "gap":         song.get("gap"),
                    "notes":       song.get("notes"),
                    "jamchart_id": song.get("jamchart_id"),
                    "transition":  song.get("transition"),
                }
                total += 1

        time.sleep(SLEEP_S)

    print(f"  setlist_songs: {total} ingested")


@dlt.resource(
    name="songs",
    write_disposition="merge",
    primary_key="song_id",
)
def kglw_songs() -> Iterator[dict]:
    """
    Full song catalog.

    Confirmed real shape (2026-06-20): id/name/slug/isoriginal/original_artist.
    NO times_played, gap, or last_played_date fields exist on this endpoint —
    that data isn't exposed here and would need deriving from setlist data
    separately if needed for the gap tracker feature.
    """
    data = api_get("songs")
    if not data:
        return

    songs = data if isinstance(data, list) else data.get("data", [])
    for song in songs:
        yield {
            "song_id":         song.get("id"),
            "name":            song.get("name"),
            "slug":            song.get("slug"),
            "is_original":     bool(song.get("isoriginal")),
            "original_artist": song.get("original_artist"),
            "created_at":      song.get("created_at"),
            "updated_at":      song.get("updated_at"),
        }

    print(f"  songs: {len(songs)} ingested")


@dlt.resource(
    name="jamchart",
    write_disposition="merge",
    primary_key="uniqueid",
)
def kglw_jamchart() -> Iterator[dict]:
    """
    Notable/legendary versions from the jam chart.

    Confirmed real shape (2026-06-20): primary key is uniqueid (string).
    Field names are completely different from original assumptions —
    songname/jamchartnote/isrecommended, not song_title/description/rating.
    """
    data = api_get("jamcharts")
    if not data:
        return

    entries = data if isinstance(data, list) else data.get("data", [])
    for entry in entries:
        yield {
            "uniqueid":       entry.get("uniqueid"),
            "show_id":        entry.get("showid"),
            "song_id":        entry.get("song_id"),
            "song_name":      entry.get("songname"),
            "song_slug":      entry.get("song_slug"),
            "show_date":      entry.get("showdate"),
            "venue_name":     entry.get("venuename"),
            "venue_slug":     entry.get("venue_slug"),
            "city":           entry.get("city"),
            "state":          entry.get("state"),
            "country":        entry.get("country"),
            "set_number":     entry.get("setnumber"),
            "position":       entry.get("position"),
            "footnote":       entry.get("footnote"),
            "track_time":     entry.get("tracktime"),
            "jamchart_note":  entry.get("jamchartnote"),
            "is_recommended": bool(entry.get("isrecommended")),
            "permalink":      entry.get("permalink"),
        }

    print(f"  jamchart: {len(entries)} entries ingested")


@dlt.resource(
    name="show_links",
    write_disposition="merge",
    primary_key=["show_id", "url"],
)
def kglw_links(show_ids: list[int]) -> Iterator[dict]:
    """YouTube and audio recording links for shows."""
    total = 0
    for show_id in show_ids:
        data = api_get(f"links/show/{show_id}")
        if not data:
            time.sleep(SLEEP_S)
            continue

        links = data if isinstance(data, list) else data.get("data", [])
        for link in links:
            url  = link.get("url", "")
            kind = _classify_link(url)
            yield {
                "show_id":      show_id,
                "url":          url,
                "link_type":    link.get("type") or kind,
                "is_youtube":   "youtube.com" in url or "youtu.be" in url,
                "is_audio":     kind == "audio",
                "label":        link.get("label"),
                "source":       link.get("source"),
                "youtube_id":   _extract_youtube_id(url),
            }
            total += 1

        time.sleep(SLEEP_S)

    print(f"  show_links: {total} ingested")



@dlt.resource(
    name="venues",
    write_disposition="merge",
    primary_key="venue_id",
)
def kglw_venues() -> Iterator[dict]:
    """
    Venue catalog.

    Confirmed real shape (2026-06-20): venue_id, venuename, city, state,
    country (flat string), zip, capacity, slug. No lat/lng in the API —
    will need separate geocoding before the globe page can place pins.
    """
    data = api_get("venues")
    if not data:
        return

    venues = data if isinstance(data, list) else data.get("data", [])
    for v in venues:
        yield {
            "venue_id":  v.get("venue_id"),
            "name":      v.get("venuename"),
            "city":      v.get("city"),
            "state":     v.get("state"),
            "country":   v.get("country"),
            "zip":       v.get("zip"),
            "capacity":  v.get("capacity"),
            "slug":      v.get("slug"),
        }

    print(f"  venues: {len(venues)} ingested")


# ── Attended shows (manual) ───────────────────────────────────────────────────

@dlt.resource(
    name="attended",
    write_disposition="merge",
    primary_key="show_id",
)
def kglw_attended() -> Iterator[dict]:
    """Shows you personally attended. Set KGLW_ATTENDED_SHOW_IDS in .env."""
    ids_str = os.getenv("KGLW_ATTENDED_SHOW_IDS", "").strip()
    if not ids_str:
        print("  attended: KGLW_ATTENDED_SHOW_IDS not set — skipping")
        return

    show_ids = [int(x.strip()) for x in ids_str.split(",") if x.strip().isdigit()]
    for show_id in show_ids:
        data = api_get(f"shows/{show_id}")
        if not data:
            continue
        show  = data.get("data") or data
        venue = show.get("venue") or {}

        yield {
            "show_id":    show.get("id") or show_id,
            "show_date":  show.get("date"),
            "venue_name": venue.get("name"),
            "venue_city": venue.get("city"),
            "notes":      "",
            "attended_at": datetime.utcnow().isoformat(),
        }
        time.sleep(SLEEP_S)

    print(f"  attended: {len(show_ids)} shows")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_poster_url(show: dict) -> str | None:
    uploads = show.get("uploads") or []
    for u in uploads:
        if "poster" in str(u.get("type", "")).lower():
            return u.get("url")
    return None


def _extract_youtube_id(url: str) -> str | None:
    if "youtu.be/" in url:
        return url.split("youtu.be/")[-1].split("?")[0].strip()
    if "youtube.com/watch" in url and "v=" in url:
        return url.split("v=")[-1].split("&")[0].strip()
    if "youtube.com/live/" in url:
        return url.split("/live/")[-1].split("?")[0].strip()
    return None


def _classify_link(url: str) -> str:
    url_lower = url.lower()
    if "youtube" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    if any(x in url_lower for x in ["archive.org", "soundcloud", ".mp3", ".flac"]):
        return "audio"
    if "setlist" in url_lower:
        return "setlist"
    return "other"


def _get_recent_show_ids(limit: int = 100) -> list[int]:
    """
    Fetch IDs of the most recent N shows.

    Confirmed (2026-06-20): /shows has no working pagination — fetch once,
    sort by date client-side, take the most recent N. Field is show_id,
    not id.
    """
    data = api_get("shows")
    if not data or not data.get("data"):
        return []

    shows = data["data"]
    # Sort by show_date descending — API itself returns oldest-first
    shows_sorted = sorted(
        shows,
        key=lambda s: s.get("showdate") or "",
        reverse=True,
    )

    ids: list[int] = []
    for show in shows_sorted[:limit]:
        if sid := show.get("show_id"):
            ids.append(int(sid))

    return ids


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description="KGLW data pipeline")
    p.add_argument("--dry-run",     action="store_true")
    p.add_argument("--shows-only",  action="store_true", help="Only ingest shows and venues")
    p.add_argument("--song",        type=str, default=None, help="Fetch history for one song title")
    p.add_argument("--attended",    action="store_true", help="Refresh attended shows only")
    p.add_argument("--setlists",    action="store_true", help="Ingest setlists for recent 50 shows")
    p.add_argument("--max-pages",   type=int, default=20, help="Max show pages to fetch (50/page)")
    args = p.parse_args()

    print(f"KGLW Pipeline — {date.today()}")

    if args.dry_run:
        print("[dry-run] Would fetch:")
        print("  kglw.net/api/v2/shows (up to 1000 shows)")
        print("  kglw.net/api/v2/songs (full catalog)")
        print("  kglw.net/api/v2/jamcharts")
        print("  kglw.net/api/v2/venues")
        print("  Links for recent 100 shows")
        print("  Setlists for recent 50 shows")
        return 0

    pipeline = dlt.pipeline(
        pipeline_name="kglw",
        destination=dlt.destinations.duckdb(DB_PATH),
        dataset_name="kglw",
    )

    if args.attended:
        info = pipeline.run(kglw_attended())
        print(f"✅ Attended: {info}")
        return 0

    # Core catalog — always run
    resources = [
        kglw_shows(),
        kglw_songs(),
        kglw_jamchart(),
        kglw_venues(),
    ]

    if not args.shows_only:
        # Get recent show IDs for links + setlists
        print("  Fetching recent show IDs for links/setlists...")
        recent_ids = _get_recent_show_ids(limit=100)
        print(f"  Found {len(recent_ids)} recent show IDs")
        resources.append(kglw_links(recent_ids))

    if args.setlists or not args.shows_only:
        print("  Fetching setlists for recent 50 shows...")
        if 'recent_ids' not in dir():
            recent_ids = _get_recent_show_ids(limit=50)
        resources.append(kglw_setlists(recent_ids[:50]))

    resources.append(kglw_attended())

    info = pipeline.run(resources)
    print(f"\n✅ KGLW pipeline complete")
    print(f"   {info}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
