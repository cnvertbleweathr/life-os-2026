"""
/api/habits — today's checklist, streaks, YTD completion, history.

Writes (POST /log) append a full-day snapshot to data/habits/habits_log.jsonl
via api.store; the habits pipeline loads that file into DuckDB on the next sync.
Reads of today and the recent strip come straight from the log, so a toggle
shows up immediately without waiting for the sync.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.auth import require_owner
from api.deps import get_db, query, query_one
from api.store import (
    HABITS_LOG,
    date_window,
    timestamp,
    today_local,
    validate_log_date,
)

router = APIRouter()

HABITS = {
    "meditation":          "Meditation",
    "pushups_100":         "100 Pushups",
    "nonfiction_pages_10": "10 Nonfiction Pages",
    "fiction_pages_10":    "10 Fiction Pages",
}

FALLBACK_QUOTES = [
    ("The secret of getting ahead is getting started.", "Mark Twain"),
    ("We are what we repeatedly do. Excellence, then, is not an act, but a habit.", "Aristotle"),
    ("Motivation is what gets you started. Habit is what keeps you going.", "Jim Ryun"),
    ("Discipline is the bridge between goals and accomplishment.", "Jim Rohn"),
    ("Small daily improvements are the key to staggering long-term results.", "Robin Sharma"),
]


def _day_state(log_date: str, latest: dict | None = None) -> dict:
    """Habit state for one date: the last snapshot written for it, or all false."""
    latest = HABITS_LOG.latest_by("date") if latest is None else latest
    row = latest.get(log_date, {})
    return {
        "date": log_date,
        "habits": [
            {"key": k, "label": label, "done": bool(row.get(k, False))}
            for k, label in HABITS.items()
        ],
        "done_count":  sum(1 for k in HABITS if row.get(k, False)),
        "total_count": len(HABITS),
        "logged_at":   row.get("logged_at"),
    }


@router.get("/today")
async def habits_today():
    """Today's habit state (user's local date) from the JSONL log."""
    return _day_state(today_local().isoformat())


class HabitLogIn(BaseModel):
    habit: str
    done: bool
    date: str | None = Field(
        default=None,
        description="YYYY-MM-DD; defaults to today. Up to 7 days back for backfill.",
    )


@router.post("/log", dependencies=[Depends(require_owner)])
async def habits_log(body: HabitLogIn):
    """
    Mark one habit done/undone for a date. Appends a full-day snapshot so the
    log stays in the one-row-per-write format the pipeline and Streamlit use.
    """
    if body.habit not in HABITS:
        raise HTTPException(422, f"unknown habit '{body.habit}'")
    try:
        log_date = validate_log_date(body.date)
    except ValueError as e:
        raise HTTPException(422, str(e))

    current = _day_state(log_date)
    values = {h["key"]: h["done"] for h in current["habits"]}
    values[body.habit] = body.done
    HABITS_LOG.append({"date": log_date, "logged_at": timestamp(), **values})
    return _day_state(log_date)


@router.get("/recent")
async def habits_recent(days: int = 21):
    """
    Last N days (oldest first) straight from the log, so it's current without
    a sync. Days with no entry come back with every habit false.
    """
    days = max(1, min(days, 120))
    latest = HABITS_LOG.latest_by("date")
    out = []
    for d in date_window(days):
        state = _day_state(d.isoformat(), latest)
        out.append({
            "date": state["date"],
            "logged": state["logged_at"] is not None,
            "done_count": state["done_count"],
            **{h["key"]: h["done"] for h in state["habits"]},
        })
    return out


@router.get("/streaks")
async def habits_streaks(request: Request):
    """Current and longest streaks per habit."""
    db = get_db(request)
    return query(db, """
        SELECT habit, current_streak, longest_streak
        FROM main_marts.mart_habit_streaks
        ORDER BY habit
    """)


@router.get("/history")
async def habits_history(request: Request, days: int = 60):
    """Last N days of habit performance."""
    db = get_db(request)
    return query(db, f"""
        SELECT log_date, meditation, pushups_100, nonfiction_pages_10, fiction_pages_10,
               habits_completed_count, daily_completion_pct
        FROM main_marts.mart_habit_performance
        WHERE log_date >= (current_date - interval {days} day)::varchar
        ORDER BY log_date DESC
    """)


@router.get("/ytd")
async def habits_ytd(request: Request):
    """Year-to-date completion rates per habit."""
    db = get_db(request)
    return query(db, """
        SELECT habit, done_days, days_observed, completion_rate_pct
        FROM habits.habit_summary
        WHERE year = year(current_date)
        ORDER BY habit
    """)


@router.get("/quote")
async def habits_quote():
    """Today's motivational quote (zenquotes with local fallback)."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get("https://zenquotes.io/api/today")
            if r.status_code == 200:
                data = r.json()
                if data:
                    return {"quote": data[0]["q"], "author": data[0]["a"]}
    except Exception:
        pass
    idx = today_local().timetuple().tm_yday % len(FALLBACK_QUOTES)
    q, a = FALLBACK_QUOTES[idx]
    return {"quote": q, "author": a}
