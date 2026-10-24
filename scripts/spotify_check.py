#!/usr/bin/env python3
"""
spotify_check.py — is ONS's Spotify access still working after the 2026 API changes?

Read-only. Checks, with the same token cache the daily sync uses:
  1. the token refreshes without a browser (the 9am sync can't open one)
  2. who you're logged in as
  3. for Tewnidge, Deeds and the Daily 10 playlist: owner, whether you own
     or collaborate on it, and whether its items are readable — in the old
     (`track`) or new (`item`) shape
  4. that search still answers (Bucket A/B depend on it)

Usage:  python scripts/spotify_check.py
Exit 1 if anything the daily sync depends on is broken.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from spotify_compat import PlaylistNotReadable, entry_track, iter_playlist_tracks  # noqa: E402

load_dotenv(ROOT / ".env")

TOKEN_CACHE = ROOT / "secrets" / "spotify_token_cache.json"   # spotify_daily10_playlist.py
SCOPE = ("playlist-modify-private playlist-modify-public playlist-read-private "
         "playlist-read-collaborative ugc-image-upload")
PLAYLISTS = {
    "Tewnidge": os.getenv("SPOTIFY_TEWNIDGE_PLAYLIST_ID", "").strip() or "7hxa1w4AzUjm6xgvU3Zf3x",
    "Deeds": os.getenv("SPOTIFY_DEEDS_PLAYLIST_ID", "").strip() or "6GP6ERcYJArZ7WWaC2g0Xv",
}

problems = 0


def line(ok: bool | None, label: str, detail: str = "") -> None:
    global problems
    mark = {True: "✓", False: "✗", None: "!"}[ok]
    if ok is False:
        problems += 1
    print(f"  {mark}  {label:<26} {detail}")


def main() -> int:
    print("Spotify access check\n")
    if not TOKEN_CACHE.exists():
        line(False, "token cache", f"{TOKEN_CACHE} missing — run the Daily 10 script once interactively")
        return 1

    auth = SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback"),
        scope=SCOPE, cache_path=str(TOKEN_CACHE), open_browser=False,
    )
    try:
        token = auth.get_cached_token()       # refreshes if expired; never opens a browser
    except Exception as e:                    # noqa: BLE001
        token = None
        line(False, "token refresh", repr(e))
    if not token:
        line(False, "token refresh", "no valid cached token; re-authorise interactively")
        return 1
    line(True, "token refresh", "cached token valid / refreshed")

    sp = spotipy.Spotify(auth_manager=auth, requests_timeout=30, retries=3)
    try:
        me = sp.current_user()
    except spotipy.SpotifyException as e:
        line(False, "current user", f"HTTP {e.http_status}: {e.msg}")
        return 1
    line(True, "logged in as", f"{me.get('display_name')} ({me['id']})")

    daily10 = None
    try:
        daily10 = json.loads((ROOT / "data/spotify/processed/daily10_latest.json").read_text()).get("playlist_id")
    except (OSError, ValueError):
        pass
    targets = dict(PLAYLISTS, **({"Daily 10": daily10} if daily10 else {}))

    for label, pid in targets.items():
        print(f"\n  {label} ({pid})")
        try:
            meta = sp.playlist(pid)
        except spotipy.SpotifyException as e:
            line(False, "metadata", f"HTTP {e.http_status}: {e.msg}")
            continue
        owner = (meta.get("owner") or {}).get("id")
        mine = owner == me["id"]
        collab = bool(meta.get("collaborative"))
        line(mine or collab, "owner", f"{owner}{' (you)' if mine else ''}"
             f"{', collaborative' if collab else ''}")
        if not (mine or collab):
            print("       Spotify no longer returns items for playlists you only follow. Copy it to a")
            print("       playlist you own (Spotify app: select all → Add to playlist → New playlist)")
            print(f"       and set SPOTIFY_{label.upper().replace(' ', '')}_PLAYLIST_ID in .env.")

        try:
            raw = sp.playlist_items(pid, limit=5)
            entries = raw.get("items") or []
            shape = ("new (item)" if any("item" in e for e in entries)
                     else "old (track)" if any("track" in e for e in entries) else "empty")
            tracks = list(iter_playlist_tracks(sp, pid))
            artists = {(t.get("artists") or [{}])[0].get("name") for t in tracks} - {None}
            line(bool(tracks), "items", f"{len(tracks)} tracks, {len(artists)} artists, shape: {shape}")
            if entries and not entry_track(entries[0]):
                line(False, "entry format", f"unrecognised keys: {sorted(entries[0])}")
        except PlaylistNotReadable as e:
            line(False, "items", str(e))
        except spotipy.SpotifyException as e:
            line(False, "items", f"HTTP {e.http_status}: {e.msg}")

    print()
    try:
        res = sp.search(q='artist:"King Gizzard"', type="track", limit=10)
        line(bool(res["tracks"]["items"]), "search", f"{len(res['tracks']['items'])} results (max 10 in Dev Mode)")
    except spotipy.SpotifyException as e:
        line(False, "search", f"HTTP {e.http_status}: {e.msg}")

    print(f"\n{'All good.' if not problems else f'{problems} problem(s) found.'}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
