"""The shared Spotify sign-in must be requested with one scope everywhere.

spotipy writes the *requested* scope into the token cache on every refresh, so a
script asking for a narrower scope would shrink the cached scope. Daily 10 (which
needs playlist-modify + ugc-image-upload) would then reject the cache and try a
browser sign-in during the unattended 4:00 sync. This happened once on 2026-11-27.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import spotify_auth  # noqa: E402

SHARED_USERS = [
    "sync_playlist_artists.py",
    "spotify_daily10_playlist.py",
    "spotify_check.py",
]


def _spotify_oauth_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)
            if name == "SpotifyOAuth":
                yield node


def test_shared_scope_covers_what_daily10_needs():
    scopes = set(spotify_auth.SCOPE.split())
    assert {"playlist-modify-private", "playlist-modify-public", "ugc-image-upload",
            "playlist-read-private", "playlist-read-collaborative"} <= scopes


def test_every_shared_cache_user_requests_the_shared_scope():
    for fname in SHARED_USERS:
        tree = ast.parse((SCRIPTS / fname).read_text())
        calls = list(_spotify_oauth_calls(tree))
        assert calls, f"{fname}: no SpotifyOAuth call found"
        for call in calls:
            kw = {k.arg: k.value for k in call.keywords}
            assert isinstance(kw.get("scope"), ast.Name) and kw["scope"].id == "SCOPE", (
                f"{fname}:{call.lineno} must pass scope=SCOPE from spotify_auth")
            assert "TOKEN_CACHE" in ast.unparse(kw.get("cache_path", ast.Constant(None))), (
                f"{fname}:{call.lineno} must pass cache_path=str(TOKEN_CACHE)")


def test_shared_cache_path_is_defined_only_in_spotify_auth():
    offenders = [p.name for p in SCRIPTS.glob("*.py")
                 if p.name != "spotify_auth.py" and "spotify_token_cache.json" in p.read_text()]
    assert not offenders, f"hard-coded shared cache path in: {offenders}"
