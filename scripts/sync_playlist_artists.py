#!/usr/bin/env python3
"""
sync_playlist_artists.py

Pulls all artists from Tewnidge and Deeds playlists and saves to
data/spotify/processed/my_artists.json.

Also cross-references against upcoming Denver shows and saves
data/shows/my_artist_shows.json — used by the Shows page and
Home page alert.

Usage:
  python scripts/sync_playlist_artists.py
"""

from __future__ import annotations

import json
import os
import csv
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

TEWNIDGE_ID = "7hxa1w4AzUjm6xgvU3Zf3x"
DEEDS_ID    = "6GP6ERcYJArZ7WWaC2g0Xv"

OUT_ARTISTS    = ROOT / "data" / "spotify" / "processed" / "my_artists.json"
OUT_MY_SHOWS   = ROOT / "data" / "shows" / "my_artist_shows.json"
AEG_CSV        = ROOT / "data" / "shows" / "processed" / "denver_events_upcoming.csv"
TM_CSV         = ROOT / "data" / "shows" / "processed" / "denver_events_ticketmaster.csv"
DENVER_TZ      = ZoneInfo("America/Denver")


def get_sp() -> spotipy.Spotify:
    return spotipy.Spotify(auth_manager=SpotifyOAuth(
        scope="playlist-read-private playlist-read-collaborative",
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
        cache_path=str(ROOT / "secrets" / ".spotify_cache"),
    ))


def get_playlist_artists(sp: spotipy.Spotify, playlist_id: str, label: str) -> set[str]:
    artists: set[str] = set()
    offset = 0
    while True:
        results = sp.playlist_tracks(
            playlist_id,
            offset=offset,
            limit=100,
            fields="items(track(artists(name))),next",
        )
        items = results.get("items", [])
        if not items:
            break
        for item in items:
            track = item.get("track") or {}
            for artist in (track.get("artists") or []):
                name = (artist.get("name") or "").strip()
                if name:
                    artists.add(name)
        offset += 100
        if not results.get("next"):
            break
    print(f"  {label}: {len(artists)} unique artists")
    return artists


def load_shows_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({k: (v or "").strip() for k, v in row.items()})
    return rows


def parse_dt(s: str):
    if not s:
        return None
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=DENVER_TZ)
        return dt.astimezone(DENVER_TZ)
    except Exception:
        return None


def normalize_artist(name: str) -> str:
    """Lowercase + strip for fuzzy matching."""
    return name.lower().strip()


def find_matching_shows(my_artists: set[str], show_rows: list[dict]) -> list[dict]:
    """Find shows where the title contains any of my artist names."""
    normalized = {normalize_artist(a): a for a in my_artists}
    now = datetime.now(tz=DENVER_TZ)
    matches = []
    seen_keys = set()

    for row in show_rows:
        title = row.get("title", "").lower()
        dt = parse_dt(row.get("start_datetime", ""))
        if dt is None or dt < now:
            continue

        matched_artist = None
        for norm, original in normalized.items():
            if norm in title:
                matched_artist = original
                break

        if not matched_artist:
            continue

        # Dedupe
        key = f"{row.get('title','').lower().strip()}|{row.get('venue_name','').lower().strip()}"
        if key in seen_keys:
            continue
        seen_keys.add(key)

        matches.append({
            "artist":         matched_artist,
            "title":          row.get("title", ""),
            "venue":          row.get("venue_name", ""),
            "start_datetime": row.get("start_datetime", ""),
            "date_str":       dt.strftime("%a, %b %d %Y"),
            "time_str":       dt.strftime("%I:%M %p").lstrip("0"),
            "event_url":      row.get("event_url", ""),
            "source":         row.get("source", ""),
        })

    matches.sort(key=lambda x: x["start_datetime"])
    return matches


def main() -> None:
    print("Syncing playlist artists...")
    sp = get_sp()

    tewnidge = get_playlist_artists(sp, TEWNIDGE_ID, "Tewnidge")
    deeds    = get_playlist_artists(sp, DEEDS_ID, "Deeds")
    combined = tewnidge | deeds
    print(f"  Combined: {len(combined)} unique artists")

    OUT_ARTISTS.parent.mkdir(parents=True, exist_ok=True)
    OUT_ARTISTS.write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "tewnidge_count": len(tewnidge),
        "deeds_count": len(deeds),
        "combined_count": len(combined),
        "artists": sorted(combined),
    }, indent=2))
    print(f"  Saved artists → {OUT_ARTISTS}")

    # Cross-reference against Denver shows
    print("\nCross-referencing against Denver shows...")
    show_rows = load_shows_csv(AEG_CSV) + load_shows_csv(TM_CSV)

    if not show_rows:
        print("  No shows data yet — run daily_sync --only aeg_events ticketmaster first")
        my_shows = []
    else:
        my_shows = find_matching_shows(combined, show_rows)
        print(f"  Found {len(my_shows)} shows featuring your artists:")
        for s in my_shows:
            print(f"    ⭐ {s['artist']} — {s['title']} @ {s['venue']} · {s['date_str']}")

    OUT_MY_SHOWS.parent.mkdir(parents=True, exist_ok=True)
    OUT_MY_SHOWS.write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "shows": my_shows,
    }, indent=2))
    print(f"  Saved my shows → {OUT_MY_SHOWS}")


if __name__ == "__main__":
    main()
