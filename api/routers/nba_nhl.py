"""
/api/nba-nhl — the NBA and NHL daily slate and the season-to-date pick record.

Source: data/bets/{league}/history/<date>.json, written by scripts/nba_nhl_generate_picks.py
(line captured at pick time) and graded in place by scripts/nba_nhl_grade_picks.py. Reading
the files rather than nba.live_picks / mart_*_live_picks keeps the slate current between
the morning load and the next DLT run; the record mirrors the mart's arithmetic
(dbt/macros/nba_nhl_live_picks.sql): pushes count as entries but not in win% or ROI.

No rule has passed validation (docs/NBA_NHL_ATS_DATA.md → Edge validation), so every game is
NO_BET; NBA games also carry the nba_totals_open_v1 paper test.

ONS_BETS_DIR overrides data/bets (tests, and dev servers pointed at scratch picks).
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()
ROOT = Path(__file__).resolve().parents[2]
LEAGUES = ("nba", "nhl")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EASTERN = ZoneInfo("America/New_York")   # game_date is the US/Eastern date (generator, spines)


def bets_dir() -> Path:
    return Path(os.environ["ONS_BETS_DIR"]) if os.getenv("ONS_BETS_DIR") else ROOT / "data" / "bets"


def _league(league: str) -> str:
    league = league.lower()
    if league not in LEAGUES:
        raise HTTPException(404, f"unknown league {league!r}")
    return league


def _history(league: str) -> Path:
    return bets_dir() / league / "history"


def _dates(league: str) -> list[str]:
    h = _history(league)
    if not h.exists():
        return []
    return sorted(p.stem for p in h.glob("*.json") if DATE_RE.match(p.stem))


def _load(league: str, d: str) -> list[dict]:
    path = _history(league) / f"{d}.json"
    try:
        return json.loads(path.read_text()).get("games", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _paper(g: dict) -> dict | None:
    pe = g.get("paper")
    if not pe:
        return None
    return {k: pe.get(k) for k in ("test", "fires", "side", "pred_total", "captured_total", "gap",
                                   "price", "prices_in_band", "outcome", "pnl", "clv")}


def _game(g: dict) -> dict[str, Any]:
    keys = ("game_id", "season", "season_type", "game_date", "start_time", "matchup", "home_team",
            "away_team", "neutral_site", "captured_at", "captured_after_start", "book", "home_spread",
            "home_spread_price", "away_spread_price", "ml_book", "home_ml", "away_ml", "total_book", "total",
            "over_price", "under_price", "verdict", "bet", "rules_fired", "rules_version",
            "final_status", "home_score", "away_score", "went_ot", "shootout",
            "closing_home_spread", "closing_total", "closing_home_ml", "closing_away_ml", "graded_at")
    out = {k: g.get(k) for k in keys}
    out["rules_fired"] = out["rules_fired"] or []
    out["paper"] = _paper(g)
    return out


def _record(games: list[dict]) -> dict[str, Any]:
    """Season-to-date numbers, same definitions as mart_{league}_live_picks."""
    paper = [g["paper"] for g in games if g.get("paper") and g["paper"].get("fires")]
    graded = [p for p in paper if p.get("outcome") in ("win", "loss", "push")]
    w = sum(p["outcome"] == "win" for p in graded)
    l = sum(p["outcome"] == "loss" for p in graded)
    push = sum(p["outcome"] == "push" for p in graded)
    decided = [p for p in graded if p["outcome"] in ("win", "loss")]
    clvs = [p["clv"] for p in graded if p.get("clv") is not None]
    pnl = sum(p.get("pnl") or 0 for p in decided)
    bets = [g for g in games if g.get("verdict") not in (None, "NO_BET")]
    return {
        "games_logged": len(games),
        "games_graded": sum(1 for g in games if g.get("graded_at")),
        "captured_after_start": sum(1 for g in games if g.get("captured_after_start")),
        "bets": len(bets),
        "paper_entries": len(paper),
        "paper_graded": len(graded),
        "paper_wins": w, "paper_losses": l, "paper_pushes": push,
        "paper_pnl": round(pnl, 3) if decided else None,
        "paper_win_pct": round(100 * w / len(decided), 1) if decided else None,
        "paper_roi": round(100 * pnl / len(decided), 1) if decided else None,
        "paper_clv_avg": round(sum(clvs) / len(clvs), 2) if clvs else None,
        "paper_beat_close_pct": round(100 * sum(c > 0 for c in clvs) / len(clvs), 1) if clvs else None,
    }


def _today() -> str:
    return datetime.now(EASTERN).date().isoformat()


@router.get("/{league}/dates")
async def slate_dates(league: str):
    """Every date with a logged slate, oldest first."""
    return _dates(_league(league))


@router.get("/{league}/slate")
async def slate(league: str, day: str | None = Query(None, alias="date", description="YYYY-MM-DD (Eastern); default today")):
    """One day's games: the line captured at pick time, the verdict and rules fired, the NBA
    paper test, and, once graded, the final score and closing line."""
    league = _league(league)
    d = day or _today()
    if not DATE_RE.match(d):
        raise HTTPException(422, "date must be YYYY-MM-DD")
    try:
        date.fromisoformat(d)
    except ValueError:
        raise HTTPException(422, "date must be a real date")
    dates = _dates(league)
    games = sorted((_game(g) for g in _load(league, d)), key=lambda g: (g["start_time"] or "", g["matchup"] or ""))
    return {
        "league": league,
        "date": d,
        "today": _today(),
        "logged": d in dates,
        "captured_at": min((g["captured_at"] for g in games if g["captured_at"]), default=None),
        "previous_date": next((x for x in reversed(dates) if x < d), None),
        "next_date": next((x for x in dates if x > d), None),
        "games": games,
    }


@router.get("/{league}/record")
async def season_record(league: str, season: int | None = Query(None, description="season = end year; default latest logged")):
    """Season-to-date: games logged and graded, bets, the paper test's record, ROI and CLV,
    plus one row per day for the chart."""
    league = _league(league)
    by_day = {d: [_game(g) for g in _load(league, d)] for d in _dates(league)}
    seasons = sorted({g["season"] for gs in by_day.values() for g in gs if g["season"] is not None})
    if season is None:
        season = seasons[-1] if seasons else None
    days = []
    games: list[dict] = []
    for d, gs in by_day.items():
        gs = [g for g in gs if g["season"] == season]
        if not gs:
            continue
        games += gs
        r = _record(gs)
        days.append({"date": d, "games": r["games_logged"], "graded": r["games_graded"],
                     "paper_entries": r["paper_entries"], "paper_wins": r["paper_wins"],
                     "paper_losses": r["paper_losses"], "paper_pushes": r["paper_pushes"],
                     "paper_pnl": r["paper_pnl"]})
    return {"league": league, "season": season, "seasons": seasons,
            "first_date": days[0]["date"] if days else None, "last_date": days[-1]["date"] if days else None,
            **_record(games), "days": days}
