"""
spotify_compat.py — playlist reading that survives Spotify's Feb 2026 API changes.

Spotify's Development Mode migration (existing apps moved 2026-03-09):
  - GET /playlists/{id}/tracks became /playlists/{id}/items
  - each playlist entry's `track` object was renamed to `item`
  - items are only returned for playlists you own or collaborate on

Code that asked for fields="items(track(...))" and read entry["track"] now
gets nothing back, silently: Daily 10 Bucket B and the Tewnidge/Deeds
show matching both depended on it. This module reads either shape and
raises a clear error when a playlist's items aren't readable at all.

Reference:
https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide
"""

from __future__ import annotations

from typing import Iterator

import spotipy


class PlaylistNotReadable(RuntimeError):
    """The playlist's items can't be read with this account (not owned/collaborative)."""


def entry_track(entry: dict) -> dict:
    """The track object from a playlist entry, old (`track`) or new (`item`) shape."""
    return (entry.get("item") or entry.get("track") or {}) if isinstance(entry, dict) else {}


def iter_playlist_tracks(sp: spotipy.Spotify, playlist_id: str, page_size: int = 100) -> Iterator[dict]:
    """
    Yield the track object for every entry in a playlist.

    No `fields` filter: filters written for the old field names return empty
    entries, and the payload saving isn't worth that risk.
    """
    offset = 0
    while True:
        try:
            page = sp.playlist_items(playlist_id, offset=offset, limit=page_size)
        except spotipy.SpotifyException as e:
            if e.http_status in (401, 403, 404):
                raise PlaylistNotReadable(
                    f"playlist {playlist_id}: HTTP {e.http_status}. Since March 2026 Spotify only "
                    "returns items for playlists you own or collaborate on. Copy it into a "
                    "playlist you own and use that ID instead."
                ) from e
            raise
        entries = page.get("items") or []
        for entry in entries:
            track = entry_track(entry)
            if track:
                yield track
        if not page.get("next") or not entries:
            break
        offset += page_size


def first_artist_names(tracks) -> list[str]:
    """Unique first-artist names in order of appearance (case-insensitive)."""
    seen, out = set(), []
    for t in tracks:
        artists = t.get("artists") or []
        if artists and artists[0].get("name"):
            name = artists[0]["name"].strip()
            if name.lower() not in seen:
                seen.add(name.lower())
                out.append(name)
    return out
