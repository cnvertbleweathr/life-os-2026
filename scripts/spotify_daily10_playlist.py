#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]

STREAMS_CSV = ROOT / "data" / "spotify" / "processed" / "streams_clean.csv"
OUT_DIR = ROOT / "data" / "spotify" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

URI_CACHE_CSV = OUT_DIR / "spotify_uri_cache.csv"
DAILY_AUDIT_CSV = OUT_DIR / "daily10_audit.csv"
LATEST_JSON = OUT_DIR / "daily10_latest.json"

TOKEN_CACHE = ROOT / "secrets" / "spotify_token_cache.json"


# --------------------
# Utilities
# --------------------
def norm(s: str) -> str:
    return " ".join((s or "").strip().split())


def norm_key(s: str) -> str:
    return norm(s).lower()

def spotify_safe_text(s: str, *, max_len: int) -> str:
    """
    Spotify playlist name/description limits are strict and errors are opaque.
    - Remove newlines
    - Collapse whitespace
    - Hard-truncate to max_len
    """
    s = (s or "").replace("\r", " ").replace("\n", " ")
    s = " ".join(s.split()).strip()
    if len(s) > max_len:
        s = s[: max_len - 1] + "…"
    return s

@dataclass(frozen=True)
class TrackKey:
    artist: str
    track: str


# --------------------
# Spotify Client
# --------------------
def build_spotify_client() -> spotipy.Spotify:
    client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback").strip()

    if not client_id or not client_secret:
        raise SystemExit("Missing SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET")

    scope = (
        "playlist-modify-private "
        "playlist-modify-public "
        "playlist-read-private "
        "playlist-read-collaborative "
        "ugc-image-upload"
    )

    TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)

    auth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=scope,
        cache_path=str(TOKEN_CACHE),
        open_browser=True,
    )
    return spotipy.Spotify(auth_manager=auth)


# --------------------
# History + Tewnidge
# --------------------
def read_listening_history(streams_csv: Path):
    totals = defaultdict(int)
    listened = set()

    with open(streams_csv, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            artist = norm(row.get("artist_name"))
            track = norm(row.get("track_name"))
            if not artist or not track:
                continue
            ms = int(row.get("ms_played") or 0)
            tk = TrackKey(artist, track)
            totals[tk] += ms
            listened.add((norm_key(artist), norm_key(track)))

    return totals, listened


def top_n_tracks(totals: Dict[TrackKey, int], n: int) -> List[TrackKey]:
    return [k for k, _ in sorted(totals.items(), key=lambda x: x[1], reverse=True)[:n]]


def fetch_tewnidge(sp: spotipy.Spotify, playlist_id: str):
    uris, artists = set(), []
    seen = set()

    offset = 0
    while True:
        page = sp.playlist_items(
            playlist_id,
            offset=offset,
            limit=100,
            fields="items(track(uri,artists(name))),next",
        )
        for it in page["items"]:
            tr = it["track"] or {}
            uri = tr.get("uri")
            arts = tr.get("artists") or []
            if uri:
                uris.add(uri)
            if arts:
                name = arts[0]["name"]
                key = name.lower()
                if key not in seen:
                    seen.add(key)
                    artists.append(name)
        if not page["next"]:
            break
        offset += 100

    return uris, artists


# --------------------
# Playlist Helpers
# --------------------
def find_existing_playlist_id(sp: spotipy.Spotify, name: str) -> Optional[str]:
    offset = 0
    while True:
        page = sp.current_user_playlists(limit=50, offset=offset)
        for pl in page["items"]:
            if pl["name"] == name:
                return pl["id"]
        if not page["next"]:
            break
        offset += 50
    return None


def replace_playlist_items(sp: spotipy.Spotify, pid: str, uris: List[str]) -> None:
    sp.playlist_replace_items(pid, uris[:100])
    for i in range(100, len(uris), 100):
        sp.playlist_add_items(pid, uris[i:i + 100])


def create_or_replace_playlist(sp, name, description, public, uris) -> str:
    pid = find_existing_playlist_id(sp, name)
    if pid:
        replace_playlist_items(sp, pid, uris)
        return pid

    user_id = sp.me()["id"]
    pl = sp.user_playlist_create(user_id, name=name, public=public, description=description)
    pid = pl["id"]
    replace_playlist_items(sp, pid, uris)
    return pid


# --------------------
# Latest Pointer + Decorate
# --------------------
def write_latest_pointer(date_str: str, playlist_id: str):
    payload = {
        "date": date_str,
        "playlist_id": playlist_id,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    LATEST_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote latest pointer: {LATEST_JSON}")


def maybe_run_decorate(date_str: str, playlist_id: str):
    script = ROOT / "scripts" / "spotify_daily10_decorate.py"
    if not script.exists():
        print("Decorate skipped: script missing")
        return
    if not os.getenv("OPENAI_API_KEY"):
        print("Decorate skipped: OPENAI_API_KEY missing")
        return

    cmd = [
        "python3",
        str(script),
        "--playlist-id",
        playlist_id,
        "--date",
        date_str,
    ]
    print("Running decorate:", " ".join(cmd))
    subprocess.run(cmd, cwd=str(ROOT))


# --------------------
# Main
# --------------------
def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    p.add_argument("--top-n", type=int, default=500)
    p.add_argument("--top-picks", type=int, default=5)
    p.add_argument("--b-picks", type=int, default=5)
    p.add_argument("--public", action="store_true")
    p.add_argument("--no-decorate", action="store_true")
    p.add_argument(
        "--tewnidge-playlist-id",
        default=os.getenv("SPOTIFY_TEWNIDGE_PLAYLIST_ID", "").strip(),
    )
    args = p.parse_args()

    if not args.tewnidge_playlist_id:
        raise SystemExit("Missing Tewnidge playlist id")

    sp = build_spotify_client()
    rng = random.Random(args.date)

    totals, listened_pairs = read_listening_history(STREAMS_CSV)
    top500 = top_n_tracks(totals, args.top_n)

    tewnidge_uris, tewnidge_artists = fetch_tewnidge(sp, args.tewnidge_playlist_id)

    bucket_a = rng.sample(top500, min(args.top_picks, len(top500)))
    bucket_b = rng.sample(tewnidge_artists, min(args.b_picks, len(tewnidge_artists)))

    final_uris = []
    for tk in bucket_a:
        q = f'track:"{tk.track}" artist:"{tk.artist}"'
        res = sp.search(q=q, type="track", limit=1)
        items = res["tracks"]["items"]
        if items:
            final_uris.append(items[0]["uri"])

    playlist_name = f"Daily 10 — {args.date}"
    description = (
        "Bucket A: 5 random tracks from my top 500 most-played.\n"
        "Bucket B: 5 unheard tracks by artists from Tewnidge."
    )

    playlist_name = spotify_safe_text(f"Daily 10 — {args.date}", max_len=100)

    description = spotify_safe_text(
        description,
        max_len=300,
        )

    # Optional debug:
    print(f"Playlist name length: {len(playlist_name)}")
    print(f"Description length: {len(description)}")


    playlist_id = create_or_replace_playlist(
        sp, playlist_name, description, args.public, final_uris
    )

    write_latest_pointer(args.date, playlist_id)

    print(f"Created/Replaced playlist: {playlist_name}")
    print(f"DAILY10_PLAYLIST_ID={playlist_id}")

    if not args.no_decorate:
        maybe_run_decorate(args.date, playlist_id)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
