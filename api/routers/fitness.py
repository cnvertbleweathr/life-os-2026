"""
/api/fitness — running (Strava), CrossFit (SugarWOD), today's WOD.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Request

from api.deps import _clean, get_db, query, query_one

router       = APIRouter()
ROOT         = Path(__file__).resolve().parents[2]
SUGARWOD     = ROOT / "data" / "sugarwod" / "processed" / "workouts_clean.csv"
WOD_PATH     = ROOT / "data" / "fitness" / "wod_today.json"
PH_LOGO_URL  = "/static/parkhill_logo.png"


@router.get("/summary")
async def fitness_summary(request: Request):
    """YTD running summary + recent runs + CrossFit attendance."""
    db   = get_db(request)
    year = date.today().year

    running = query_one(db, """
        SELECT miles_total AS total_miles, runs_count AS total_runs,
               avg_pace_min_per_mile AS avg_pace_min_mile, miles_total AS ytd_miles
        FROM strava.running_summary WHERE year = ? LIMIT 1
    """, [year]) or {}

    recent_runs = query(db, """
        SELECT
            start_date::date AS run_date,
            round(distance_miles, 2) AS miles,
            round(moving_time_s / 60.0, 1) AS minutes,
            round((moving_time_s / 60.0) / distance_miles, 2) AS pace
        FROM strava.activities
        WHERE is_run = true
          AND start_date >= current_date - interval 30 day
        ORDER BY start_date DESC
        LIMIT 10
    """)

    # Weekly mileage — last 12 weeks
    weekly = query(db, f"""
        WITH all_weeks AS (
            SELECT strftime(range::date, '%Y-W%W') AS week
            FROM range(DATE '{year}-01-01', current_date + INTERVAL 1 DAY, INTERVAL 1 WEEK)
        ),
        run_weeks AS (
            SELECT strftime(start_date::date, '%Y-W%W') AS week,
                   round(sum(distance_miles), 1) AS miles
            FROM strava.activities
            WHERE is_run = true AND start_date >= DATE '{year}-01-01'
            GROUP BY 1
        )
        SELECT a.week, coalesce(r.miles, 0) AS miles
        FROM all_weeks a
        LEFT JOIN run_weeks r ON r.week = a.week
        ORDER BY a.week DESC
        LIMIT 12
    """)

    return {
        "running_summary": running,
        "recent_runs":     recent_runs,
        "weekly_miles":    list(reversed(weekly)),
    }


@router.get("/wod")
async def get_wod():
    """Today's WOD from CrossFit Park Hill."""
    if not WOD_PATH.exists():
        return {"fetched_ok": False, "text": None}
    try:
        return json.loads(WOD_PATH.read_text())
    except Exception:
        return {"fetched_ok": False, "text": None}


@router.get("/crossfit")
async def crossfit_log(limit: int = 50):
    """Recent CrossFit workouts from SugarWOD CSV."""
    if not SUGARWOD.exists():
        return []
    df = pd.read_csv(SUGARWOD)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["date"].dt.year == date.today().year]
    df = df.sort_values("date", ascending=False).head(limit)
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    df["is_pr"] = df["pr"].astype(str).str.strip().str.upper() == "PR"
    cols = ["date", "title", "barbell_lift", "best_result_raw", "best_result_unit", "is_pr"]
    available = [c for c in cols if c in df.columns]
    raw_rows = df[available].to_dict(orient="records")
    return [{k: _clean(v) for k, v in row.items()} for row in raw_rows]


@router.get("/prs")
async def personal_records():
    """All PRs from SugarWOD."""
    if not SUGARWOD.exists():
        return []
    df = pd.read_csv(SUGARWOD)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["is_pr"] = df["pr"].astype(str).str.strip().str.upper() == "PR"
    prs = df[df["is_pr"]].sort_values("date", ascending=False)
    prs["date"] = prs["date"].dt.strftime("%Y-%m-%d")
    cols = ["date", "title", "barbell_lift", "best_result_raw", "best_result_unit"]
    available = [c for c in cols if c in prs.columns]
    raw_rows = prs[available].to_dict(orient="records")
    return [{k: _clean(v) for k, v in row.items()} for row in raw_rows]
