#!/usr/bin/env python3
"""
Habits DLT pipeline.

Habits are stored locally in DuckDB via DLT. The web UI (POST /api/habits/log)
and the legacy Streamlit page append full-day snapshots to
data/habits/habits_log.jsonl; this pipeline loads that file into the warehouse.

The log is append-only, so a date can have several lines. Only the latest
line per date counts (pipelines/_jsonl.latest_by). Before this, repeated
saves on the same day were each counted in habit_summary.

Tables produced in DuckDB (schema: habits):
  habits.habit_log        — one row per (date, habit) entry
  habits.habit_summary    — aggregated completion counts per habit per year

Usage:
  python pipelines/habits_pipeline.py            # load today's log
  python pipelines/habits_pipeline.py --year 2026
"""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import Iterator

import dlt

try:
    from pipelines._jsonl import data_dir, db_path, latest_by
except ImportError:  # run as a plain script from pipelines/
    from _jsonl import data_dir, db_path, latest_by

HABIT_KEYS = ["meditation", "pushups_100", "nonfiction_pages_10", "fiction_pages_10"]


def _log_path():
    return data_dir() / "habits" / "habits_log.jsonl"


def _days(year: int | None) -> list[dict]:
    """Latest snapshot per date, optionally filtered to one year, sorted by date."""
    latest = latest_by(_log_path(), "date")
    return [
        row for d, row in sorted(latest.items())
        if not year or str(d).startswith(str(year))
    ]


# ---------------------------------------------------------------------------
# DLT resources
# ---------------------------------------------------------------------------

@dlt.resource(
    name="habit_log",
    write_disposition="merge",
    primary_key=["log_date", "habit"],
)
def habit_log_resource(year: int | None = None) -> Iterator[dict]:
    """Yields one record per (date, habit) from the latest snapshot per date."""
    for row in _days(year):
        for habit in HABIT_KEYS:
            yield {
                "log_date": row["date"],
                "habit": habit,
                "completed": int(bool(row.get(habit, False))),
                "logged_at": row.get("logged_at", ""),
            }


@dlt.resource(
    name="habit_summary",
    write_disposition="replace",
)
def habit_summary_resource(year: int) -> Iterator[dict]:
    """Aggregates completion counts across the full year."""
    days = _days(year)
    total_days = len(days)
    for habit in HABIT_KEYS:
        done = sum(1 for row in days if row.get(habit))
        yield {
            "year": year,
            "habit": habit,
            "done_days": done,
            "days_observed": total_days,
            "completion_rate_pct": round((done / total_days) * 100, 2) if total_days else 0.0,
        }


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run(year: int) -> None:
    pipeline = dlt.pipeline(
        pipeline_name="habits",
        destination=dlt.destinations.duckdb(db_path()),
        dataset_name="habits",
    )

    load_info = pipeline.run(
        [
            habit_log_resource(year=year),
            habit_summary_resource(year=year),
        ]
    )
    print(load_info)


def main() -> None:
    p = argparse.ArgumentParser(description="Load habits JSONL into DuckDB via DLT.")
    p.add_argument("--year", type=int, default=datetime.now().year)
    args = p.parse_args()
    run(args.year)


if __name__ == "__main__":
    main()
