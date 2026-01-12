#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import random
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

URI_CACHE_CSV = OUT_DIR / "spotify_uri_cache.csv"       # query_key,track_uri
DAILY_AUDIT_CSV = OUT_DIR / "daily10_audit.csv"         # audit output
TOKEN_CACHE = ROOT / "secrets" / "spotify_token_cache.json"


def norm(s: str) -> str:
    return " ".join((s or "").strip().split())


def norm_key(s: str) -> str:
    return norm(s).lower()


@dataclass(frozen=True)
class TrackKey:
    artist: str
    track: str


def load_uri_cache(path: Path) -> Dict[str, str]:
    cache: Dict[str, str] = {}
    if not path.exists():
        return cache
    with open(path, "r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            k = (row.get("query_key") or "").strip()
            v = (row.get("track_uri") or "").strip()
            if k and v:
                cache[k] = v
    return cache


def append_uri_cache(path: Path, items: Dict[str, str]) -> None:
    if not items:
        return
    exists = path.exists()
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["query_key", "track_uri"])
        if not exists:
            w.writeheader()
        for k, v in items.items():
            w.writerow({"query_key": k, "track_uri": v})


def build_spotify_client() -> spotipy.Spotify:

    client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback").strip()

    if not client_id or not client_secret:
        raise SystemExit("Missing SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET in .env")

    scope = "playlist-modify-private playlist-modify-public playlist-read-private playlist-read-collaborative"
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


def read_listening_history(streams_csv: Path) -> Tuple[Dict[TrackKey, int], Set[Tuple[str, str]]]:
    """
    Returns:
      - totals: dict TrackKey -> total_ms_played
      - listened_pairs: set of (artist_lower, track_lower) seen in history
    """
    if not streams_csv.exists():
        raise SystemExit(f"Missing {streams_csv}. Run spotify_ingest_streaming.py first.")

    totals: Dict[TrackKey, int] = defaultdict(int)
    listened_pairs: Set[Tuple[str, str]] = set()

    with open(streams_csv, "r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            artist = norm(row.get("artist_name") or "")
            track = norm(row.get("track_name") or "")
            if not artist or not track:
                continue

            try:
                ms = int(row.get("ms_played") or 0)
            except Exception:
                ms = 0

            tk = TrackKey(artist=artist, track=track)
            totals[tk] += ms
            listened_pairs.add((norm_key(artist), norm_key(track)))

    return totals, listened_pairs


def top_n_tracks(totals: Dict[TrackKey, int], n: int) -> List[TrackKey]:
    ranked = sorted(totals.items(), key=lambda x: x[1], reverse=True)
    return [k for k, _ in ranked[:n]]


def fetch_tewnidge(sp: spotipy.Spotify, playlist_id: str) -> Tuple[Set[str], List[str]]:
    """
    Returns:
      - tewnidge_track_uris: all track URIs in playlist
      - tewnidge_artists: unique primary-artist names in playlist (display-case)
    """
    tewnidge_track_uris: Set[str] = set()
    artists_seen: Set[str] = set()
    tewnidge_artists: List[str] = []

    offset = 0
    limit = 100
    while True:
        page = sp.playlist_items(
            playlist_id,
            offset=offset,
            limit=limit,
            additional_types=["track"],
            fields="items(track(uri,name,artists(name))),next",
        )
        for it in page.get("items") or []:
            tr = it.get("track") or {}
            uri = (tr.get("uri") or "").strip()
            artists = tr.get("artists") or []
            artist = ((artists[0].get("name") if artists else "") or "").strip()

            if uri:
                tewnidge_track_uris.add(uri)
            if artist:
                key = artist.lower()
                if key not in artists_seen:
                    artists_seen.add(key)
                    tewnidge_artists.append(artist)

        if page.get("next") is None:
            break
        offset += limit

    return tewnidge_track_uris, tewnidge_artists


def search_tracks_by_artist(
    sp: spotipy.Spotify,
    artist_name: str,
    max_pages: int = 6,
    page_size: int = 50,
) -> List[dict]:
    """
    Returns raw Spotify 'track' objects from search results for artist:"..."
    """
    results: List[dict] = []
    q = f'artist:"{artist_name}"'
    for page in range(max_pages):
        res = sp.search(q=q, type="track", limit=page_size, offset=page * page_size)
        items = ((res.get("tracks") or {}).get("items") or [])
        if not items:
            break
        results.extend(items)
        # If fewer than page_size returned, no more pages
        if len(items) < page_size:
            break
    return results


def pick_unheard_non_tewnidge_track_uri_for_artist(
    sp: spotipy.Spotify,
    artist_name: str,
    tewnidge_track_uris: Set[str],
    listened_pairs: Set[Tuple[str, str]],
    rng: random.Random,
    max_pages: int = 6,
) -> Optional[Tuple[str, str]]:
    """
    Returns (track_uri, track_name) meeting constraints:
      - primary artist matches artist_name
      - uri NOT in tewnidge playlist
      - (artist, track) NOT in listened_pairs (ever)
    """
    artist_lower = artist_name.lower()
    items = search_tracks_by_artist(sp, artist_name, max_pages=max_pages)

    candidates: List[Tuple[str, str]] = []
    for tr in items:
        uri = (tr.get("uri") or "").strip()
        name = norm(tr.get("name") or "")
        artists = tr.get("artists") or []
        primary = ((artists[0].get("name") if artists else "") or "").strip()
        if not uri or not name or not primary:
            continue

        # strict primary-artist match
        if primary.lower() != artist_lower:
            continue

        if uri in tewnidge_track_uris:
            continue

        if (artist_lower, norm_key(name)) in listened_pairs:
            continue

        candidates.append((uri, name))

    if not candidates:
        return None

    return rng.choice(candidates)


def find_existing_playlist_id(sp: spotipy.Spotify, playlist_name: str) -> Optional[str]:
    """
    Searches current user's playlists for a playlist with an exact name match.
    Returns playlist id if found, else None.
    """
    offset = 0
    limit = 50
    while True:
        page = sp.current_user_playlists(limit=limit, offset=offset)
        items = page.get("items") or []
        for pl in items:
            if (pl.get("name") or "") == playlist_name:
                return pl.get("id")
        if page.get("next") is None:
            break
        offset += limit
    return None


def replace_playlist_items(sp: spotipy.Spotify, playlist_id: str, uris: List[str]) -> None:
    """
    Replaces playlist contents with provided URIs (chunked).
    """
    if not uris:
        return
    sp.playlist_replace_items(playlist_id, uris[:100])
    for i in range(100, len(uris), 100):
        sp.playlist_add_items(playlist_id, uris[i : i + 100])


def create_or_replace_playlist(
    sp: spotipy.Spotify,
    playlist_name: str,
    description: str,
    public: bool,
    uris: List[str],
) -> str:
    """
    Idempotent:
      - If playlist with same name exists: replace its items
      - Else: create new playlist and add items
    Returns playlist id.
    """
    existing_id = find_existing_playlist_id(sp, playlist_name)
    if existing_id:
        replace_playlist_items(sp, existing_id, uris)
        return existing_id

    me = sp.me()
    user_id = me["id"]
    pl = sp.user_playlist_create(
        user=user_id,
        name=playlist_name,
        public=public,
        description=description,
    )
    pid = pl["id"]
    replace_playlist_items(sp, pid, uris)
    return pid


def resolve_trackkey_to_uri(
    sp: spotipy.Spotify,
    tk: TrackKey,
    uri_cache: Dict[str, str],
    new_cache: Dict[str, str],
) -> Optional[str]:
    """
    Resolve TrackKey -> Spotify track URI via search, caching by query_key.
    """
    cache_key = f"{tk.artist}|||{tk.track}".lower()
    if cache_key in uri_cache:
        return uri_cache[cache_key]

    q = f'track:"{tk.track}" artist:"{tk.artist}"'
    res = sp.search(q=q, type="track", limit=5)
    items = ((res.get("tracks") or {}).get("items") or [])
    if not items:
        return None

    uri = (items[0].get("uri") or "").strip()
    if not uri:
        return None

    uri_cache[cache_key] = uri
    new_cache[cache_key] = uri
    return uri


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    p.add_argument("--top-n", type=int, default=500)
    p.add_argument("--top-picks", type=int, default=5)
    p.add_argument("--b-picks", type=int, default=5)
    p.add_argument("--public", action="store_true", help="Create playlist as public (default private).")
    p.add_argument(
        "--tewnidge-playlist-id",
        default=os.getenv("SPOTIFY_TEWNIDGE_PLAYLIST_ID", "").strip(),
        help="Spotify playlist ID for Tewnidge (or set SPOTIFY_TEWNIDGE_PLAYLIST_ID in .env).",
    )
    args = p.parse_args()

    if not args.tewnidge_playlist_id:
        raise SystemExit("Missing --tewnidge-playlist-id (or SPOTIFY_TEWNIDGE_PLAYLIST_ID in .env).")

    sp = build_spotify_client()

    # Seeded RNG so "Daily 10 — YYYY-MM-DD" is stable if you rerun same day
    rng = random.Random(args.date)

    # Load listening history
    totals, listened_pairs = read_listening_history(STREAMS_CSV)
    top500 = top_n_tracks(totals, n=args.top_n)
    if len(top500) < args.top_picks:
        print(f"Warning: only {len(top500)} tracks available for top {args.top_n}.", file=sys.stderr)

    # Load Tewnidge artists + tracks
    tewnidge_track_uris, tewnidge_artists = fetch_tewnidge(sp, args.tewnidge_playlist_id)
    if len(tewnidge_artists) < args.b_picks:
        print(f"Warning: only {len(tewnidge_artists)} unique artists found in Tewnidge.", file=sys.stderr)

    # ----------------------------
    # Bucket A: 5 from top 500
    # ----------------------------
    bucket_a_keys = rng.sample(top500, k=min(args.top_picks, len(top500)))

    # Resolve Bucket A to URIs
    uri_cache = load_uri_cache(URI_CACHE_CSV)
    new_cache: Dict[str, str] = {}
    bucket_a_uris: List[str] = []
    bucket_a_audit: List[Tuple[str, str, str]] = []  # (artist, track, uri)

    for tk in bucket_a_keys:
        uri = resolve_trackkey_to_uri(sp, tk, uri_cache, new_cache)
        if uri:
            bucket_a_uris.append(uri)
            bucket_a_audit.append((tk.artist, tk.track, uri))
        else:
            bucket_a_audit.append((tk.artist, tk.track, ""))

    # ----------------------------
    # Bucket B: 5 random artists from Tewnidge
    # For each: pick 1 track by that artist that:
    #  - is NOT on Tewnidge
    #  - is NOT ever listened (per export)
    # ----------------------------
    bucket_b_uris: List[str] = []
    bucket_b_audit: List[Tuple[str, str, str]] = []  # (artist, track, uri)

    # Start with 5 random artists, but we may need to try more to fill
    attempted_artists: Set[str] = set()

    def try_artist(artist: str) -> bool:
        attempted_artists.add(artist.lower())
        pick = pick_unheard_non_tewnidge_track_uri_for_artist(
            sp=sp,
            artist_name=artist,
            tewnidge_track_uris=tewnidge_track_uris,
            listened_pairs=listened_pairs,
            rng=rng,
            max_pages=8,
        )
        if not pick:
            return False
        uri, track_name = pick
        if uri in bucket_b_uris:
            return False
        bucket_b_uris.append(uri)
        bucket_b_audit.append((artist, track_name, uri))
        return True

    # First pass: 5 random artists
    initial_artists = rng.sample(tewnidge_artists, k=min(args.b_picks, len(tewnidge_artists)))
    for a in initial_artists:
        if len(bucket_b_uris) >= args.b_picks:
            break
        try_artist(a)

    # Fill pass: keep sampling artists until we fill or hit attempt cap
    attempt_cap = 120
    attempts = 0
    while len(bucket_b_uris) < args.b_picks and attempts < attempt_cap:
        attempts += 1
        a = rng.choice(tewnidge_artists)
        if a.lower() in attempted_artists:
            continue
        try_artist(a)

    if len(bucket_b_uris) < args.b_picks:
        print(
            f"Warning: Only found {len(bucket_b_uris)}/{args.b_picks} Bucket B tracks "
            f"meeting constraints (not on Tewnidge + never listened).",
            file=sys.stderr,
        )

    # Persist cache updates
    if new_cache:
        append_uri_cache(URI_CACHE_CSV, new_cache)

    # Combine and create playlist
    # Keep order: top500 first, then new/unheard
    final_uris = [u for u in bucket_a_uris if u] + [u for u in bucket_b_uris if u]
    # Enforce uniqueness
    seen = set()
    final_uris = [u for u in final_uris if not (u in seen or seen.add(u))]

    if not final_uris:
        raise SystemExit("No URIs resolved; cannot create playlist.")

    playlist_name = f"Daily 10 — {args.date}"
    description = (
        "Bucket A: 5 random tracks from my top 500 most-played (Spotify export). "
        "Bucket B: 5 tracks by artists from my Tewnidge playlist, filtered to tracks "
        "not on Tewnidge and never played (Spotify export)."
    )

    playlist_id = create_or_replace_playlist(
        sp=sp,
        playlist_name=playlist_name,
        description=description,
        public=bool(args.public),
        uris=final_uris,
    )

    # Audit output
    with open(DAILY_AUDIT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "bucket", "artist", "track", "uri"])
        w.writeheader()
        for artist, track, uri in bucket_a_audit:
            w.writerow({"date": args.date, "bucket": "A_top500_random", "artist": artist, "track": track, "uri": uri})
        for artist, track, uri in bucket_b_audit:
            w.writerow({"date": args.date, "bucket": "B_tewnidge_artist_unheard_not_on_tewnidge", "artist": artist, "track": track, "uri": uri})

    print(f"Created/Replaced playlist: {playlist_name}")
    print(f"Playlist ID: {playlist_id}")
    print(f"Tracks added: {len(final_uris)}")
    print(f"Audit CSV: {DAILY_AUDIT_CSV}")
    print(f"URI cache CSV: {URI_CACHE_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
