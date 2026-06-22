#!/usr/bin/env python3
"""
pipelines/kglw_youtube_pipeline.py — King Gizzard & The Lizard Wizard
official YouTube channel video catalog.

Why this exists: kglw.net's own `links/show/{id}` endpoint is currently
broken server-side (confirmed 2026-06-22 — every call returns HTTP 200
with a raw PHP PDOException as the body: "Column not found: 1054
Unknown column 'show'"). Rather than depend on a third-party API that's
down, this pipeline ingests the official YouTube channel's upload
history directly. Matching videos to specific shows (kglw.shows) is a
separate, deliberately NOT-yet-built step — see the bottom of this file
for why.

Uses the YouTube Data API v3 (https://developers.google.com/youtube/v3).
Requires YOUTUBE_API_KEY in .env.

Quota-efficient by design: fetches the channel's "uploads" playlist ID
once (1 unit), then paginates through playlistItems.list (~1-5 units
per page of 50 videos) rather than the much more expensive search.list
(100 units per call). A full channel refresh of even several hundred
videos should cost well under 100 units total — a tiny fraction of the
10,000/day free quota.

Tables created:
  kglw_youtube.videos — video_id, title, published_at, description,
                        duration, view_count, channel_id

Usage:
  python pipelines/kglw_youtube_pipeline.py                # full ingest
  python pipelines/kglw_youtube_pipeline.py --dry-run       # show what would run
  python pipelines/kglw_youtube_pipeline.py --limit 50      # fetch only the first N videos (testing)

Config:
  Set YOUTUBE_API_KEY in .env
"""
from __future__ import annotations

import argparse
import os
import time
from datetime import date
from pathlib import Path
from typing import Any, Iterator

import dlt
import requests
from dotenv import load_dotenv

ROOT    = Path(__file__).resolve().parents[1]
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")

load_dotenv(ROOT / ".env")

API_KEY  = os.getenv("YOUTUBE_API_KEY", "").strip()
API_BASE = "https://www.googleapis.com/youtube/v3"

# King Gizzard & The Lizard Wizard's official channel.
# Confirmed handle from the person's own message: @KingGizzardAndTheLizardWizard
# Resolved to a channel ID once at runtime (see _resolve_channel_id) rather
# than hardcoded, since handles can be re-pointed but channel IDs are stable.
CHANNEL_HANDLE = "KingGizzardAndTheLizardWizard"

SLEEP_S = 0.3  # polite pacing between paginated calls


def _api_get(path: str, params: dict) -> dict | None:
    """
    GET against the YouTube Data API v3. Returns parsed JSON or None
    on error. Logs the real HTTP status and response body on failure —
    same discipline as the kglw_pipeline.py fix, learned the hard way
    when a generic error message hid a real server-side bug for days.
    """
    if not API_KEY:
        print("  ⚠️  YOUTUBE_API_KEY not set in .env — cannot fetch from YouTube API")
        return None

    url = f"{API_BASE}/{path}"
    params = {**params, "key": API_KEY}

    try:
        resp = requests.get(url, params=params, timeout=15)
    except requests.RequestException as e:
        print(f"  ⚠️  YouTube API connection failed for {path}: {e}")
        return None

    if resp.status_code != 200:
        snippet = resp.text[:300].replace("\n", " ")
        print(f"  ⚠️  YouTube API error {path}: HTTP {resp.status_code} — {snippet!r}")
        return None

    try:
        return resp.json()
    except ValueError:
        print(f"  ⚠️  YouTube API error {path}: HTTP 200 but non-JSON body")
        return None


def _resolve_channel_id(handle: str) -> str | None:
    """
    Resolves a @handle to a stable channel ID via the channels.list
    forHandle parameter (the current, correct way to do this — the old
    approach of scraping the channel page for the ID is unnecessary and
    fragile by comparison).
    """
    data = _api_get("channels", {"part": "id,contentDetails", "forHandle": handle})
    if not data or not data.get("items"):
        print(f"  ⚠️  Could not resolve channel handle @{handle} — check the handle is correct")
        return None
    return data["items"][0]


def _get_uploads_playlist_id(channel_item: dict) -> str | None:
    """Every channel has an auto-generated 'uploads' playlist containing
    every public video, in upload order. This is the cheap way to list
    all videos — far cheaper than search.list."""
    try:
        return channel_item["contentDetails"]["relatedPlaylists"]["uploads"]
    except KeyError:
        return None


@dlt.resource(
    name="videos",
    write_disposition="merge",
    primary_key="video_id",
)
def kglw_youtube_videos(limit: int | None = None) -> Iterator[dict]:
    """
    All videos from the official KGLW YouTube channel, oldest fields
    first as returned by the uploads playlist (which YouTube orders
    newest-first by default).

    NOTE: this resource only ingests video metadata (title, description,
    publish date, etc.) — it does NOT attempt to match videos to shows
    in kglw.shows. See the bottom of this file for why that's a
    deliberately separate, not-yet-built step.
    """
    channel = _resolve_channel_id(CHANNEL_HANDLE)
    if not channel:
        return

    uploads_playlist_id = _get_uploads_playlist_id(channel)
    if not uploads_playlist_id:
        print("  ⚠️  Could not find uploads playlist for channel — aborting")
        return

    total_fetched = 0
    next_page_token: str | None = None

    while True:
        params = {
            "part": "snippet,contentDetails",
            "playlistId": uploads_playlist_id,
            "maxResults": 50,
        }
        if next_page_token:
            params["pageToken"] = next_page_token

        data = _api_get("playlistItems", params)
        if not data:
            break

        items = data.get("items", [])
        if not items:
            break

        # playlistItems gives title/description/publishedAt but not
        # duration/view_count — those need a separate videos.list call.
        # Batch up to 50 video IDs per call (1 unit per call regardless
        # of how many IDs, up to 50) rather than one call per video.
        video_ids = [it["contentDetails"]["videoId"] for it in items]
        details = _api_get("videos", {
            "part": "contentDetails,statistics",
            "id": ",".join(video_ids),
        })
        details_by_id = {d["id"]: d for d in (details.get("items", []) if details else [])}

        for it in items:
            vid = it["contentDetails"]["videoId"]
            snippet = it["snippet"]
            detail = details_by_id.get(vid, {})

            yield {
                "video_id":     vid,
                "title":        snippet.get("title"),
                "description":  snippet.get("description"),
                "published_at": it["contentDetails"].get("videoPublishedAt") or snippet.get("publishedAt"),
                "channel_id":   snippet.get("channelId"),
                "duration":     detail.get("contentDetails", {}).get("duration"),
                "view_count":   detail.get("statistics", {}).get("viewCount"),
            }
            total_fetched += 1

            if limit and total_fetched >= limit:
                print(f"  videos: hit --limit {limit}, stopping")
                return

        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break

        time.sleep(SLEEP_S)

    print(f"  videos: {total_fetched} ingested")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description="KGLW YouTube channel pipeline")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=None, help="Only fetch the first N videos (for testing)")
    args = p.parse_args()

    print(f"KGLW YouTube Pipeline — {date.today()}")

    if args.dry_run:
        print("[dry-run] Would fetch:")
        print(f"  Resolve @{CHANNEL_HANDLE} to a channel ID")
        print("  Fetch the channel's uploads playlist (all videos, paginated)")
        print("  For each video: title, description, publish date, duration, view count")
        if args.limit:
            print(f"  (limited to first {args.limit} videos)")
        return 0

    if not API_KEY:
        print("ERROR: YOUTUBE_API_KEY not set in .env — nothing to do.")
        return 1

    pipeline = dlt.pipeline(
        pipeline_name="kglw_youtube",
        destination=dlt.destinations.duckdb(DB_PATH),
        dataset_name="kglw_youtube",
    )

    info = pipeline.run(kglw_youtube_videos(limit=args.limit))
    print(f"\n✅ KGLW YouTube pipeline complete")
    print(f"   {info}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ─────────────────────────────────────────────────────────────────────────────
# Why show-matching isn't built yet
# ─────────────────────────────────────────────────────────────────────────────
#
# Matching a video to a specific show in kglw.shows requires knowing the
# actual title format KGLW uses for live recordings. I haven't seen real
# titles from this channel — youtube.com isn't in my sandbox's network
# allowlist, so I can't browse it myself, and I don't want to guess at a
# parsing scheme (regex for venue/date patterns) against a format I've
# never actually seen. Guessing here risks the same mistake as assuming
# kglw.net's API shape without checking it.
#
# Next step: run this pipeline once with --limit 20, then run:
#   python3 -c "
#   import duckdb
#   con = duckdb.connect('data/warehouse/ons.duckdb')
#   for row in con.execute('SELECT title, published_at FROM kglw_youtube.videos ORDER BY published_at DESC LIMIT 20').fetchall():
#       print(row)
#   "
# and share the real titles. Once the actual format is visible, the
# matching step (likely a dbt model joining kglw.shows to
# kglw_youtube.videos on parsed date + fuzzy venue name) can be written
# against real data instead of a guess.
