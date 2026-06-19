"""
/api/goals — goal progress, pace, domain grouping.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Request

from api.deps import get_db, query, query_one

router = APIRouter()


def _pace_status(progress_pct: float | None, goal_type: str | None) -> str:
    """
    Determine if a goal is on-track, at-risk, or behind based on
    current date progress through the year.
    """
    if progress_pct is None:
        return "unknown"
    doy = date.today().timetuple().tm_yday
    year_pct = doy / 365 * 100
    if goal_type == "binary":
        return "on_track" if progress_pct >= 100 else "in_progress"
    gap = progress_pct - year_pct
    if gap >= -5:
        return "on_track"
    elif gap >= -15:
        return "at_risk"
    else:
        return "behind"


@router.get("/progress")
async def goals_progress(request: Request):
    """All goals with progress, pace, and status."""
    db   = get_db(request)
    rows = query(db, """
        SELECT domain, goal_key, goal_value_type, target_numeric,
               current_value, progress_percent, unit, description
        FROM main_marts.mart_goal_progress
        ORDER BY domain, goal_key
    """)

    # Enrich with pace status and formatted label
    for row in rows:
        row["pace_status"] = _pace_status(
            row.get("progress_percent"),
            row.get("goal_value_type")
        )
        # Format label: remove underscores, title case
        key = row.get("goal_key", "")
        # Strip trailing _YYYY or _N suffixes
        label = key.rsplit("_", 1)[0] if key[-1].isdigit() else key
        row["label"] = label.replace("_", " ").title()

    return rows


@router.get("/by-domain")
async def goals_by_domain(request: Request):
    """Goals grouped by domain."""
    db   = get_db(request)
    rows = query(db, """
        SELECT domain, goal_key, goal_value_type, target_numeric,
               current_value, progress_percent, unit
        FROM main_marts.mart_goal_progress
        ORDER BY domain, goal_key
    """)

    domains: dict = {}
    for row in rows:
        d = row.get("domain", "Other")
        if d not in domains:
            domains[d] = []
        pp = row.get("progress_percent")
        doy = date.today().timetuple().tm_yday
        year_pct = doy / 365 * 100
        row["pace_status"] = _pace_status(pp, row.get("goal_value_type"))
        row["label"] = row.get("goal_key", "").replace("_", " ").title()
        domains[d].append(row)

    return [{"domain": d, "goals": goals} for d, goals in domains.items()]


@router.get("/summary")
async def goals_summary(request: Request):
    """High-level goal summary: total, on_track, at_risk, behind."""
    db   = get_db(request)
    rows = query(db, """
        SELECT progress_percent, goal_value_type
        FROM main_marts.mart_goal_progress
    """)

    counts = {"on_track": 0, "at_risk": 0, "behind": 0, "unknown": 0, "total": len(rows)}
    for row in rows:
        status = _pace_status(row.get("progress_percent"), row.get("goal_value_type"))
        counts[status] = counts.get(status, 0) + 1

    return counts
