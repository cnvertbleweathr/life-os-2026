"""
/api/progeny — the kids' development: countdowns, weekly focus, timeline,
learning paths, CDC milestones, read-alouds, baby prep.

Privacy: every endpoint here is owner-only (api/main.py mounts the router with
require_owner), reads included. Kids' names, quotes and milestones never go out
over the public tunnel without the write key.

Reads come from the dbt marts (main_marts.mart_progeny_*), which are views, so
ages are computed from the birthdate at read time. Writes append to
data/progeny/*.jsonl through progeny/store.py and never touch DuckDB; the daily
sync loads them, so a new entry appears in the reads after the next sync.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from api.deps import get_db, query
from api.store import today_local
from progeny import store

router = APIRouter()

PREP_CATEGORIES = ["Gear", "Nursery", "Hospital", "Feeding", "Health", "Admin", "Family", "Other"]
Kind = Literal["quotes", "firsts", "books", "milestones", "path_evidence", "prep_tasks"]


def _plain(value: Any) -> Any:
    """Dates as YYYY-MM-DD; pandas hands DATE columns back as Timestamps."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def mart(request: Request, name: str, order_by: str | None = None) -> list[dict[str, Any]]:
    """All rows of a progeny mart, or [] before the first sync has built it."""
    sql = f"SELECT * FROM main_marts.mart_progeny_{name}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    return [{k: _plain(v) for k, v in row.items()} for row in query(get_db(request), sql)]


def _kids_config() -> tuple[list[dict[str, Any]], str | None]:
    try:
        return store.load_kids(), None
    except Exception as e:  # malformed kids.yaml
        return [], str(e)


def weekly_focus(paths: list[dict[str, Any]], week: int) -> list[dict[str, Any]]:
    """One learning path per kid, the same all week, cycling through every path in turn."""
    by_kid: dict[str, list[dict[str, Any]]] = {}
    for p in paths:
        by_kid.setdefault(p["kid_id"], []).append(p)
    out = []
    for kid_paths in by_kid.values():
        kid_paths.sort(key=lambda p: p["path_order"])
        p = kid_paths[week % len(kid_paths)]
        out.append({**p, "activities": [a for a in (p.get("focus_activities") or "").split("\n") if a.strip()]})
    return out


# ── reads ─────────────────────────────────────────────────────────────────────

@router.get("/overview")
async def overview(request: Request):
    """Kids with live ages and countdowns, plus this week's learning focus."""
    kids_cfg, error = _kids_config()
    return {
        "configured": bool(kids_cfg),
        "config_error": error,
        "config_kids": kids_cfg,
        "kids": mart(request, "kids", "coalesce(birthdate, due_date)"),
        "focus": weekly_focus(mart(request, "paths"), today_local().isocalendar().week),
        "today": today_local().isoformat(),
    }


@router.get("/timeline")
async def timeline(request: Request, limit: int = 300):
    limit = max(1, min(limit, 2000))
    return mart(request, "timeline", f"event_date DESC, logged_at DESC LIMIT {limit}")


@router.get("/paths")
async def paths(request: Request):
    rows = mart(request, "paths", "kid_id, path_order")
    for r in rows:
        r["activities"] = [a for a in (r.pop("focus_activities", None) or "").split("\n") if a.strip()]
    return rows


@router.get("/milestones")
async def milestones(request: Request):
    return mart(request, "milestones", "kid_id, band_role, domain, sort_order")


@router.get("/reading")
async def reading(request: Request):
    return {
        "kids": mart(request, "reading", "kid_id"),
        "titles": mart(request, "reading_titles", "kid_id, rank_by_reads"),
    }


@router.get("/prep")
async def prep(request: Request):
    return {
        "tasks": mart(request, "prep_tasks", "status = 'done', due_date NULLS LAST, task"),
        "burndown": mart(request, "prep", "day"),
    }


@router.get("/options")
async def options(request: Request):
    """Everything the log forms need: kids, the CDC checklist, path levels, categories, known titles."""
    kids_cfg, error = _kids_config()
    titles = mart(request, "reading_titles", "times_read DESC")
    return {
        "kids": kids_cfg,
        "config_error": error,
        "milestones": store.milestone_rows(),
        "levels": store.path_level_rows(),
        "prep_categories": PREP_CATEGORIES,
        "known_titles": list(dict.fromkeys(t["title"] for t in titles if t.get("title"))),
    }


# ── writes ────────────────────────────────────────────────────────────────────

class EntryIn(BaseModel):
    fields: dict[str, Any]
    entry_id: str | None = Field(default=None, description="Pass an existing id to edit that entry")


def _title_key(title: Any) -> str:
    return " ".join(str(title or "").lower().split())


def _read_before(request: Request, kid: str, title: Any) -> bool:
    """Has this kid had this book read before? Checks the warehouse and the not-yet-synced log."""
    key = _title_key(title)
    if any(t["kid_id"] == kid and t["title_key"] == key for t in mart(request, "reading_titles")):
        return True
    return any(
        e.get("kid") == kid and not e.get("deleted") and _title_key(e.get("title")) == key
        for e in store.latest_entries("books")
    )


@router.post("/{kind}")
async def log_entry(kind: Kind, body: EntryIn, request: Request):
    """Append one entry to data/progeny/<kind>.jsonl. Re-reads of a book are flagged automatically."""
    fields = dict(body.fields)
    if kind == "books" and "repeat" not in fields:
        fields["repeat"] = _read_before(request, fields.get("kid"), fields.get("title"))
    try:
        return store.append_entry(kind, fields, entry_id=body.entry_id, source="web")
    except ValueError as e:
        raise HTTPException(422, str(e))
