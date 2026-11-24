"""
/api/secretary — the Secretary page: heads-ups with done / dismiss, and what's coming.

Privacy: owner-only, reads included (api/main.py mounts it with require_owner).
Birthdays and family names never go out over the public tunnel without the write key.

Reads: secretary.headsups (written by the sync's secretary_headsups step) and dbt's
int_events_tiered, through the API's shared read-only DuckDB connection.

Writes: done / dismiss / reopen append to data/secretary/headsup_actions.jsonl
(secretary/headsups.py record_action); the next sync applies them to
secretary.headsups. Until then the reads overlay the queued action, so a click
shows at once and survives a reload.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from api.deps import get_db
from api.store import today_local
from secretary import config as SC
from secretary import headsups as H

router = APIRouter()

UPCOMING_DAYS = 30
CLOSED_KEEP_DAYS = 14          # done / dismissed stay listed (with Undo) this long after the click


def _iso(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return v


def _rows(db, sql: str, params: list) -> list[dict]:
    try:
        cur = db.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception:                     # table not built yet (first day) → nothing to show
        return []


def calendar_status(today: date) -> dict:
    scripts = str(Path(__file__).resolve().parents[2] / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    try:
        from calendar_export import read_status
        s = read_status(today)
        return {"ok": bool(s.get("ok")), "message": s.get("message"), "last_ok_at": s.get("last_ok_at")}
    except Exception as e:                # never break the page over the status file
        return {"ok": False, "message": f"calendar status unreadable: {e}", "last_ok_at": None}


def headsups(db, today: date) -> list[dict]:
    since = today - timedelta(days=CLOSED_KEEP_DAYS)
    rows: list[dict] = []
    # last_action_at arrived after the first release; until the next sync adds it, read NULL instead
    for action_col in ("last_action_at", "CAST(NULL AS VARCHAR) AS last_action_at"):
        rows = _rows(db, f"""
            SELECT {', '.join(H.COLUMNS)}, {action_col}
            FROM secretary.headsups
            WHERE due_date <= ? AND event_date >= ?
              AND (status = 'open' OR (status IN ('done', 'dismissed') AND closed_at >= ?))""",
            [today, since, since])
        if rows:
            break
    # an open heads-up whose event is past only lingers until the next sync expires it
    rows = [r for r in rows if r["status"] != "open" or r["event_date"] >= today]
    pending = H.pending_actions()
    out = []
    for r in rows:
        status, queued = r["status"], False
        a = pending.get(r["headsup_id"])
        # A click the sync hasn't seen yet (its `at` isn't the row's last_action_at) shows at once.
        if a and a.get("at") != r["last_action_at"] and a.get("status") in ("open", *H.CLOSED_BY_YOU) \
                and r["status"] in ("open", *H.CLOSED_BY_YOU) and a["status"] != status:
            status, queued = a["status"], True
        out.append({
            **{k: _iso(r[k]) for k in H.COLUMNS},
            "status": status,
            "queued": queued,
            "shown_today": r["last_shown_on"] == today,
            "days_to_go": (r["event_date"] - today).days,
        })
    return sorted(out, key=lambda h: (H.TIER_RANK.get(h["tier"], 9), h["event_date"], h["title"]))


def upcoming(db, today: date) -> list[dict]:
    rows = _rows(db, """
        SELECT event_key, display_title AS title, tier, event_date, start_at, all_day, is_birthday
        FROM main_intermediate.int_events_tiered
        WHERE event_date BETWEEN ? AND ? AND tier <> 'trivia'
        ORDER BY event_date, start_at NULLS FIRST, title""", [today, today + timedelta(days=UPCOMING_DAYS)])
    for r in rows:
        r["days_to_go"] = (r["event_date"] - today).days
        r["time"] = (r["start_at"].astimezone(SC.TZ).strftime("%-I:%M%p").lower().replace(":00", "")
                     if r["start_at"] is not None and not r["all_day"] else None)
        for k in ("event_date", "start_at"):
            r[k] = _iso(r[k])
    return rows


def projects(db, today: date) -> list[dict]:
    """Active life projects with overdue / due (7 days) / done this week / next: the packet's summary."""
    from secretary.sheet import projects_summary
    return projects_summary(db, today)["projects"]


def sheet_proposals() -> dict[str, list[str]]:
    from secretary.sheet import proposals
    return proposals()


@router.get("/overview")
async def overview(request: Request):
    db = get_db(request)
    today = today_local()
    cfg = SC.load()
    return {
        "today": today.isoformat(),
        "nag_limit": cfg.settings["nag_limit"],
        "critical_daily_days": cfg.settings.get("critical_daily_days", 3),
        "configured": cfg.settings_path is not None,
        "placeholders": cfg.placeholders,
        "proposals": sheet_proposals(),
        "problems": cfg.problems,
        "calendar": calendar_status(today),
        "headsups": headsups(db, today),
        "upcoming": upcoming(db, today),
        "projects": projects(db, today),
    }


class ActionIn(BaseModel):
    headsup_id: str = Field(min_length=3, max_length=600)
    action: Literal["done", "dismiss", "reopen"]


@router.post("/headsups/action")
async def act(body: ActionIn, request: Request):
    db = get_db(request)
    if not _rows(db, "SELECT 1 FROM secretary.headsups WHERE headsup_id = ?", [body.headsup_id]):
        raise HTTPException(404, "No such heads-up (it may have been replaced by a newer one; reload).")
    row = H.record_action(body.headsup_id, body.action, by="website")
    return {"headsup_id": body.headsup_id, "status": row["status"], "queued": True, "at": row["at"]}
