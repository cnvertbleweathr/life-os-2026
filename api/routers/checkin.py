"""
/api/checkin — daily subjective check-in (energy, mood, focus, sleep,
soreness, stress on a 1–5 scale, plus an optional note).

Writes append to data/checkin/checkin_log.jsonl via api.store. Re-submitting
the same day appends a new row; the latest row for a date wins everywhere
(API reads and pipelines/checkin_pipeline.py).

Readiness is computed here, server-side, so the stored value doesn't depend
on whichever client submitted it. Soreness and stress count inverted.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.store import (
    CHECKIN_LOG,
    date_window,
    timestamp,
    today_local,
    validate_log_date,
)

router = APIRouter()

FIELDS   = ["energy", "mood", "focus", "sleep", "soreness", "stress"]
INVERTED = {"soreness", "stress"}


def readiness(values: dict[str, int]) -> float:
    """0–1 score, same formula as the check-in page."""
    total = sum((6 - values[f]) if f in INVERTED else values[f] for f in FIELDS)
    return round(total / (len(FIELDS) * 5), 3)


def _shape(row: dict) -> dict:
    return {
        "date":      row["date"],
        "logged_at": row.get("logged_at"),
        **{f: row.get(f) for f in FIELDS},
        "readiness": row.get("readiness"),
        "note":      row.get("note") or "",
    }


Scale = Field(ge=1, le=5)


class CheckinIn(BaseModel):
    energy:   int = Scale
    mood:     int = Scale
    focus:    int = Scale
    sleep:    int = Scale
    soreness: int = Scale
    stress:   int = Scale
    note:     str = Field(default="", max_length=2000)
    date:     str | None = Field(default=None, description="YYYY-MM-DD; defaults to today")


@router.post("/log")
async def checkin_log(body: CheckinIn):
    try:
        log_date = validate_log_date(body.date)
    except ValueError as e:
        raise HTTPException(422, str(e))

    values = {f: getattr(body, f) for f in FIELDS}
    row = CHECKIN_LOG.append({
        "date":      log_date,
        "logged_at": timestamp(),
        **values,
        "readiness": readiness(values),
        "note":      body.note.strip(),
    })
    return _shape(row)


@router.get("/today")
async def checkin_today():
    """Today's check-in, or null if there isn't one yet."""
    row = CHECKIN_LOG.latest_by("date").get(today_local().isoformat())
    return _shape(row) if row else None


@router.get("/history")
async def checkin_history(days: int = 30):
    """Check-ins over the last N days, oldest first. Days without one are skipped."""
    days = max(1, min(days, 366))
    latest = CHECKIN_LOG.latest_by("date")
    return [
        _shape(latest[d.isoformat()])
        for d in date_window(days)
        if d.isoformat() in latest
    ]
