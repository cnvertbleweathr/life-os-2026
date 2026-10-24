"""spotify_compat reads playlists in both the pre- and post-Feb-2026 shapes."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import spotipy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from spotify_compat import (  # noqa: E402
    PlaylistNotReadable,
    first_artist_names,
    iter_playlist_tracks,
)


def track(uri, artist):
    return {"uri": uri, "artists": [{"name": artist}]}


class FakeSpotify:
    """Pages of playlist entries; key is 'track' (old API) or 'item' (new)."""

    def __init__(self, entries, key="item", page=2, status=None):
        self.entries = [{key: t} for t in entries]
        self.page, self.status, self.calls = page, status, []

    def playlist_items(self, playlist_id, offset=0, limit=100, **kw):
        assert "fields" not in kw            # old-name filters return empty entries
        self.calls.append(offset)
        if self.status:
            raise spotipy.SpotifyException(self.status, -1, "Forbidden")
        chunk = self.entries[offset:offset + self.page]
        more = offset + self.page < len(self.entries)
        return {"items": chunk, "next": "x" if more else None}


TRACKS = [track("a", "Tame Impala"), track("b", "tame impala"), None, track("c", "Khruangbin")]


@pytest.mark.parametrize("key", ["item", "track"])
def test_reads_both_shapes_across_pages(key):
    sp = FakeSpotify(TRACKS, key=key, page=2)
    tracks = list(iter_playlist_tracks(sp, "pl", page_size=2))
    assert [t["uri"] for t in tracks] == ["a", "b", "c"]          # null entry skipped
    assert sp.calls == [0, 2]
    assert first_artist_names(tracks) == ["Tame Impala", "Khruangbin"]


def test_followed_playlist_raises_clear_error():
    with pytest.raises(PlaylistNotReadable, match="own or collaborate"):
        list(iter_playlist_tracks(FakeSpotify(TRACKS, status=403), "pl"))
