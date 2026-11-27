"""
spotify_auth.py — the one Spotify sign-in ONS keeps alive.

Every script that talks to Spotify as the user (Daily 10, sync_playlist_artists,
spotify_check) shares one token cache and must request exactly this SCOPE.

Why exactly: spotipy writes the *requested* scope into the cache file every time
it refreshes the token (spotipy.oauth2.SpotifyOAuth._add_custom_values_to_token_info).
If one script asked for less, its refresh would shrink the cached scope. The next
script asking for more would then reject the cached token and try to open a browser
sign-in in the middle of the unattended 4:00 sync.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TOKEN_CACHE = ROOT / "secrets" / "spotify_token_cache.json"

SCOPE = (
    "playlist-modify-private "
    "playlist-modify-public "
    "playlist-read-private "
    "playlist-read-collaborative "
    "ugc-image-upload"
)
