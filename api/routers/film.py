"""
/api/film — watches, the GIF library, and the scene catalog's review queue.

Public (`public` router; narcisystem.com is public, see api/auth.py):
  GET   /api/film/watches                 every watch from mart_film_watches, newest first
  GET   /api/film/library                 rendered films this requester may see, plus queue counts
  GET   /api/film/scene                   the film for the page's title scene (the latest watch)
  GET   /api/film/strip/{film_key}?theme=light|dark[&fallback=motif]
                                          the film's 40 frames as one 2560×32 PNG strip

plex_clip and youtube GIFs are a personal-use derivative of copyrighted films:
only the owner (a local request, or one with the write key) can list or fetch them.
Sprite (public-domain) and motif (original) GIFs are public.

Owner only (`router`, mounted with require_owner):
  GET   /api/film/queue                   suggested rows, newest first
  GET   /api/film/queue?status=all        every row (or approved / rejected / rendered)
  PATCH /api/film/queue/{film_key}        edit label, note, render mode, clip window
  POST  /api/film/queue/{film_key}/approve   approve, optionally with the same edits
  POST  /api/film/queue/{film_key}/reject
  PUT   /api/film/clip/{film_key}         {youtube_url, start}: point the film's GIF at
                                          5 s of a YouTube video, approve it, and render
                                          it now in the background (any watched film)
  GET   /api/film/clip/{film_key}         that render's progress, for the page to poll

film_key is 'tmdb:<id>' or 'title:<title>:<year>' (from mart_film_watches);
URL-encode it. Writes go to data/film/scene_catalog.jsonl via api.film_catalog;
the approval UI is on the /film page.
"""

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from api import film_catalog as fc
from api import film_render_jobs as jobs
from api.auth import require_owner
from api.deps import get_db, query
from api.store import data_dir

router = APIRouter()   # owner only (see api/main.py)
public = APIRouter()

Theme = Literal["light", "dark"]
STRIP_FRAMES, FRAME_W, FRAME_H, FRAME_MS = 40, 64, 32, 125


def is_owner(request: Request) -> bool:
    try:
        require_owner(request)
        return True
    except HTTPException:
        return False


visible = fc.is_visible   # a GIF this requester may see


# ── public ───────────────────────────────────────────────────────────────────

@public.get("/watches")
async def watches(request: Request, limit: int = 2000):
    limit = max(1, min(limit, 5000))
    rows = query(get_db(request), """
        select watch_id, film_key, tmdb_id, title, film_year, cast(watch_date as varchar) as watch_date,
               watch_year, source, rating, liked, has_review, is_rewatch, watch_number,
               letterboxd_url, plex_plays
        from main_marts.mart_film_watches
        order by watch_date desc, title
        limit ?
    """, [limit])
    owner, cat = is_owner(request), fc.catalog()
    for r in rows:
        c = cat.get(r["film_key"])
        r["gif"] = bool(c and visible(c, owner))
        r["gif_mode"] = c.get("render_mode") if r["gif"] else None
        r["gif_version"] = c.get("rendered_at") if r["gif"] else None
        if owner:   # what the clip editor on /film needs
            r["clip"] = _clip_status(r["film_key"], c)
    return rows


@public.get("/library")
async def library(request: Request):
    owner, cat = is_owner(request), fc.catalog().values()
    films = [
        {k: r.get(k) for k in ("film_key", "tmdb_id", "title", "year", "scene_label", "scene_note",
                               "render_mode", "rendered_at")}
        for r in cat if visible(r, owner)
    ]
    films.sort(key=lambda r: r.get("rendered_at") or "", reverse=True)
    counts = {s: sum(1 for r in cat if r.get("status") == s) for s in fc.STATUSES}
    return {"films": films, "counts": counts}


@public.get("/scene")
async def scene(request: Request):
    """The latest watch, and whether its strip is its GIF or a motif stand-in."""
    latest = query(get_db(request), """
        select film_key, title, film_year from main_marts.mart_film_watches
        order by watch_date desc, plex_last_viewed_at_utc desc nulls last limit 1
    """)
    if not latest:
        return None
    film = latest[0]
    row = fc.catalog().get(film["film_key"])
    gif = bool(row and visible(row, is_owner(request)))
    return {
        "film_key": film["film_key"], "title": film["title"], "year": film["film_year"],
        "scene_label": row.get("scene_label") if gif else None,
        "strip": "gif" if gif else "motif",
        "version": row.get("rendered_at") if gif else None,
    }


def _clip_status(film_key: str, row: dict | None) -> dict:
    """Where a film's clip stands, for the owner's editor:
    rendering / queued (this process is on it), failed (render_error), waiting
    (approved, for the 9:00 sync), done (rendered), or none (no catalog row)."""
    row = row or {}
    job = jobs.state(film_key)
    status = row.get("status")
    if job:
        state = job
    elif status == "approved" and row.get("render_error"):
        state = "failed"
    elif status == "approved":
        state = "waiting"
    elif status == "rendered":
        state = "done"
    else:
        state = "none"
    return {
        "state": state, "error": row.get("render_error") if state == "failed" else None,
        "render_mode": row.get("render_mode"), "youtube_url": row.get("youtube_url"),
        "clip_start": row.get("clip_start") if row.get("render_mode") == "youtube" else None,
        "rendered_at": row.get("rendered_at"),
    }


def _expand(path: Path) -> list:
    """The GIF's 40 frames at 125 ms, re-expanding frames Pillow merged when saving."""
    from PIL import Image, ImageSequence
    frames = []
    with Image.open(path) as im:
        for f in ImageSequence.Iterator(im):
            frames += [f.convert("RGB")] * max(1, round(f.info.get("duration", FRAME_MS) / FRAME_MS))
    return (frames + frames[-1:] * STRIP_FRAMES)[:STRIP_FRAMES]


def _strip_png(frames: list) -> bytes:
    from PIL import Image
    strip = Image.new("RGB", (FRAME_W * STRIP_FRAMES, FRAME_H))
    for i, f in enumerate(frames):
        strip.paste(f, (i * FRAME_W, 0))
    buf = io.BytesIO()
    strip.save(buf, "PNG", optimize=True)
    return buf.getvalue()


@lru_cache(maxsize=128)
def _gif_strip(path: str, mtime: float) -> bytes:
    return _strip_png(_expand(Path(path)))


@lru_cache(maxsize=64)
def _motif_strip(film_key: str, title: str, theme: str) -> bytes:
    from film import canvas, motifs
    return _strip_png(canvas.render_frames(motifs.render(title, film_key), theme))


@public.get("/strip/{film_key:path}")
async def strip(film_key: str, request: Request, theme: Theme = "light", fallback: Literal["motif"] | None = None):
    owner = is_owner(request)
    row = fc.catalog().get(film_key)
    if row and visible(row, owner):
        path = data_dir() / row["gif_web" if theme == "light" else "gif_matrix"]
        if path.exists():
            private = row.get("render_mode") in fc.PRIVATE_MODES
            return Response(_gif_strip(str(path), path.stat().st_mtime), media_type="image/png",
                            headers={"Cache-Control": f"{'private' if private else 'public'}, max-age=3600"})
    if fallback == "motif":
        title = (row or {}).get("title") or next(iter(query(get_db(request), """
            select title from main_marts.mart_film_watches where film_key = ? limit 1""", [film_key])), {}).get("title")
        if not title:
            raise HTTPException(404, "unknown film")
        return Response(_motif_strip(film_key, title, theme), media_type="image/png",
                        headers={"Cache-Control": "public, max-age=3600"})
    if row and row.get("status") == "rendered" and not owner:
        raise HTTPException(403, "this film's GIF is private")
    raise HTTPException(404, "no rendered GIF for this film")


class CatalogEdit(BaseModel):
    scene_label: str | None = Field(default=None, max_length=120)
    scene_note:  str | None = Field(default=None, max_length=500)
    render_mode: Literal["sprite", "plex_clip", "motif", "youtube"] | None = None
    clip_start:  float | None = Field(default=None, ge=0)
    clip_end:    float | None = Field(default=None, ge=0)
    youtube_url: str | None = Field(default=None, max_length=500)


class ClipPick(BaseModel):
    youtube_url: str = Field(max_length=500)
    start: float = Field(ge=0, le=24 * 3600)


def _edits(body: CatalogEdit | None) -> dict:
    return body.model_dump(exclude_unset=True) if body else {}


def _call(fn, *args):
    try:
        return fn(*args)
    except fc.CatalogError as e:
        raise HTTPException(e.status, str(e)) from e


@router.get("/queue")
async def queue(status: Literal["suggested", "approved", "rejected", "rendered", "all"] = "suggested"):
    rows = fc.catalog().values()
    if status != "all":
        rows = [r for r in rows if r.get("status") == status]
    return sorted(rows, key=lambda r: r.get("suggested_at") or "", reverse=True)


@router.patch("/queue/{film_key:path}")
async def edit(film_key: str, body: CatalogEdit):
    return _call(fc.edit, film_key, _edits(body))


@router.post("/queue/{film_key:path}/approve")
async def approve(film_key: str, body: CatalogEdit | None = None):
    return _call(fc.approve, film_key, _edits(body))


@router.post("/queue/{film_key:path}/reject")
async def reject(film_key: str):
    return _call(fc.reject, film_key)


@router.put("/clip/{film_key:path}")
async def set_clip(film_key: str, body: ClipPick, request: Request):
    film = fc.catalog().get(film_key) or next(iter(query(get_db(request), """
        select film_key, tmdb_id, title, film_year as year from main_marts.mart_film_watches
        where film_key = ? limit 1""", [film_key])), None)
    if not film:
        raise HTTPException(404, "no watch for this film")
    row = _call(fc.set_youtube_clip, film, body.youtube_url, body.start)
    jobs.submit(film_key)
    return _clip_status(film_key, row)


@router.get("/clip/{film_key:path}")
async def clip_status(film_key: str):
    return _clip_status(film_key, fc.catalog().get(film_key))
