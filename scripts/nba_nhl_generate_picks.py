#!/usr/bin/env python3
"""
nba_nhl_generate_picks.py

Daily NBA / NHL picks, following the CFB flow (scripts/generate_picks.py):
picks JSON -> graded in place (scripts/nba_nhl_grade_picks.py) -> DLT
(pipelines/nba_nhl_live_picks_pipeline.py) -> DuckDB -> mart_{nba,nhl}_live_picks.

For every game on the date it records the line and price AT PICK TIME (the ESPN
pregame line the daily sync just loaded: the item-level "current" line for a game
not yet played), scores the game with the rules, and writes
data/bets/{league}/history/<date>.json.

Rules: none. Phase 4 validated no NBA or NHL rule (docs/NBA_NHL_ATS_DATA.md), so
every game is recorded as NO_BET with rules_fired = []. The one thing logged
beyond that is the NBA PAPER forward test registered in Phase 4:

  nba_totals_open_v1  regular season only; predicted total (bias code as of commit
                      d56fbcd) differs from the captured total by >= 12 points;
                      both captured prices within -135..+115. Logged as a paper
                      entry with the captured line, price, book and timestamp,
                      before tip-off. Never a bet.

Append-only: a game already in the day's file keeps its first capture; re-running
only adds games that were not there. Games that have started or finished when the
script runs are recorded with captured_after_start = true and are not eligible for
the paper test (their line is not a pregame capture).

Usage
  uv run python scripts/nba_nhl_generate_picks.py                 # today, both leagues
  uv run python scripts/nba_nhl_generate_picks.py --date 2026-11-08 --dry-run
  uv run python scripts/nba_nhl_generate_picks.py --league nba

Read-only on DuckDB; run after espn_odds_pipeline --daily and nba_stats_pipeline.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from nba_nhl_lookup_common import blend, parse_date, season_of
from nba_pregame_lookup import team_form, total_bias

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "warehouse" / "ons.duckdb"
BETS = ROOT / "data" / "bets"

RULES_VERSION = "none: Phase 4 validated no rule (docs/NBA_NHL_ATS_DATA.md -> Edge validation)"
PAPER_TEST = {"name": "nba_totals_open_v1", "threshold": 12.0, "price_band": [-135, 115],
              "model_commit": "d56fbcd", "season_type": 2}


def history_path(league: str, d: date, bets: Path = BETS) -> Path:
    return bets / league / "history" / f"{d.isoformat()}.json"


def todays_games(con, league: str, d: date) -> pd.DataFrame:
    return con.execute(f"""
        select g.game_id, g.season, g.season_type, g.game_date, g.start_time, g.home_team, g.away_team,
               g.completed, g.status, g.neutral_site,
               o.book, o.line_snapshot, o.home_spread, o.home_spread_price, o.away_spread_price,
               o.ml_book, o.home_ml, o.away_ml, o.total_book, o.total, o.over_price, o.under_price,
               o.open_total, o.open_over_price, o.open_under_price
        from main_staging.stg_{league}__games g
        left join main_staging.stg_{league}__odds o using (game_id)
        where g.game_date = ? and g.season_type in (2, 3)
        order by g.start_time, g.game_id""", [d]).df()


def num(v):
    return None if v is None or pd.isna(v) else float(v)


def paper_entry(con, g: pd.Series, d: date, started: bool) -> dict | None:
    """The registered NBA totals paper test; None when it doesn't apply."""
    if started or int(g.season_type) != PAPER_TEST["season_type"] or pd.isna(g.total):
        return None
    season = int(g.season)
    fh, fa = team_form(con, g.home_team, season, d), team_form(con, g.away_team, season, d)

    def b(f, m):
        return blend(f["std"][m], f["std"]["games"], f["prior"][m])
    vals = [b(fh, "pace"), b(fa, "pace"), b(fh, "ortg"), b(fa, "drtg"), b(fa, "ortg"), b(fh, "drtg")]
    if any(v is None for v in vals):
        return None
    hpace, apace, h_o, a_d, a_o, h_d = vals
    pred_raw = (hpace + apace) / 2 / 100 * ((h_o + a_d) / 2 + (a_o + h_d) / 2)
    bias = total_bias(con, season, 2) or 0.0
    pred = pred_raw - bias
    gap = pred - float(g.total)
    lo, hi = PAPER_TEST["price_band"]
    side = "OVER" if gap > 0 else "UNDER"
    price = num(g.over_price if side == "OVER" else g.under_price)
    other = num(g.under_price if side == "OVER" else g.over_price)
    in_band = price is not None and other is not None and lo <= price <= hi and lo <= other <= hi
    fires = abs(gap) >= PAPER_TEST["threshold"] and in_band
    return {"test": PAPER_TEST["name"], "fires": bool(fires), "side": side if fires else None,
            "pred_total": round(pred, 2), "captured_total": float(g.total), "gap": round(gap, 2),
            "price": price if fires else None, "prices_in_band": bool(in_band)}


def build(con, league: str, d: date, now: datetime) -> list[dict]:
    rows = []
    for _, g in todays_games(con, league, d).iterrows():
        start = pd.Timestamp(g.start_time).tz_convert("UTC") if pd.notna(g.start_time) else None
        started = bool(g.completed) or (start is not None and start <= pd.Timestamp(now))
        rec = {
            "game_id": g.game_id, "league": league, "season": int(g.season), "season_type": int(g.season_type),
            "game_date": d.isoformat(), "start_time": start.isoformat() if start is not None else None,
            "matchup": f"{g.away_team} @ {g.home_team}", "home_team": g.home_team, "away_team": g.away_team,
            "neutral_site": bool(g.neutral_site),
            "captured_at": now.isoformat(timespec="seconds"), "captured_after_start": started,
            "book": g.book, "line_snapshot": g.line_snapshot,
            "home_spread": num(g.home_spread), "home_spread_price": num(g.home_spread_price),
            "away_spread_price": num(g.away_spread_price),
            "ml_book": g.ml_book, "home_ml": num(g.home_ml), "away_ml": num(g.away_ml),
            "total_book": g.total_book, "total": num(g.total),
            "over_price": num(g.over_price), "under_price": num(g.under_price),
            "espn_open_total": num(g.open_total),
            "verdict": "NO_BET", "bet": None, "rules_fired": [], "rules_version": RULES_VERSION,
            "paper": paper_entry(con, g, d, started) if league == "nba" else None,
        }
        rows.append(rec)
    return rows


def merge_append_only(path: Path, new: list[dict]) -> tuple[dict, int]:
    """Keep every game already captured; add only games not yet in the file."""
    if path.exists():
        data = json.loads(path.read_text())
    else:
        data = {"league": new[0]["league"] if new else None, "games": []}
    have = {g["game_id"] for g in data["games"]}
    added = [g for g in new if g["game_id"] not in have]
    data["games"].extend(added)
    return data, len(added)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    p.add_argument("--date", help="YYYY-MM-DD (US/Eastern game date); default today")
    p.add_argument("--league", choices=["nba", "nhl"])
    p.add_argument("--dry-run", action="store_true", help="print, write nothing")
    p.add_argument("--db", default=str(DB_PATH))
    p.add_argument("--bets-dir", default=str(BETS), help="root for {league}/history (tests)")
    a = p.parse_args()
    d = parse_date(a.date)
    now = datetime.now(timezone.utc)
    con = duckdb.connect(a.db, read_only=True)
    for league in [a.league] if a.league else ["nba", "nhl"]:
        games = build(con, league, d, now)
        path = history_path(league, d, Path(a.bets_dir))
        data, added = merge_append_only(path, games)
        data.update(league=league, date=d.isoformat(), season=season_of(d), rules_version=RULES_VERSION,
                    paper_test=PAPER_TEST if league == "nba" else None,
                    last_run_at=now.isoformat(timespec="seconds"))
        data.setdefault("first_run_at", now.isoformat(timespec="seconds"))
        papers = [g for g in data["games"] if (g.get("paper") or {}).get("fires")]
        print(f"\n{league.upper()} {d}: {len(data['games'])} games ({added} new this run), bets 0 "
              f"(no validated rule), paper entries {len(papers)}")
        for g in data["games"]:
            pe = g.get("paper") or {}
            paper = (f"  PAPER {pe['side']} {pe['captured_total']:g} @ {pe['price']:+g} (pred {pe['pred_total']:.1f})"
                     if pe.get("fires") else (f"  paper: gap {pe['gap']:+.1f}" if pe else ""))
            line = (f"{g['home_team']} {g['home_spread']:+g}" if g["home_spread"] is not None else "no line")
            tot = f"o/u {g['total']:g}" if g["total"] is not None else ""
            late = "  [captured after start: not a pregame line]" if g["captured_after_start"] else ""
            print(f"  {g['matchup']:12} {line:12} {tot:10} {g['book'] or '':12} {g['verdict']}{paper}{late}")
        if a.dry_run:
            print(f"  (dry run: {path} not written)")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, default=str))
        print(f"  wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
