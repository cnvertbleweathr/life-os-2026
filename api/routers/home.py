"""
/api/home — everything the Home page needs in one or a few requests.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

from api.deps import get_db, query, query_one

router  = APIRouter()
ROOT    = Path(__file__).resolve().parents[2]


# ── File paths ────────────────────────────────────────────────────────────────
EVENTS_CSV   = ROOT / "data" / "calendar" / "processed" / "events_clean_2026.csv"
WOD_PATH     = ROOT / "data" / "fitness" / "wod_today.json"
DAILY10_PATH = ROOT / "data" / "spotify" / "processed" / "daily10_latest.json"
PICKS_PATH   = ROOT / "data" / "bets" / "todays_picks.json"
HABITS_LOG   = ROOT / "data" / "habits" / "habits_log.jsonl"
STREAMS_PATH = ROOT / "data" / "streams" / "today.json"


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


@router.get("/summary")
async def home_summary(request: Request):
    """
    Everything the Home page needs in one request:
      - today's date
      - stat cards (running, habits, books)
      - upcoming calendar events
      - today's WOD
      - Daily 10 playlist
      - top CFB picks (max 3)
      - goals summary
      - streams
    """
    db      = get_db(request)
    today   = date.today().isoformat()
    year    = date.today().year

    # ── Stat cards ────────────────────────────────────────────────────────────
    running = query_one(db, """
        SELECT total_miles, total_runs, ytd_miles
        FROM strava.running_summary
        WHERE year = ?
        LIMIT 1
    """, [year]) or {}

    # Weekly miles (last 7 days)
    weekly_miles = query_one(db, """
        SELECT round(sum(distance_miles), 1) as miles, count(*) as runs
        FROM strava.activities
        WHERE start_date >= (current_date - interval 7 day)::varchar
    """) or {}

    # Habits today
    habits_today: dict[str, bool] = {}
    if HABITS_LOG.exists():
        for line in reversed(HABITS_LOG.read_text().splitlines()):
            try:
                row = json.loads(line)
                if row.get("date") == today:
                    habits_today = {k: bool(v) for k, v in row.items()
                                    if k not in ("date", "logged_at")}
                    break
            except Exception:
                continue

    habit_keys   = ["meditation", "pushups_100", "nonfiction_pages_10", "fiction_pages_10"]
    habits_done  = sum(1 for k in habit_keys if habits_today.get(k, False))
    habits_total = len(habit_keys)

    # Books
    books = query_one(db, """
        SELECT count(*) as books_read
        FROM hardcover.books_read
        WHERE year(marked_read_at::date) = ?
          AND status = 'read'
    """, [year]) or {}

    # ── Calendar — next 30 days ───────────────────────────────────────────────
    events: list[dict] = []
    if EVENTS_CSV.exists():
        import pandas as pd
        df = pd.read_csv(EVENTS_CSV)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        mask = (df["date"].dt.date >= date.today()) & \
               (df["date"].dt.date <= date.today().replace(month=min(date.today().month + 1, 12)))
        upcoming = df[mask].sort_values("date").head(20)
        events = upcoming[["date", "title", "emoji"]].assign(
            date=upcoming["date"].dt.strftime("%b %-d")
        ).where(pd.notna(upcoming), None).to_dict(orient="records")

    # ── WOD ───────────────────────────────────────────────────────────────────
    wod = _load_json(WOD_PATH) or {}

    # ── Daily 10 ─────────────────────────────────────────────────────────────
    daily10 = _load_json(DAILY10_PATH) or {}

    # ── Top picks (max 3, model_score desc) ──────────────────────────────────
    picks_raw = _load_json(PICKS_PATH) or []
    picks = sorted(picks_raw, key=lambda x: x.get("model_score", 0), reverse=True)[:3]

    # ── Goals summary ─────────────────────────────────────────────────────────
    goals = query(db, """
        SELECT domain, goal_key, current_value, target_numeric, progress_percent
        FROM main_marts.mart_goal_progress
        WHERE progress_percent IS NOT NULL
        ORDER BY domain, goal_key
    """)

    # ── Streams ───────────────────────────────────────────────────────────────
    streams = _load_json(STREAMS_PATH) or {}

    return {
        "date":       today,
        "stat_cards": {
            "weekly_miles": weekly_miles.get("miles"),
            "weekly_runs":  weekly_miles.get("runs"),
            "ytd_miles":    running.get("ytd_miles") or running.get("total_miles"),
            "habits_done":  habits_done,
            "habits_total": habits_total,
            "books_read":   books.get("books_read"),
        },
        "calendar":   events,
        "wod":        wod,
        "daily10":    daily10,
        "picks":      picks,
        "goals":      goals,
        "streams":    streams,
    }


@router.get("/wod")
async def get_wod():
    """Today's WOD from CrossFit Park Hill."""
    return _load_json(WOD_PATH) or {}


@router.get("/calendar")
async def get_calendar():
    """Upcoming calendar events — next 30 days."""
    if not EVENTS_CSV.exists():
        return []
    import pandas as pd
    df = pd.read_csv(EVENTS_CSV)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    mask = df["date"].dt.date >= date.today()
    upcoming = df[mask].sort_values("date").head(30)
    return upcoming[["date", "title", "emoji"]].assign(
        date=upcoming["date"].dt.strftime("%Y-%m-%d")
    ).where(pd.notna(upcoming), None).to_dict(orient="records")


@router.get("/streams")
async def get_streams():
    """Today's sports streams."""
    return _load_json(STREAMS_PATH) or {}
