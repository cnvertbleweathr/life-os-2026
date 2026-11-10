"""render_mode "youtube": pixelate 5 seconds of a YouTube video the owner picked.

The owner pastes a link and a start time on /film. yt-dlp resolves the link to
a direct stream URL (nothing is downloaded), and film.clip.extract_frames has
ffmpeg read just the seconds it needs from it, exactly like a streamed Plex
clip. The GIFs are a personal-use derivative: gitignored, owner only.

yt-dlp needs a JavaScript runtime to solve YouTube's challenges. It uses node
(found on PATH, in ~/.nvm, or at YTDLP_NODE) or deno if either exists; the
solver scripts come from the yt-dlp-ejs package (the `yt-dlp[default]` extra).

YouTube's media servers usually refuse the first request for a fresh stream
URL (403) and accept the same request a couple of seconds later, so the
frame read is retried (with_retries).
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar
from urllib.parse import parse_qs, urlparse

from film.clip import ClipError

HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "www.youtu.be"}
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
# Small, plain-HTTP formats: ffmpeg can seek straight to the start time with range requests.
FORMAT = "bv*[height<=480][protocol^=http]/b[height<=480][protocol^=http]/bv*[protocol^=http]/b"
RETRY_WAITS = (2.0, 3.0, 5.0)   # seconds between attempts at a 403'd stream

T = TypeVar("T")


def with_retries(read: Callable[[], T], waits: tuple[float, ...] = RETRY_WAITS) -> T:
    """Run `read` (an ffmpeg read of a YouTube stream), retrying while YouTube
    answers 403. Errors never carry the stream URL, which is long and signed."""
    for wait in (*waits, None):
        try:
            return read()
        except ClipError as e:
            refused = "403" in str(e)
            if refused and wait is not None:
                time.sleep(wait)
                continue
            if refused:
                raise ClipError("YouTube kept refusing the stream (403); try again in a few minutes") from e
            raise ClipError(re.sub(r"https?://\S+", "<stream>", str(e))) from e
    raise AssertionError("unreachable")


def parse_time(value: str | float | int | None) -> float | None:
    """Seconds from '83', '83.5', '1:23', '1:02:03', '1m23s', '1h2m3s' or '83s'. None for blank."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value < 0:
            raise ValueError("the start time can't be negative")
        return float(value)
    s = value.strip().lower()
    if not s:
        return None
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s)
    if re.fullmatch(r"\d+(:\d{1,2}){1,2}(\.\d+)?", s):
        parts = s.split(":")
        if any(float(p) >= 60 for p in parts[1:]):
            raise ValueError(f"{value!r} isn't a valid time")
        total = 0.0
        for p in parts:
            total = total * 60 + float(p)
        return total
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?", s)
    if m and any(m.groups()):
        h, mi, se = m.groups()
        return int(h or 0) * 3600 + int(mi or 0) * 60 + float(se or 0)
    raise ValueError(f"{value!r} isn't a time; use 1:23, 1:02:03 or seconds")


def parse_url(url: str) -> tuple[str, float | None]:
    """(canonical watch URL, the link's own start time or None). ValueError if it isn't a YouTube video."""
    u = urlparse((url or "").strip())
    host = (u.hostname or "").lower()
    if u.scheme not in ("http", "https") or host not in HOSTS:
        raise ValueError("that isn't a YouTube link")
    q = parse_qs(u.query)
    if host.endswith("youtu.be"):
        vid = u.path.strip("/").split("/")[0]
    elif u.path == "/watch":
        vid = (q.get("v") or [""])[0]
    else:
        m = re.match(r"^/(?:shorts|embed|live|v)/([^/?#]+)", u.path)
        vid = m.group(1) if m else ""
    if not VIDEO_ID.match(vid):
        raise ValueError("that YouTube link doesn't point at a video")
    t = (q.get("t") or q.get("start") or [None])[0]
    try:
        start = parse_time(t) if t else None
    except ValueError:
        start = None
    return f"https://www.youtube.com/watch?v={vid}", start


def js_runtimes() -> dict:
    """yt-dlp's js_runtimes option: node and/or deno, wherever this machine has them.
    launchd runs with a bare PATH, so look in the usual install places too."""
    found: dict[str, dict] = {}
    node = os.getenv("YTDLP_NODE") or shutil.which("node") or next(iter(sorted(
        glob.glob(str(Path.home() / ".nvm/versions/node/*/bin/node")), reverse=True)), None) or next(
        (p for p in ("/opt/homebrew/bin/node", "/usr/local/bin/node") if Path(p).exists()), None)
    if node:
        found["node"] = {"path": node}
    deno = shutil.which("deno") or next(
        (p for p in (str(Path.home() / ".deno/bin/deno"), "/opt/homebrew/bin/deno") if Path(p).exists()), None)
    if deno:
        found["deno"] = {"path": deno}
    return found


def _friendly(message: str) -> str:
    m = message.lower()
    if "private video" in m:
        return "the video is private"
    if "sign in to confirm your age" in m or "age-restricted" in m:
        return "the video is age-restricted, so it can't be read without signing in"
    if "video unavailable" in m or "video is unavailable" in m or "has been removed" in m or "terminated" in m:
        return "the video is unavailable (removed, or blocked in this country)"
    if "sign in to confirm you" in m and "bot" in m:
        return "YouTube asked this machine to sign in (bot check); try again later"
    if "live event" in m or "premieres in" in m:
        return "the video hasn't started yet"
    return re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*)?", "", message).strip()[:240]


def stream(url: str, start: float | None = None) -> tuple[str, str]:
    """(direct media URL, ffmpeg headers) for a YouTube video. Raises ClipError with a readable reason."""
    try:
        import yt_dlp
    except ImportError as e:   # pragma: no cover - a deploy problem, not a user one
        raise ClipError("yt-dlp isn't installed on this machine (pip install 'yt-dlp[default]')") from e
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "format": FORMAT,
            "js_runtimes": js_runtimes(), "socket_timeout": 30}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        raise ClipError(_friendly(str(e))) from e
    if not info or not info.get("url"):
        raise ClipError("YouTube gave no playable stream for this video")
    duration = info.get("duration")
    if start is not None and duration and start >= duration:
        raise ClipError(f"the start time is past the end of the video ({int(duration) // 60}:{int(duration) % 60:02d} long)")
    headers = "".join(f"{k}: {v}\r\n" for k, v in (info.get("http_headers") or {}).items())
    return info["url"], headers
