#!/usr/bin/env python3
"""
Habits DLT pipeline.

Replaces Pixela entirely. Habits are stored locally in DuckDB via DLT.
The Streamlit UI writes to data/habits/habits_log.jsonl; this pipeline
loads that file into the warehouse.

Tables produced in DuckDB (schema: habits):
  habits.habit_log        — one row per (date, habit) entry
  habits.habit_summary    — aggregated completion counts per habit per year

Usage:
  python pipelines/habits_pipeline.py            # load today's log
  python pipelines/habits_pipeline.py --year 2026
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, date
from pathlib import Path
from typing import Iterator

import dlt

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "data" / "habits" / "habits_log.jsonl"
DB_PATH = str(ROOT / "data" / "warehouse" / "lifeos.duckdb")

HABIT_KEYS = ["meditation", "pushups_100", "nonfiction_pages_10", "fiction_pages_10"]


# ---------------------------------------------------------------------------
# DLT resource: stream rows from the JSONL log
# ---------------------------------------------------------------------------

@dlt.resource(
    name="habit_log",
    write_disposition="merge",
    primary_key=["log_date", "habit"],
)
def habit_log_resource(year: int | None = None) -> Iterator[dict]:
    """Yields one record per (date, habit) from the local JSONL log."""
    if not LOG_PATH.exists():
        return

    with LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue

            log_date = row.get("date", "")
            if year and not log_date.startswith(str(year)):
                continue

            for habit in HABIT_KEYS:
                yield {
                    "log_date": log_date,
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
    if not LOG_PATH.exists():
        return

    counts: dict[str, int] = {h: 0 for h in HABIT_KEYS}
    days_logged: set[str] = set()

    with LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue

            log_date = row.get("date", "")
            if not log_date.startswith(str(year)):
                continue

            days_logged.add(log_date)
            for habit in HABIT_KEYS:
                if row.get(habit):
                    counts[habit] += 1

    total_days = len(days_logged)
    for habit in HABIT_KEYS:
        done = counts[habit]
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
        destination=dlt.destinations.duckdb(DB_PATH),
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
