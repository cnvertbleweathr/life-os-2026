#!/usr/bin/env python3
"""
Load the cleaned SugarWOD CSV into DuckDB as a real table: sugarwod.workouts

Why this exists:
  Every other domain (Strava, habits, hardcover, KGLW) lands in DuckDB via a
  DLT pipeline into a named schema, so dbt marts can just reference
  `strava.activities`, `habits.habit_log`, etc. SugarWOD only ever gets as
  far as data/sugarwod/processed/workouts_clean.csv — there's no DuckDB
  table for it, which means dbt can't build anything on top of it.

  This script closes that gap with a plain DuckDB write (CREATE OR REPLACE
  TABLE ... AS SELECT * FROM read_csv_auto(...)). It's a stopgap until
  SugarWOD gets a proper DLT resource; safe to re-run any time a new export
  is imported via scripts/import_sugarwod_csv.py.

Reads:
  data/sugarwod/processed/workouts_clean.csv

Writes:
  sugarwod.workouts table in data/warehouse/ons.duckdb

IMPORTANT — DuckDB single-writer rule:
  Stop FastAPI before running this (it holds a long-lived connection to
  ons.duckdb). Restart FastAPI after, same as before any dbt run or DLT sync.

Usage:
  python scripts/load_sugarwod_to_duckdb.py
  python scripts/load_sugarwod_to_duckdb.py --dry-run   # preview row count / schema only
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "sugarwod" / "processed" / "workouts_clean.csv"
DB_PATH = ROOT / "data" / "warehouse" / "ons.duckdb"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the row count and inferred schema without writing to DuckDB.",
    )
    args = parser.parse_args()

    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"Missing {CSV_PATH}. Run scripts/import_sugarwod_csv.py first."
        )

    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Missing {DB_PATH}. Expected the ONS warehouse to already exist."
        )

    con = duckdb.connect(str(DB_PATH))

    if args.dry_run:
        preview = con.execute(
            f"SELECT * FROM read_csv_auto('{CSV_PATH.as_posix()}') LIMIT 5"
        ).df()
        count = con.execute(
            f"SELECT count(*) FROM read_csv_auto('{CSV_PATH.as_posix()}')"
        ).fetchone()[0]
        print(f"[dry-run] {CSV_PATH} -> would load {count} rows into sugarwod.workouts")
        print(preview)
        con.close()
        return

    con.execute("CREATE SCHEMA IF NOT EXISTS sugarwod")
    con.execute(
        f"""
        CREATE OR REPLACE TABLE sugarwod.workouts AS
        SELECT *
        FROM read_csv_auto('{CSV_PATH.as_posix()}')
        """
    )
    row_count = con.execute("SELECT count(*) FROM sugarwod.workouts").fetchone()[0]
    con.close()

    print(f"Loaded {row_count} rows into sugarwod.workouts from {CSV_PATH}")


if __name__ == "__main__":
    main()
