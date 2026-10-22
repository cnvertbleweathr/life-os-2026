#!/usr/bin/env python3
"""
Capture Inbox DLT pipeline (ROADMAP P0: raw.capture_inbox).

Loads data/inbox/capture_inbox.jsonl (written by POST /api/inbox) into DuckDB.
Rows are keyed by capture_id; if a later line repeats an id (future triage
edits), the latest one wins.

Table produced (schema: raw):
  raw.capture_inbox — capture_id, captured_at, capture_date, text, kind,
                      domain, source, status

Usage:
  python pipelines/inbox_pipeline.py
"""

from __future__ import annotations

import argparse
from typing import Iterator

import dlt

try:
    from pipelines._jsonl import data_dir, db_path, latest_by
except ImportError:
    from _jsonl import data_dir, db_path, latest_by

COLUMNS = ["capture_id", "captured_at", "capture_date", "text", "kind", "domain", "source", "status"]


@dlt.resource(
    name="capture_inbox",
    write_disposition="merge",
    primary_key="capture_id",
    columns={c: {"data_type": "text"} for c in COLUMNS},
)
def capture_inbox_resource() -> Iterator[dict]:
    latest = latest_by(data_dir() / "inbox" / "capture_inbox.jsonl", "capture_id")
    for row in latest.values():
        yield {c: row.get(c) for c in COLUMNS}


def run(year: int | None = None) -> None:
    pipeline = dlt.pipeline(
        pipeline_name="capture_inbox",
        destination=dlt.destinations.duckdb(db_path()),
        dataset_name="raw",
    )
    print(pipeline.run(capture_inbox_resource()))


if __name__ == "__main__":
    argparse.ArgumentParser(description="Load capture inbox JSONL into DuckDB.").parse_args()
    run()
