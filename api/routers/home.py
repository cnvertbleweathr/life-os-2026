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
        SELECT miles_total AS total_miles, runs_count AS total_runs, miles_total AS ytd_miles
        FROM strava.running_summary
        WHERE year = ?
        LIMIT 1
    """, [year]) or {}

    # Weekly miles (last 7 days)
    weekly_miles = query_one(db, """
        SELECT round(sum(distance_miles), 1) as miles, count(*) as runs
        FROM strava.activities
        WHERE is_run = true
          AND start_date >= current_date - interval 7 day
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
        WHERE year = ?
    """, [year]) or {}

    # ── Calendar — next 30 days ───────────────────────────────────────────────
    events: list[dict] = []
    if EVENTS_CSV.exists():
        import pandas as pd
        from api.deps import _clean
        df = pd.read_csv(EVENTS_CSV)
        # start mixes all-day dates ("2026-01-04") with offset-aware
        # timestamps ("2026-01-06T08:00:00-06:00"). Vectorized
        # pd.to_datetime(..., utc=True) silently returns NaT for every row
        # when a column mixes those formats (pandas 3.0 behavior) - parsing
        # element-wise avoids that.
        df["date"] = df["start"].apply(lambda x: pd.to_datetime(x, errors="coerce", utc=True))
        df["title"] = df["summary"]
        mask = (df["date"].dt.date >= date.today()) & \
               (df["date"].dt.date <= date.today().replace(month=min(date.today().month + 1, 12)))
        upcoming = df[mask].sort_values("date").head(20)
        raw_events = upcoming[["date", "title"]].assign(
            date=upcoming["date"].dt.strftime("%b %-d")
        ).to_dict(orient="records")
        events = [{k: _clean(v) for k, v in row.items()} for row in raw_events]

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

@router.get("/briefs")
async def get_briefs(request: Request, brief_type: str = None):
    """Get life briefs (daily or weekly)."""
    db = get_db(request)
    
    if brief_type:
        rows = query(db, """
            SELECT brief_date, brief_type, brief_content, token_count, generated_at
            FROM dashboard_life_briefs
            WHERE brief_type = ?
            LIMIT 10
        """, [brief_type])
    else:
        rows = query(db, """
            SELECT brief_date, brief_type, brief_content, token_count, generated_at
            FROM dashboard_life_briefs
            LIMIT 10
        """)
    
    return [dict(row) for row in rows]


@router.get("/brief/latest")
async def get_latest_brief(request: Request, brief_type: str = "daily"):
    """Get the latest brief (daily or weekly)."""
    db = get_db(request)
    
    row = query_one(db, """
        SELECT brief_date, brief_type, brief_content, token_count, generated_at
        FROM dashboard_life_briefs
        WHERE brief_type = ?
        ORDER BY generated_at DESC
        LIMIT 1
    """, [brief_type])
    
    return dict(row) if row else None


@router.get("/wod")
async def get_wod():
    """Today's WOD from CrossFit Park Hill."""
    return _load_json(WOD_PATH) or {}

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
    from api.deps import _clean
    df = pd.read_csv(EVENTS_CSV)
    # See home_summary for why this is parsed element-wise.
    df["date"] = df["start"].apply(lambda x: pd.to_datetime(x, errors="coerce", utc=True))
    df["title"] = df["summary"]
    mask = df["date"].dt.date >= date.today()
    upcoming = df[mask].sort_values("date").head(30)
    raw_events = upcoming[["date", "title"]].assign(
        date=upcoming["date"].dt.strftime("%Y-%m-%d")
    ).to_dict(orient="records")
    return [{k: _clean(v) for k, v in row.items()} for row in raw_events]


@router.get("/streams")
async def get_streams():
    """Today's sports streams."""
    return _load_json(STREAMS_PATH) or {}
