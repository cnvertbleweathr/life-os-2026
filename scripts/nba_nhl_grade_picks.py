#!/usr/bin/env python3
"""
nba_nhl_grade_picks.py

Grades data/bets/{nba,nhl}/history/<date>.json in place, the NBA / NHL
counterpart of scripts/grade_picks.py. Idempotent: graded games are skipped, and
games not final yet are re-checked on the next run.

For each game it records the final score and status (from the ESPN games the
daily sync loaded) and the CLOSING line (the spine's chosen line once the game is
final: the close snapshot, else the final pregame line). For a bet or a paper
entry it records:
  outcome   win / loss / push
  pnl       per 1-unit stake at the price captured at pick time
  clv       closing line minus captured line, in points toward the bet
            (totals: close - captured for an over, captured - close for an under);
            > 0 means the bet beat the close.
Cover and over/under use the same sign conventions as int_*__game_spine
(home_spread < 0 when home is favoured; margin + spread > 0 = home covers).
Canceled / postponed games are marked and never graded.

Usage
  uv run python scripts/nba_nhl_grade_picks.py                # every ungraded file
  uv run python scripts/nba_nhl_grade_picks.py --date 2026-11-08 --dry-run

Read-only on DuckDB; writes only the JSON files.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "warehouse" / "ons.duckdb"
BETS = ROOT / "data" / "bets"


def payout(price: float) -> float:
    return 100.0 / -price if price < 0 else price / 100.0


def finals(con, league: str, game_ids: list[str]) -> dict:
    if not game_ids:
        return {}
    rows = con.execute(f"""
        select g.game_id, g.completed, g.status, g.home_score, g.away_score, g.went_ot,
               {'g.shootout' if league == 'nhl' else 'false'} as shootout,
               o.book, o.line_snapshot, o.home_spread, o.home_spread_price, o.away_spread_price,
               o.home_ml, o.away_ml, o.total, o.over_price, o.under_price
        from main_staging.stg_{league}__games g
        left join main_staging.stg_{league}__odds o using (game_id)
        where g.game_id in (select unnest(?))""", [game_ids]).df()
    return {r.game_id: r for r in rows.itertuples()}


def settle_total(side: str, captured: float, price: float, total_points: int) -> tuple[str, float]:
    margin = total_points - captured if side == "OVER" else captured - total_points
    if margin > 0:
        return "win", round(payout(price), 4)
    if margin < 0:
        return "loss", -1.0
    return "push", 0.0


def grade_game(g: dict, f, league: str, now: str) -> bool:
    """Grade one game record in place; True if it changed."""
    if g.get("graded_at"):
        return False
    if f is None:
        return False
    if f.status in ("STATUS_CANCELED", "STATUS_POSTPONED"):
        if g.get("final_status") != f.status:
            g["final_status"] = f.status
            return True
        return False
    if not f.completed:
        return False
    g.update(
        final_status=f.status, home_score=int(f.home_score), away_score=int(f.away_score),
        went_ot=bool(f.went_ot), shootout=bool(f.shootout),
        closing_book=f.book, closing_snapshot=f.line_snapshot,
        closing_home_spread=None if f.home_spread is None or f.home_spread != f.home_spread else float(f.home_spread),
        closing_total=None if f.total is None or f.total != f.total else float(f.total),
        closing_home_ml=None if f.home_ml is None or f.home_ml != f.home_ml else float(f.home_ml),
        closing_away_ml=None if f.away_ml is None or f.away_ml != f.away_ml else float(f.away_ml),
    )
    total_points = g["home_score"] + g["away_score"]
    pe = g.get("paper") or {}
    if pe.get("fires"):
        outcome, pnl = settle_total(pe["side"], pe["captured_total"], pe["price"], total_points)
        clv = None
        if g["closing_total"] is not None:
            clv = (g["closing_total"] - pe["captured_total"]) if pe["side"] == "OVER" \
                else (pe["captured_total"] - g["closing_total"])
        pe.update(outcome=outcome, pnl=pnl, clv=clv)
    if g.get("bet"):   # no validated rules yet; kept for when one ships
        raise NotImplementedError("bet grading arrives with the first validated rule")
    g["graded_at"] = now
    return True


def grade_file(con, path: Path, dry_run: bool, now: str) -> dict:
    data = json.loads(path.read_text())
    league = data["league"]
    fs = finals(con, league, [g["game_id"] for g in data["games"] if not g.get("graded_at")])
    changed = sum(grade_game(g, fs.get(g["game_id"]), league, now) for g in data["games"])
    pending = sum(1 for g in data["games"] if not g.get("graded_at") and not g.get("final_status", "").startswith("STATUS_C")
                  and g.get("final_status") != "STATUS_POSTPONED")
    if changed and not dry_run:
        path.write_text(json.dumps(data, indent=2, default=str))
    return {"data": data, "changed": changed, "pending": pending}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    p.add_argument("--date", help="grade only this date's files (YYYY-MM-DD)")
    p.add_argument("--league", choices=["nba", "nhl"])
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--db", default=str(DB_PATH))
    p.add_argument("--bets-dir", default=str(BETS), help="root for {league}/history (tests)")
    a = p.parse_args()
    con = duckdb.connect(a.db, read_only=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for league in [a.league] if a.league else ["nba", "nhl"]:
        files = sorted((Path(a.bets_dir) / league / "history").glob(f"{a.date or '*'}.json"))
        if not files:
            print(f"{league.upper()}: no history files{' for ' + a.date if a.date else ''}")
        for path in files:
            r = grade_file(con, path, a.dry_run, now)
            papers = [g["paper"] for g in r["data"]["games"] if (g.get("paper") or {}).get("outcome")]
            rec = f"{sum(x['outcome'] == 'win' for x in papers)}-{sum(x['outcome'] == 'loss' for x in papers)}-" \
                  f"{sum(x['outcome'] == 'push' for x in papers)}"
            print(f"{league.upper()} {path.stem}: graded {r['changed']} now, {r['pending']} pending; "
                  f"paper record {rec}{' (dry run, not written)' if a.dry_run and r['changed'] else ''}")
            for g in r["data"]["games"]:
                if not g.get("graded_at"):
                    continue
                pe = g.get("paper") or {}
                extra = (f"  PAPER {pe['side']} {pe['captured_total']:g}: {pe['outcome']} {pe['pnl']:+.2f}u,"
                         f" CLV {pe['clv']:+.1f}" if pe.get("outcome") else "")
                close = (f"close {g['home_team']} {g['closing_home_spread']:+g}"
                         if g.get("closing_home_spread") is not None else "no close")
                print(f"  {g['matchup']:12} {g['away_score']:>3}-{g['home_score']:<3} {close:16}"
                      f" o/u {g.get('closing_total') or '-'}{extra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
