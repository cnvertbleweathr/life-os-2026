"""
/api/display — what the LED panel shows (owner only: the playlist includes
plex_clip GIFs; the Pi reaches the API over Tailscale, which counts as local).

  GET /api/display/playlist             the ordered items, decided here; the Pi just plays them
  GET /api/display/gif/{film_key}       a film's gif_matrix (dark-palette) GIF
  GET /api/display/frame/{token}.png    a score or idle frame from the latest playlist

Curation:
  - A live game for one of my teams pre-empts everything: the playlist is
    just the live score frames, and the Pi refetches every 30 s.
  - Otherwise film loops (15 s each, three plays) rotate, with one score card
    (later today, recent finals, next games) after every two films. The film
    order shifts daily so the same few don't always lead.
  - Nothing to show: a date-and-time frame.
  - DISPLAY_QUIET_HOURS="23-7" (local hours, optional) blanks the panel overnight.
"""

from __future__ import annotations

import hashlib
import os
from collections import OrderedDict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse

from api import display, espn
from api import film_catalog as fc
from api.store import data_dir, today_local

router = APIRouter()

TZ = ZoneInfo("America/Denver")
FILM_SECONDS, SCORE_SECONDS, LIVE_SECONDS, IDLE_SECONDS = 15, 8, 10, 30
MAX_FILMS, MAX_SCORES = 12, 6
_frames: "OrderedDict[str, bytes]" = OrderedDict()


def _keep(png: bytes) -> str:
    token = hashlib.sha1(png).hexdigest()[:16]
    _frames[token] = png
    _frames.move_to_end(token)
    while len(_frames) > 256:
        _frames.popitem(last=False)
    return token


def quiet(now: datetime, spec: str | None = None) -> bool:
    """True inside DISPLAY_QUIET_HOURS ("23-7" wraps past midnight; "" or unset = never)."""
    spec = (spec if spec is not None else os.getenv("DISPLAY_QUIET_HOURS", "")).strip()
    if "-" not in spec:
        return False
    try:
        start, end = (int(x) % 24 for x in spec.split("-", 1))
    except ValueError:
        return False
    h = now.astimezone(TZ).hour
    return start <= h < end if start < end else (h >= start or h < end)


def films_for(day_ordinal: int) -> list[dict]:
    """Rendered films with a matrix GIF on disk, newest render first, rotated by the day."""
    rows = [r for r in fc.catalog().values()
            if r.get("status") == "rendered" and r.get("gif_matrix") and (data_dir() / r["gif_matrix"]).exists()]
    rows.sort(key=lambda r: r.get("rendered_at") or "", reverse=True)
    if len(rows) > 1:
        k = day_ordinal % len(rows)
        rows = rows[k:] + rows[:k]
    return rows[:MAX_FILMS]


def build(now: datetime, games: dict, films: list[dict]) -> dict:
    """The playlist from already-fetched games and films. Pure apart from the frame cache."""
    if quiet(now):
        return {"mode": "off", "refresh_s": 300, "items": []}

    def score_item(g: dict, seconds: int) -> dict:
        token = _keep(display.png(display.score_frame(g, now)))
        return {"type": "png", "url": f"/api/display/frame/{token}.png", "seconds": seconds,
                "label": f"{g['league_label']} {g['short_name']} · {g['state']}"}

    if games.get("live"):
        return {"mode": "live", "refresh_s": 30, "items": [score_item(g, LIVE_SECONDS) for g in games["live"]]}

    cards = [score_item(g, SCORE_SECONDS) for g in
             (games.get("today", []) + games.get("final", []) + games.get("next", []))[:MAX_SCORES]]
    reels = [{"type": "gif", "url": f"/api/display/gif/{r['film_key']}", "seconds": FILM_SECONDS,
              "label": f"{r.get('title')} ({r.get('year')})"} for r in films]
    if not cards and not reels:
        token = _keep(display.png(display.idle_frame(now)))
        return {"mode": "idle", "refresh_s": 60,
                "items": [{"type": "png", "url": f"/api/display/frame/{token}.png", "seconds": IDLE_SECONDS, "label": "clock"}]}

    items: list[dict] = []
    if not reels:
        items = cards
    else:
        ci = 0
        for i, reel in enumerate(reels):
            items.append(reel)
            if cards and i % 2 == 1:
                items.append(cards[ci % len(cards)]); ci += 1
        items += cards[ci:]                                     # any cards the films didn't reach
    return {"mode": "rotation", "refresh_s": 60, "items": items}


@router.get("/playlist")
async def playlist():
    now = datetime.now(timezone.utc)
    errors: list[str] = []
    games: dict = {}
    if not quiet(now):
        try:
            async with httpx.AsyncClient() as client:
                games = await espn.my_games(client, now, today_local())
                await display.ensure_logos(client, games["live"] + games["today"] + games["final"] + games["next"])
            errors = games.get("errors", [])
        except Exception as e:                                  # ESPN down: films still play
            errors = [f"espn: {e}"]
            games = {}
    out = build(now, games, films_for(now.astimezone(TZ).toordinal()))
    return {"generated_at": now.isoformat(), "panel": {"w": display.W, "h": display.H}, **out, "errors": errors}


@router.get("/gif/{film_key:path}")
async def gif(film_key: str):
    row = fc.catalog().get(film_key)
    if not row or row.get("status") != "rendered" or not row.get("gif_matrix"):
        raise HTTPException(404, "no rendered GIF for this film")
    path = data_dir() / row["gif_matrix"]
    if not path.exists():
        raise HTTPException(404, "GIF file missing; it re-renders when the row is edited")
    return FileResponse(path, media_type="image/gif", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/frame/{token}.png")
async def frame(token: str):
    png = _frames.get(token)
    if png is None:
        raise HTTPException(404, "frame expired; fetch the playlist again")
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=600"})
