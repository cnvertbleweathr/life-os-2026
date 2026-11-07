"""
/api/film — the film scene catalog's review queue (owner only).

  GET   /api/film/queue                   suggested rows, newest first
  GET   /api/film/queue?status=all        every row (or approved / rejected / rendered)
  PATCH /api/film/queue/{film_key}        edit label, note, render mode, clip window
  POST  /api/film/queue/{film_key}/approve   approve, optionally with the same edits
  POST  /api/film/queue/{film_key}/reject

film_key is 'tmdb:<id>' or 'title:<title>:<year>' (from mart_film_watches);
URL-encode it. Writes go to data/film/scene_catalog.jsonl via api.film_catalog;
the approval UI arrives with the /film page (Phase 4). Watches, the GIF library
and static GIF serving come with later phases.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api import film_catalog as fc

router = APIRouter()


class CatalogEdit(BaseModel):
    scene_label: str | None = Field(default=None, max_length=120)
    scene_note:  str | None = Field(default=None, max_length=500)
    render_mode: Literal["sprite", "plex_clip", "motif"] | None = None
    clip_start:  float | None = Field(default=None, ge=0)
    clip_end:    float | None = Field(default=None, ge=0)


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
