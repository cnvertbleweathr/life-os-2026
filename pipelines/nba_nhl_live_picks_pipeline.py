#!/usr/bin/env python3
"""
nba_nhl_live_picks_pipeline.py

DLT pipeline that loads data/bets/{nba,nhl}/history/*.json (written by
scripts/nba_nhl_generate_picks.py, graded in place by scripts/nba_nhl_grade_picks.py)
into DuckDB. Same pattern as pipelines/live_picks_pipeline.py (CFB): local files
are the source, one merge resource, so re-running after grading updates rows.

Tables produced
  nba.live_picks, nhl.live_picks -- one row per game logged by the generator:
    the line and price captured at pick time, the verdict (NO_BET until a rule is
    validated), the NBA paper-test fields, and the final score, closing line,
    outcome, P&L and CLV once graded (NULL until then).

Usage
  python pipelines/nba_nhl_live_picks_pipeline.py              # both leagues
  python pipelines/nba_nhl_live_picks_pipeline.py --league nba
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterator

import dlt

ROOT = Path(__file__).resolve().parents[1]
BETS = ROOT / "data" / "bets"
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")

T, D, B, I = "text", "double", "bool", "bigint"
# Explicit types: grading and paper columns are NULL on every row until graded,
# and DLT drops all-null columns otherwise (see live_picks_pipeline.py).
COLUMNS = {c: {"data_type": t, "nullable": True} for c, t in {
    "start_time": T, "book": T, "line_snapshot": T, "home_spread": D, "home_spread_price": D,
    "away_spread_price": D, "ml_book": T, "home_ml": D, "away_ml": D, "total_book": T, "total": D,
    "over_price": D, "under_price": D, "espn_open_total": D, "bet": T, "rules_fired": T,
    "paper_test": T, "paper_fires": B, "paper_side": T, "paper_pred_total": D, "paper_captured_total": D,
    "paper_gap": D, "paper_price": D, "paper_prices_in_band": B, "paper_outcome": T, "paper_pnl": D,
    "paper_clv": D, "final_status": T, "home_score": I, "away_score": I, "went_ot": B, "shootout": B,
    "closing_book": T, "closing_snapshot": T, "closing_home_spread": D, "closing_total": D,
    "closing_home_ml": D, "closing_away_ml": D, "graded_at": T,
}.items()}


def rows(league: str, bets: Path = BETS) -> Iterator[dict]:
    for path in sorted((bets / league / "history").glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        for g in data.get("games", []):
            pe = g.get("paper") or {}
            r = {k: v for k, v in g.items() if k not in ("paper", "rules_fired")}
            r["rules_fired"] = json.dumps(g.get("rules_fired") or [])
            r.update({
                "paper_test": pe.get("test"), "paper_fires": pe.get("fires"), "paper_side": pe.get("side"),
                "paper_pred_total": pe.get("pred_total"), "paper_captured_total": pe.get("captured_total"),
                "paper_gap": pe.get("gap"), "paper_price": pe.get("price"),
                "paper_prices_in_band": pe.get("prices_in_band"), "paper_outcome": pe.get("outcome"),
                "paper_pnl": pe.get("pnl"), "paper_clv": pe.get("clv"),
                "source_file": path.name,
            })
            yield r


def run(leagues: list[str], db: str = DB_PATH, bets: Path = BETS, pipelines_dir: str | None = None) -> None:
    for league in leagues:
        pipeline = dlt.pipeline(pipeline_name=f"{league}_live_picks", pipelines_dir=pipelines_dir,
                                destination=dlt.destinations.duckdb(db), dataset_name=league)
        res = dlt.resource(rows(league, bets), name="live_picks", write_disposition="merge",
                           primary_key="game_id", columns=COLUMNS)
        print(pipeline.run(res))


def main() -> None:
    p = argparse.ArgumentParser(description="Load NBA / NHL pick history into DuckDB via DLT.")
    p.add_argument("--league", choices=["nba", "nhl"])
    p.add_argument("--db", default=DB_PATH, help="DuckDB file (tests)")
    p.add_argument("--bets-dir", default=str(BETS), help="root for {league}/history (tests)")
    p.add_argument("--pipelines-dir", help="DLT state dir (tests; keeps test runs out of ~/.dlt)")
    a = p.parse_args()
    run([a.league] if a.league else ["nba", "nhl"], a.db, Path(a.bets_dir), a.pipelines_dir)


if __name__ == "__main__":
    main()
