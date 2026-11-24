"""
/api/checkin — daily subjective check-in (energy, mood, focus, sleep,
soreness, stress on a 1–5 scale, plus an optional note).

Writes append to data/checkin/checkin_log.jsonl via api.store. Re-submitting
the same day appends a new row; the latest row for a date wins everywhere
(API reads and pipelines/checkin_pipeline.py).

Readiness is computed here, server-side, so the stored value doesn't depend
on whichever client submitted it. Soreness and stress count inverted.

/recap and /recaps: the check-in RECAP from the voice chat, pasted on the
Check-in page. Appended to data/checkin/recaps.jsonl; the sync's ingest_recap
step (checkin/ingest_recap.py) applies it.
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


class RecapIn(BaseModel):
    text: str = Field(min_length=6, max_length=20000)


@router.post("/recap")
async def recap_submit(body: RecapIn):
    """Queue a pasted RECAP (docs/context/checkin-protocol.md) for the 4am sync's ingest_recap step,
    and preview what it will do. A paste that isn't a RECAP is refused."""
    from checkin import ingest_recap
    try:
        row = ingest_recap.submit(body.text, source="web")
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {k: row[k] for k in ("recap_id", "recap_date", "submitted_at", "preview")}


@router.get("/recaps")
async def recap_list(limit: int = 5):
    """Recent pasted RECAPs, newest first, with what the sync did (or "waiting for the 4am sync")."""
    from checkin import ingest_recap
    limit = max(1, min(limit, 50))
    results = ingest_recap.results_log().latest_by("recap_id")
    rows = sorted(ingest_recap.recaps_log().rows(), key=lambda r: r.get("submitted_at", ""), reverse=True)[:limit]
    return [{"recap_id": r["recap_id"], "recap_date": r.get("recap_date"), "submitted_at": r.get("submitted_at"),
             "result": {k: v for k, v in results[r["recap_id"]].items() if k != "sections"}
             if r["recap_id"] in results else None}
            for r in rows if r.get("recap_id")]


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
