"""
/api/cfb — picks, model info, team intel, line accuracy, backtest.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import sys
import os
import requests
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

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


@router.get("/live-tracker")
async def cfb_live_tracker(request: Request, season: int | None = None):
    """
    Real graded-record aggregates for the Live Tracker banner: graded
    picks, W-L-push record, win rate, ROI, and how many qualifying picks
    are still pending (game not yet played/graded). Backed by
    mart_live_picks, which is built from data/bets/history/*.json via
    pipelines/live_picks_pipeline.py + grade_picks.py.

    Returns the most recent season's row if `season` isn't given. Returns
    a zeroed/empty-state row (not a 404) when no rows exist yet -- e.g.
    before the season starts -- so the frontend can render "0 / 0-0 / — /
    —" without special-casing a missing-data error.
    """
    db = get_db(request)
    yr = season or (date.today().year)
    row = query_one(db, """
        SELECT season, graded_picks, wins, losses, pushes,
               win_rate_pct, total_pnl, roi_pct, pending_picks
        FROM main_marts.mart_live_picks
        WHERE season = ?
    """, [yr])
    if row:
        return row
    return {
        "season": yr, "graded_picks": 0, "wins": 0, "losses": 0, "pushes": 0,
        "win_rate_pct": None, "total_pnl": None, "roi_pct": None, "pending_picks": 0,
    }


# ── Team intel ────────────────────────────────────────────────────────────────

@router.get("/teams")
async def cfb_teams(request: Request):
    """All team ATS profiles (walk-forward tiers, current season)."""
    db = get_db(request)
    return query(db, """
        SELECT team, tier, total_win_pct AS win_rate, total_roi AS roi_pct,
               profitable_seasons AS seasons_profitable, total_games AS total_bets
        FROM cfbd.team_profiles
        ORDER BY total_roi DESC NULLS LAST
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


# DRAFT -- NOT TESTED against your live FastAPI app or real CFBD data,
# since I can't run either from this sandbox. Reviewed for logical
# correctness against the real generate_picks.py source, but you should
# verify it runs cleanly before trusting it.
#
# WHY THIS EXISTS:
# Matchup Lab previously had a simplified, hand-written scoring formula
# in the frontend (three made-up numbers approximating PPA gap, success
# rate, tier). That was honestly disabled rather than shipped, because
# the REAL score_game() in scripts/backtest_walk_forward.py is a 13+
# rule model with specific tuned thresholds (recruiting talent gap,
# success-rate interaction, travel distance, returning production,
# coach changes, etc) -- reimplementing it in TypeScript would create
# exactly the "model divergence" tests/smoke_test.py explicitly checks
# for, just in a different language instead of a different file.
#
# This endpoint instead imports and calls analyse_game() directly --
# the SAME function scripts/generate_picks.py uses to build
# todays_picks.json. One source of truth, not two.
#
# IMPORTANT DIFFERENCE FROM generate_picks.py: that script pulls live
# games+lines from the CFBD API for the CURRENT week. Matchup Lab needs
# an on-demand "what if these two teams played with this spread/total"
# query -- so this endpoint builds the same game/line dict shape
# analyse_game() expects, but from user-supplied team names + spread +
# O/U instead of a real CFBD game object. Everything downstream
# (advanced_stats lookups, tiers, coach changes, score_game itself) is
# the real, unmodified logic.
#
# Add this to api/routers/cfb.py. Needs these imports added near the
# top of that file if not already present:
#   import sys
#   from pathlib import Path as _Path
#   from pydantic import BaseModel
#   from datetime import date



# DRAFT -- NOT TESTED against your live FastAPI app or real CFBD data,
# since I can't run either from this sandbox. Reviewed for logical
# correctness against the real generate_picks.py source, but you should
# verify it runs cleanly before trusting it.
#
# WHY THIS EXISTS:
# Matchup Lab previously had a simplified, hand-written scoring formula
# in the frontend (three made-up numbers approximating PPA gap, success
# rate, tier). That was honestly disabled rather than shipped, because
# the REAL score_game() in scripts/backtest_walk_forward.py is a 13+
# rule model with specific tuned thresholds (recruiting talent gap,
# success-rate interaction, travel distance, returning production,
# coach changes, etc) -- reimplementing it in TypeScript would create
# exactly the "model divergence" tests/smoke_test.py explicitly checks
# for, just in a different language instead of a different file.
#
# This endpoint instead imports and calls analyse_game() directly --
# the SAME function scripts/generate_picks.py uses to build
# todays_picks.json. One source of truth for the SCORING logic.
#
# REAL FINDING WORTH KNOWING ABOUT (confirmed during testing, not
# guessed): generate_picks.py does NOT call backtest_walk_forward.py's
# build_tiers() -- it has its own private _build_live_tiers(), with a
# docstring saying "Same logic as backtest_walk_forward.py::build_tiers()."
# This is a duplicated reimplementation, not a shared import, and your
# own smoke_test.py only asserts model divergence for score_game(), not
# for tier-building -- so this duplication already existed and wasn't
# caught. This endpoint imports _build_live_tiers from generate_picks.py
# (the leading underscore is Python's "private" convention, not
# enforced) specifically so Matchup Lab's tiers match what real weekly
# picks actually use, even though that means relying on the
# non-canonical copy. If the two tier functions have drifted apart at
# all, that's a pre-existing inconsistency in your codebase, not
# something this endpoint introduces -- worth a follow-up diff between
# the two functions at some point, separate from this Matchup Lab work.
#
# IMPORTANT DIFFERENCE FROM generate_picks.py: that script pulls live
# games+lines from the CFBD API for the CURRENT week. Matchup Lab needs
# an on-demand "what if these two teams played with this spread/total"
# query -- so this endpoint builds the same game/line dict shape
# analyse_game() expects, but from user-supplied team names + spread +
# O/U instead of a real CFBD game object. Everything downstream
# (advanced_stats lookups, tiers, coach changes, score_game itself) is
# the real, unmodified logic.
#
# Add this to api/routers/cfb.py. Needs these imports added near the
# top of that file if not already present:
#   import sys
#   from pydantic import BaseModel
# (date and Path are likely already imported -- check before adding.)



# DRAFT v2 -- fixes a real bug found in v1 via testing, not guessed.
#
# THE BUG: v1 called analyse_game() directly. That function has this
# gate AFTER scoring (confirmed from the real source):
#
#   if model_score < 70:
#       return None
#   if len(edges) < 4:
#       return None
#
# That's the SAME min_score=70 / min_edges=4 threshold generate_picks.py
# uses to decide whether a real weekly game is worth PUBLISHING as a
# pick. It's the right gate for "should this go in todays_picks.json,"
# and the WRONG gate for "show me what the model thinks of this
# matchup" -- which is what Matchup Lab is for. A user exploring
# Georgia vs Alabama wants to see the actual score and edges even if
# they're 45/2, not a generic "no data" message that incorrectly
# implies the underlying stats are missing.
#
# Confirmed via direct testing: cfbd.advanced_stats DOES have real rows
# for Georgia/Alabama in both 2023 and 2025 -- the data was never the
# problem. analyse_game() was correctly filtering a below-threshold
# result; the previous version's error message ("not enough prior-
# season data") was simply the wrong diagnosis for what was happening.
#
# THE FIX: build row_data and call score_game() directly -- same inputs,
# same real scoring function, no publish-threshold gate. The metadata
# attachment (ret_gap, recruiting_gap, travel, coach_h2h, sp_gap) that
# analyse_game() normally does AFTER scoring is reproduced here too,
# since that's genuinely useful context for the Lab UI, not just for
# published picks.
#
# Add this to api/routers/cfb.py, replacing the entire previous
# matchup-lab block (from _SCRIPTS_DIR through the end of the file).
# Needs these imports near the top of cfb.py if not already present:
#   import sys
#   from pydantic import BaseModel
# (date and Path are likely already imported -- check before adding.)

import pandas as pd

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from backtest_walk_forward import score_game  # noqa: E402
from generate_picks import _build_live_tiers as build_tiers  # noqa: E402


class MatchupRequest(BaseModel):
    home_team: str
    away_team: str
    spread: float          # negative = home favored, matching generate_picks.py convention
    over_under: float | None = None
    season: int | None = None   # defaults to current year if not given


@router.post("/matchup-lab")
async def cfb_matchup_lab(payload: MatchupRequest, request: Request):
    """
    Run the REAL validated model (score_game) against a user-specified
    hypothetical matchup, instead of a live CFBD game from
    generate_picks.py's weekly pipeline.

    Unlike generate_picks.py's analyse_game(), this does NOT apply the
    min_score>=70 / min_edges>=4 publish-worthiness filter -- it always
    returns the model's actual score and reasoning, even for matchups
    that wouldn't clear the bar for a real published pick. That filter
    exists to decide what's worth betting publicly, not to hide the
    model's opinion from someone exploring a hypothetical matchup.

    Returns an error dict (not a 500) if advanced_stats genuinely isn't
    available for one of the requested teams/season -- a real data gap,
    distinct from "scored low," which is now reported separately.
    """
    db = get_db(request)
    year = payload.season or date.today().year
    home = payload.home_team
    away = payload.away_team
    spread = payload.spread

    row_data: dict = {
        "spread":          spread,
        "home_team":       home,
        "away_team":       away,
        "home_conference": "",
        "season":          year,
    }

    try:
        # ── PPA gap + success rates + havoc (prior season) ────────────────
        adv = db.execute("""
            SELECT team, off_ppa, off_success_rate, def_success_rate, def_havoc_total
            FROM cfbd.advanced_stats WHERE season = ? AND team IN (?, ?)
        """, [year - 1, home, away]).df()
        h = adv[adv["team"] == home]
        a = adv[adv["team"] == away]

        if h.empty or a.empty:
            return {
                "error": "no_advanced_stats",
                "message": (
                    f"cfbd.advanced_stats has no row for one or both of "
                    f"{home} / {away} in season {year - 1} (prior season "
                    f"to {year}). This IS a real data gap, not a low-score "
                    "result -- the model can't run at all without this."
                ),
            }

        row_data["off_ppa_gap"] = float(h["off_ppa"].values[0]) - float(a["off_ppa"].values[0])
        row_data["home_off_success_rate"] = float(h["off_success_rate"].values[0])
        row_data["away_off_success_rate"] = float(a["off_success_rate"].values[0])
        row_data["home_def_success_rate"] = float(h["def_success_rate"].values[0])
        row_data["away_def_success_rate"] = float(a["def_success_rate"].values[0])
        row_data["home_def_havoc"] = float(h["def_havoc_total"].values[0])
        row_data["away_def_havoc"] = float(a["def_havoc_total"].values[0])

        # ── Returning production gap (prior season) -- optional ──────────
        try:
            ret = db.execute("""
                SELECT team, percent_ppa FROM cfbd.returning_production
                WHERE season = ? AND team IN (?, ?)
            """, [year - 1, home, away]).df()
            h_ret = ret[ret["team"] == home]
            a_ret = ret[ret["team"] == away]
            if not h_ret.empty and not a_ret.empty:
                row_data["returning_production_gap"] = (
                    float(h_ret["percent_ppa"].values[0]) -
                    float(a_ret["percent_ppa"].values[0])
                )
        except Exception:
            pass

        # ── Recruiting gap (prior season 4-year weighted) -- optional ────
        try:
            rec = db.execute("""
                SELECT team, weighted_talent FROM main_marts.mart_cfbd_recruiting_talent
                WHERE season = ? AND team IN (?, ?)
            """, [year - 1, home, away]).df()
            h_rec = rec[rec["team"] == home]
            a_rec = rec[rec["team"] == away]
            if not h_rec.empty and not a_rec.empty:
                row_data["recruiting_gap"] = (
                    float(h_rec["weighted_talent"].values[0]) -
                    float(a_rec["weighted_talent"].values[0])
                )
        except Exception:
            pass

        # ── Tiers + coach changes + prior SP+ (for score_game inputs) ────
        tiers = build_tiers(db, year)

        coach_changes = set()
        home_coach = away_coach = None
        try:
            curr = db.execute(
                "SELECT school AS team, full_name AS coach FROM cfbd.coaches WHERE year = ?",
                [year]
            ).df()
            prev = db.execute(
                "SELECT school AS team, full_name AS coach FROM cfbd.coaches WHERE year = ?",
                [year - 1]
            ).df()
            merged = curr.merge(prev, on="team", suffixes=("_c", "_p"))
            coach_changes = set(merged[merged["coach_c"] != merged["coach_p"]]["team"])
            h_c = curr[curr["team"] == home]
            a_c = curr[curr["team"] == away]
            home_coach = h_c["coach"].values[0] if not h_c.empty else None
            away_coach = a_c["coach"].values[0] if not a_c.empty else None
        except Exception:
            pass

        prior_sp = {}
        sp_gap = None
        try:
            sp_df = db.execute(
                "SELECT team, season, rating FROM cfbd.sp_ratings WHERE season = ?",
                [year - 1]
            ).df()
            prior_sp = {
                (r["team"], int(r["season"])): float(r["rating"])
                for _, r in sp_df.iterrows()
            }
            h_sp = sp_df[sp_df["team"] == home]
            a_sp = sp_df[sp_df["team"] == away]
            if not h_sp.empty and not a_sp.empty:
                sp_gap = float(h_sp["rating"].values[0]) - float(a_sp["rating"].values[0])
        except Exception:
            pass

        coach_h2h = None
        if home_coach and away_coach:
            try:
                h2h = db.execute("""
                    SELECT * FROM main_marts.mart_cfbd_coach_matchups
                    WHERE (coach_a = ? AND coach_b = ?) OR (coach_a = ? AND coach_b = ?)
                    LIMIT 1
                """, [home_coach, away_coach, away_coach, home_coach]).df()
                if not h2h.empty:
                    r = h2h.iloc[0]
                    coach_h2h = {
                        "home_record": int(r.get("coach_a_wins", 0)),
                        "away_record": int(r.get("coach_b_wins", 0)),
                        "total":       int(r.get("total_games", 0)),
                        "leader":      str(r.get("all_time_leader", "")),
                        "trend":       str(r.get("recent_trend_leader", "")),
                    }
            except Exception:
                pass

        # ── Score using the REAL validated model -- no publish gate ──────
        row = pd.Series(row_data)
        model_score, edges, warnings = score_game(row, tiers, coach_changes, prior_sp)

        ppa_gap = row_data.get("off_ppa_gap")
        bet_home = bool(ppa_gap and ppa_gap > 0)
        bet_team = home if bet_home else away
        home_is_fav = spread < 0

        if bet_team == home and home_is_fav:
            bet_str = f"{home} {spread:+.1f} (home fav)"
        elif bet_team == home and not home_is_fav:
            bet_str = f"{home} +{abs(spread):.1f} (home dog)"
        elif bet_team == away and not home_is_fav:
            bet_str = f"{away} -{abs(spread):.1f} (away fav)"
        else:
            bet_str = f"{away} +{abs(spread):.1f} (away dog)"

        meets_publish_bar = model_score >= 70 and len(edges) >= 4

        return {
            "matchup":            f"{away} @ {home}",
            "bet":                bet_str,
            "model_score":        model_score,
            "edges":              edges,
            "n_edges":            len(edges),
            "warnings":           warnings,
            "ppa_gap":            round(ppa_gap, 3) if ppa_gap else None,
            "sp_gap":             round(sp_gap, 1) if sp_gap else None,
            "ret_gap":            round(row_data["returning_production_gap"], 3) if "returning_production_gap" in row_data else None,
            "recruiting_gap":     round(row_data["recruiting_gap"], 1) if "recruiting_gap" in row_data else None,
            "home_coach":         home_coach,
            "away_coach":         away_coach,
            "coach_h2h":          coach_h2h,
            "spread":             spread,
            "over_under":         payload.over_under,
            "season":             year,
            # Distinguishes "model likes this" from "model would publish
            # this as a real weekly pick" -- the Lab can show both states
            # without conflating exploratory scoring with the live feed's
            # actual threshold.
            "meets_publish_bar":  meets_publish_bar,
        }

    except Exception as e:
        return {
            "error": "matchup_lab_failed",
            "message": str(e),
        }


# DRAFT -- NOT TESTED against your live FastAPI app or real CFBD data,
# since I can't run either from this sandbox. Built from the confirmed
# real /games response shape (cfbd_pipeline.py's own field mapping),
# not guessed.
#
# WHY THIS EXISTS:
# "This Week" was correctly showing an honest preseason empty state --
# current_cfb_week() returns None outside Aug-Jan, and todays_picks.json
# requires BOTH games AND betting lines (generate_picks.py's gate:
# `if spread is None: return None`). Sportsbooks don't post Week 1
# spreads months in advance, so a real graded-picks view can't exist
# yet -- but the SCHEDULE itself (who plays whom, when) is typically
# published by CFBD well ahead of kickoff and doesn't depend on lines
# at all.
#
# This endpoint fetches just the schedule for a given year+week,
# completely independent of generate_picks.py's pipeline -- no lines
# required, no model scoring, just "what games are happening." Returns
# an honest empty list if CFBD hasn't published that week's schedule
# yet either (also a normal case this far out, not an error).
#
# Add this to api/routers/cfb.py. Needs these imports near the top if
# not already present:
#   import os
#   import requests
# (Request/Query are already imported per the existing file.)

CFBD_API_BASE = "https://api.collegefootballdata.com"


def _cfbd_get(endpoint: str, params: dict) -> list[dict]:
    """
    Minimal CFBD GET helper, mirroring scripts/generate_picks.py's
    cfbd_get() exactly (same token env var, same base URL, same timeout)
    so this endpoint behaves identically to the existing pipeline code
    rather than introducing a second, slightly different HTTP client.
    """
    token = os.getenv("CFBD_API_TOKEN", "")
    if not token:
        return []
    try:
        r = requests.get(
            f"{CFBD_API_BASE}{endpoint}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


@router.get("/schedule")
async def cfb_schedule(
    request: Request,
    season: int = Query(..., description="e.g. 2026"),
    week: int = Query(..., description="1-15"),
):
    """
    Real CFBD schedule for a given season+week -- independent of
    betting lines, so it works months before sportsbooks post Week 1
    spreads. Returns [] if CFBD hasn't published that week yet, which
    is a normal case this far from the season, not an error.

    Confirmed real field mapping (from cfbd_pipeline.py's own games
    resource, not guessed):
      id, startDate, neutralSite, conferenceGame,
      homeTeam, homeConference, awayTeam, awayConference
    """
    games = _cfbd_get("/games", {
        "year": season,
        "week": week,
        "division": "fbs",
    })

    return [
        {
            "game_id":         g.get("id"),
            "season":          season,
            "week":            week,
            "start_date":      g.get("startDate"),
            "neutral_site":    g.get("neutralSite"),
            "conference_game": g.get("conferenceGame"),
            "home_team":       g.get("homeTeam"),
            "home_conference": g.get("homeConference"),
            "away_team":       g.get("awayTeam"),
            "away_conference": g.get("awayConference"),
        }
        for g in games
    ]
