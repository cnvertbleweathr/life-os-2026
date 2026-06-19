"""
/api/habits — today's checklist, streaks, YTD completion, history.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

from api.deps import get_db, query, query_one

router   = APIRouter()
ROOT     = Path(__file__).resolve().parents[2]
LOG_PATH = ROOT / "data" / "habits" / "habits_log.jsonl"

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


def _load_today() -> dict:
    today = date.today().isoformat()
    if not LOG_PATH.exists():
        return {}
    for line in reversed(LOG_PATH.read_text().splitlines()):
        try:
            row = json.loads(line)
            if row.get("date") == today:
                return row
        except Exception:
            continue
    return {}


@router.get("/today")
async def habits_today():
    """Today's habit state from the local JSONL log."""
    today = date.today().isoformat()
    existing = _load_today()
    return {
        "date": today,
        "habits": [
            {
                "key":   k,
                "label": label,
                "done":  bool(existing.get(k, False)),
            }
            for k, label in HABITS.items()
        ],
        "done_count":  sum(1 for k in HABITS if existing.get(k, False)),
        "total_count": len(HABITS),
    }


@router.get("/streaks")
async def habits_streaks(request: Request):
    """Current and longest streaks per habit."""
    db = get_db(request)
    return query(db, """
        SELECT habit, current_streak, longest_streak, last_done_date
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
    idx = date.today().timetuple().tm_yday % len(FALLBACK_QUOTES)
    q, a = FALLBACK_QUOTES[idx]
    return {"quote": q, "author": a}
