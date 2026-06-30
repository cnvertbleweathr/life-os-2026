#!/usr/bin/env python3
"""
live_picks_pipeline.py

DLT pipeline that loads data/bets/history/*.json (written by
generate_picks.py, updated in place by grade_picks.py) into DuckDB.

Follows the same pattern as pipelines/habits_pipeline.py: a local file is
the source, not an external API; one DLT resource with write_disposition
="merge" so re-running after grading updates rows in place instead of
duplicating them.

Why this exists as its own pipeline rather than grade_picks.py writing to
DuckDB directly: every other JSON-shaped input in this system goes
External source -> DLT -> DuckDB -> dbt -> app (see ARCHITECTURE.md). A
script opening its own DuckDB connection and writing rows would be a
second, inconsistent ingestion path. This keeps picks data flowing through
the same pipe as everything else, so dbt can build a live_picks mart on
top of it exactly the way mart_cfbd_line_accuracy is built on cfbd.lines.

Tables produced in DuckDB (schema: cfbd, alongside the existing
cfbd.games/cfbd.lines tables -- this is the same data category, just a
different source):
  cfbd.live_picks   — one row per (season, week, matchup): the model's
                       pick, its score/edges, and its graded outcome once
                       available (outcome/pnl are null until grade_picks.py
                       resolves them).

Usage:
  python pipelines/live_picks_pipeline.py             # load all history files
  python pipelines/live_picks_pipeline.py --season 2026 --week 1
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterator

import dlt

ROOT        = Path(__file__).resolve().parents[1]
HISTORY_DIR = ROOT / "data" / "bets" / "history"
DB_PATH     = str(ROOT / "data" / "warehouse" / "ons.duckdb")


@dlt.resource(
    name="live_picks",
    write_disposition="merge",
    primary_key=["season", "week", "matchup"],
    columns={
        # Grading fields are NULL until grade_picks.py resolves each game.
        # Without explicit type hints, DLT skips materializing columns that
        # receive no data during a load (confirmed 2026-06-29: all-pending
        # Week 1 run dropped these columns entirely, breaking mart_live_picks).
        "outcome":    {"data_type": "text",   "nullable": True},
        "pnl":        {"data_type": "double",  "nullable": True},
        "home_score": {"data_type": "bigint",  "nullable": True},
        "away_score": {"data_type": "bigint",  "nullable": True},
    },
)
def live_picks_resource(
    season: int | None = None, week: int | None = None
) -> Iterator[dict]:
    """
    Yields one row per scored game from every data/bets/history/*.json file
    (or just the one matching season+week, if given). Each row carries the
    pick itself plus whatever grading has resolved so far -- outcome/pnl
    are present once grade_picks.py has settled the game, otherwise absent
    (DLT/DuckDB will store these as NULL, which is the correct "not graded
    yet" state, distinct from a loss).

    Intentionally excludes the "skipped" list (games with no posted line,
    excluded conference, etc.) -- there's no pick or score to track for
    those; they're recorded in the source JSON for completeness but have
    nothing meaningful to contribute to a picks-performance table.
    """
    if not HISTORY_DIR.exists():
        return

    for path in sorted(HISTORY_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue

        file_season = data.get("season")
        file_week   = data.get("week")
        if season is not None and file_season != season:
            continue
        if week is not None and file_week != week:
            continue

        for g in data.get("games", []):
            yield {
                "season":            file_season,
                "week":              file_week,
                "matchup":           g.get("matchup"),
                "bet":               g.get("bet"),
                "bet_type":          g.get("bet_type"),
                "line":              g.get("line"),
                "edge":              g.get("edge"),
                "model_score":       g.get("model_score"),
                "n_edges":           g.get("n_edges"),
                "meets_publish_bar": g.get("meets_publish_bar"),
                "ppa_gap":           g.get("ppa_gap"),
                "sp_gap":            g.get("sp_gap"),
                "ou":                g.get("ou"),
                "warnings":          g.get("warnings"),
                "generated_at":      g.get("generated_at"),
                # Grading fields -- present once grade_picks.py resolves
                # this game, absent (-> NULL) otherwise.
                "outcome":           g.get("outcome"),
                "pnl":               g.get("pnl"),
                "home_score":        g.get("home_score"),
                "away_score":        g.get("away_score"),
            }


def run(season: int | None = None, week: int | None = None) -> None:
    pipeline = dlt.pipeline(
        pipeline_name="live_picks",
        destination=dlt.destinations.duckdb(DB_PATH),
        dataset_name="cfbd",
    )
    load_info = pipeline.run(live_picks_resource(season=season, week=week))
    print(load_info)


def main() -> None:
    p = argparse.ArgumentParser(description="Load archived CFB picks into DuckDB via DLT.")
    p.add_argument("--season", type=int, default=None)
    p.add_argument("--week",   type=int, default=None)
    args = p.parse_args()
    run(season=args.season, week=args.week)


if __name__ == "__main__":
    main()
