#!/usr/bin/env python3
"""
Check-in DLT pipeline.

Loads data/checkin/checkin_log.jsonl (written by POST /api/checkin/log) into
DuckDB. The latest check-in per date wins.

Table produced (schema: checkin):
  checkin.daily_checkin — one row per date: energy, mood, focus, sleep,
                          soreness, stress (1–5), readiness (0–1), note

This is a building block for the Daily Feature Mart (ROADMAP P1).

Usage:
  python pipelines/checkin_pipeline.py
"""

from __future__ import annotations

import argparse
from typing import Iterator

import dlt

try:
    from pipelines._jsonl import data_dir, db_path, latest_by
except ImportError:
    from _jsonl import data_dir, db_path, latest_by

FIELDS = ["energy", "mood", "focus", "sleep", "soreness", "stress"]


@dlt.resource(
    name="daily_checkin",
    write_disposition="merge",
    primary_key="checkin_date",
    columns={f: {"data_type": "bigint"} for f in FIELDS}
    | {"readiness": {"data_type": "double"}, "note": {"data_type": "text"}},
)
def daily_checkin_resource(year: int | None = None) -> Iterator[dict]:
    latest = latest_by(data_dir() / "checkin" / "checkin_log.jsonl", "date")
    for d, row in sorted(latest.items()):
        if year and not str(d).startswith(str(year)):
            continue
        yield {
            "checkin_date": d,
            **{f: row.get(f) for f in FIELDS},
            "readiness": row.get("readiness"),
            "note": row.get("note") or "",
            "logged_at": row.get("logged_at", ""),
        }


def run(year: int | None = None) -> None:
    # Loads every year by default: the log is small and merge is idempotent.
    pipeline = dlt.pipeline(
        pipeline_name="checkin",
        destination=dlt.destinations.duckdb(db_path()),
        dataset_name="checkin",
    )
    print(pipeline.run(daily_checkin_resource(year=None)))


if __name__ == "__main__":
    argparse.ArgumentParser(description="Load check-in JSONL into DuckDB.").parse_args()
    run()
