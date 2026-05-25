    #!/usr/bin/env python3
"""
show_radar.py

Given your Tewnidge + Deeds artists, asks GPT-4o to suggest similar
artists likely to appeal to you. Cross-references those against upcoming
Denver shows to surface ones you might not know about.

Saves to data/shows/radar_shows.json — displayed on the Shows page
and Home page.

Usage:
  python scripts/show_radar.py
"""

from __future__ import annotations

import json
import os
import csv
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

MY_ARTISTS_PATH = ROOT / "data" / "spotify" / "processed" / "my_artists.json"
AEG_CSV         = ROOT / "data" / "shows" / "processed" / "denver_events_upcoming.csv"
TM_CSV          = ROOT / "data" / "shows" / "processed" / "denver_events_ticketmaster.csv"
MY_SHOWS_PATH   = ROOT / "data" / "shows" / "my_artist_shows.json"
OUT_PATH        = ROOT / "data" / "shows" / "radar_shows.json"
DENVER_TZ       = ZoneInfo("America/Denver")


def call_gpt(prompt: str, max_tokens: int = 800) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json={
            "model": "gpt-4o",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def load_shows() -> list[dict]:
    rows = []
    for path in [AEG_CSV, TM_CSV]:
        if not path.exists():
            continue
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


def get_similar_artists(my_artists: list[str]) -> list[str]:
    """Ask GPT to suggest similar artists based on a sample of your library."""
    # Sample top artists to keep prompt manageable
    sample = my_artists[:80]
    artists_text = "\n".join(f"- {a}" for a in sample)

    prompt = f"""Here is a sample of someone's music library (from their Spotify playlists):

{artists_text}

Based on this taste profile, suggest 40 artists they would likely enjoy that are NOT already in this list.
Focus on:
- Similar genre/sound to what's already there
- Artists who frequently tour in the US
- Mix of established and emerging acts

Respond with ONLY a JSON array of artist name strings. No explanation.
Example: ["Artist One", "Artist Two", ...]"""

    content = call_gpt(prompt, max_tokens=600)
    content = content.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(content)
    except Exception:
        return []


def find_radar_shows(
    similar_artists: list[str],
    all_shows: list[dict],
    my_artists_lower: set[str],
) -> list[dict]:
    """Find shows for similar artists that aren't already in my_artists."""
    now = datetime.now(tz=DENVER_TZ)
    similar_lower = {a.lower().strip(): a for a in similar_artists}

    matches = []
    seen = set()

    for show in all_shows:
        title = show.get("title", "").lower()
        dt = parse_dt(show.get("start_datetime", ""))
        if dt is None or dt < now:
            continue

        # Skip if already a known artist (already in my_artist_shows)
        if any(a in title for a in my_artists_lower):
            continue

        matched_artist = None
        for norm, original in similar_lower.items():
            if norm in title:
                matched_artist = original
                break

        if not matched_artist:
            continue

        key = title.strip() + "|" + show.get("venue_name", "").lower().strip()
        if key in seen:
            continue
        seen.add(key)

        matches.append({
            "artist":         matched_artist,
            "title":          show.get("title", ""),
            "venue":          show.get("venue_name", ""),
            "start_datetime": show.get("start_datetime", ""),
            "date_str":       dt.strftime("%a, %b %d %Y"),
            "time_str":       dt.strftime("%I:%M %p").lstrip("0"),
            "event_url":      show.get("event_url", ""),
            "source":         show.get("source", ""),
            "radar": True,
        })

    matches.sort(key=lambda x: x["start_datetime"])
    return matches


def main() -> None:
    if not MY_ARTISTS_PATH.exists():
        raise SystemExit("No my_artists.json. Run `python scripts/sync_playlist_artists.py` first.")

    my_artists_data = json.loads(MY_ARTISTS_PATH.read_text())
    my_artists      = my_artists_data.get("artists", [])
    my_artists_lower = {a.lower().strip() for a in my_artists}

    print(f"Loaded {len(my_artists)} artists from Tewnidge + Deeds")

    print("Asking GPT for similar artists...")
    similar = get_similar_artists(my_artists)
    print(f"  Got {len(similar)} similar artist suggestions")

    print("Cross-referencing with Denver shows...")
    all_shows = load_shows()
    radar = find_radar_shows(similar, all_shows, my_artists_lower)

    print(f"  Found {len(radar)} radar shows:")
    for s in radar:
        print(f"    📡 {s['artist']} — {s['title']} @ {s['venue']} · {s['date_str']}")

    output = {
        "generated_at":   datetime.now(timezone.utc).isoformat(),
        "similar_artists": similar,
        "radar_shows":     radar,
    }

    OUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"\nSaved to {OUT_PATH}")


if __name__ == "__main__":
    main()
