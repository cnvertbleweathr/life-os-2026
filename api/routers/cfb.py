"""
/api/cfb — picks, model info, team intel, line accuracy, backtest.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, Request

from api.deps import get_db, query, query_one

router     = APIRouter()
ROOT       = Path(__file__).resolve().parents[2]
PICKS_PATH = ROOT / "data" / "bets" / "todays_picks.json"


# ── Picks ─────────────────────────────────────────────────────────────────────

@router.get("/picks")
async def cfb_picks(
    min_score: int = Query(70, description="Minimum model score"),
    limit:     int = Query(20),
):
    """This week's qualifying picks, sorted by model score descending."""
    if not PICKS_PATH.exists():
        return []
    try:
        picks = json.loads(PICKS_PATH.read_text())
        picks = [p for p in picks if p.get("model_score", p.get("confidence", 0)) >= min_score]
        picks.sort(key=lambda x: x.get("model_score", x.get("confidence", 0)), reverse=True)
        return picks[:limit]
    except Exception:
        return []


@router.get("/picks/summary")
async def cfb_picks_summary():
    """Summary of this week's picks: count, avg score, week number."""
    if not PICKS_PATH.exists():
        return {"count": 0, "picks": []}
    try:
        picks = json.loads(PICKS_PATH.read_text())
        if not picks:
            return {"count": 0}
        avg_score = sum(p.get("model_score", p.get("confidence", 0)) for p in picks) / len(picks)
        return {
            "count":     len(picks),
            "avg_score": round(avg_score, 1),
            "week":      picks[0].get("week") if picks else None,
            "season":    picks[0].get("season") if picks else None,
        }
    except Exception:
        return {"count": 0}


# ── Team intel ────────────────────────────────────────────────────────────────

@router.get("/teams")
async def cfb_teams(request: Request):
    """All team ATS profiles (walk-forward tiers, current season)."""
    db = get_db(request)
    return query(db, """
        SELECT team, tier, win_rate, roi_pct, seasons_profitable, total_bets
        FROM cfbd.team_profiles
        ORDER BY roi_pct DESC NULLS LAST
    """)


@router.get("/team/{team}")
async def cfb_team(team: str, request: Request):
    """Single team profile + recent game context."""
    db = get_db(request)
    profile = query_one(db, """
        SELECT * FROM cfbd.team_profiles WHERE team = ? LIMIT 1
    """, [team])

    recent_games = query(db, """
        SELECT season, week, home_team, away_team, spread, spread_result,
               off_ppa_gap, home_conference
        FROM main_marts.mart_cfbd_game_context
        WHERE (home_team = ? OR away_team = ?)
          AND season = year(current_date) - 1
        ORDER BY season DESC, week DESC
        LIMIT 10
    """, [team, team])

    prior_season_adv = query_one(db, """
        SELECT off_ppa, def_ppa, off_success_rate, def_success_rate,
               def_havoc_total, off_rush_ppa
        FROM cfbd.advanced_stats
        WHERE team = ? AND season = year(current_date) - 1
        LIMIT 1
    """, [team])

    return {
        "profile":       profile,
        "recent_games":  recent_games,
        "advanced_stats": prior_season_adv,
    }


# ── Line accuracy & edge factors ─────────────────────────────────────────────

@router.get("/line-accuracy")
async def cfb_line_accuracy(
    request: Request,
    season:  int  | None = None,
    team:    str  | None = None,
    limit:   int         = Query(100, le=500),
):
    """Historical line accuracy — filterable by season and team."""
    db     = get_db(request)
    yr     = season or (date.today().year - 1)
    wheres = ["season = ?"]
    params: list[Any] = [yr]
    if team:
        wheres.append("(home_team = ? OR away_team = ?)")
        params += [team, team]
    where_clause = " AND ".join(wheres)
    return query(db, f"""
        SELECT season, week, home_team, away_team, spread, spread_result,
               ou_result, home_score, away_score, home_conference, provider
        FROM main_marts.mart_cfbd_line_accuracy
        WHERE {where_clause}
        ORDER BY season DESC, week DESC
        LIMIT {limit}
    """, params)


@router.get("/game-context/{game_id}")
async def cfb_game_context(game_id: int, request: Request):
    """Full game context for a specific game ID."""
    db = get_db(request)
    return query_one(db, """
        SELECT *
        FROM main_marts.mart_cfbd_game_context
        WHERE game_id = ?
        LIMIT 1
    """, [game_id])


# ── Recruiting ────────────────────────────────────────────────────────────────

@router.get("/recruiting/{team}")
async def cfb_recruiting(team: str, request: Request):
    """4-year weighted recruiting talent for a team."""
    db = get_db(request)
    return query(db, """
        SELECT season, weighted_talent, weighted_rank, talent_percentile,
               single_year_points, single_year_rank
        FROM main_marts.mart_cfbd_recruiting_talent
        WHERE team = ?
        ORDER BY season DESC
        LIMIT 5
    """, [team])


# ── Model metadata ────────────────────────────────────────────────────────────

@router.get("/model-info")
async def cfb_model_info():
    """Model validation summary — static from last backtest run."""
    return {
        "version":            "v3 walk-forward",
        "test_seasons":       [2022, 2023, 2024, 2025],
        "total_bets":         318,
        "record":             "224-94",
        "win_rate_pct":       70.4,
        "roi_pct":            34.5,
        "profitable_seasons": "4/4",
        "min_model_score":    70,
        "min_edges":          4,
        "disabled_signals":   ["SP+ alignment", "Defensive havoc"],
        "active_signals": [
            "Prior-season PPA gap",
            "Success rate interaction",
            "Recruiting/talent context",
            "Team tier penalties",
            "Returning production",
            "Spread range filter",
            "Coach change filter",
            "Conference filter",
        ],
        "notes": (
            "Model score is ordinal, not a probability. "
            "PPA 0.30+ bucket: small sample (30 games), high variance. "
            "Weeks 1-4 historically strongest (+39.5% ROI)."
        ),
    }
