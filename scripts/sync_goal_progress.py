#!/usr/bin/env python3
"""
sync_goal_progress.py

Auto-populates data/manual/goal_progress.csv with actuals pulled from
DuckDB (Strava, Hardcover, SugarWOD), then calls load_goal_progress.py
to push them into raw.raw_goal_progress.

Run this instead of editing goal_progress.csv by hand.

Usage:
  python scripts/sync_goal_progress.py
  python scripts/sync_goal_progress.py --year 2026
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "warehouse" / "lifeos.duckdb"
PROGRESS_PATH = ROOT / "data" / "manual" / "goal_progress.csv"


def safe_query(con: duckdb.DuckDBPyConnection, sql: str, params=None):
    try:
        return con.execute(sql, params or []).fetchone()
    except Exception:
        return None


def build_rows(year: int) -> list[dict]:
    today = date.today().isoformat()
    con = duckdb.connect(str(DB_PATH), read_only=True)
    rows = []

    def row(domain, goal_key, current_value, status="in_progress", notes=""):
        return {
            "year": year,
            "domain": domain,
            "goal_key": goal_key,
            "current_value": current_value if current_value is not None else "",
            "status": status,
            "updated_at": today,
            "notes": notes,
        }

    # ------------------------------------------------------------------
    # Fitness — running (Strava)
    # ------------------------------------------------------------------
    r = safe_query(con, "SELECT miles_total FROM strava.running_summary WHERE year = ?", [year])
    running_miles = round(float(r[0]), 2) if r else None
    rows.append(row("fitness", "running_miles", running_miles, notes="auto: strava"))

    # ------------------------------------------------------------------
    # Fitness — CrossFit classes (SugarWOD processed CSV)
    # ------------------------------------------------------------------
    wod_csv = ROOT / "data" / "sugarwod" / "processed" / "workouts_clean.csv"
    crossfit_classes = None
    if wod_csv.exists():
        import pandas as _pd
        wods = _pd.read_csv(wod_csv)
        wods['date'] = _pd.to_datetime(wods['date'], errors='coerce')
        crossfit_classes = int(wods[wods['date'].dt.year == year]['date'].nunique())
    rows.append(row("fitness", "crossfit_classes", crossfit_classes, notes="auto: sugarwod"))

    # ------------------------------------------------------------------
    # Fitness — marathon (manual boolean — don't overwrite if already true)
    # ------------------------------------------------------------------
    existing_marathon = _read_existing(PROGRESS_PATH, year, "fitness", "marathon_completed")
    marathon_val = existing_marathon if existing_marathon else 0
    rows.append(row("fitness", "marathon_completed", marathon_val, notes="manual"))

    # ------------------------------------------------------------------
    # Fitness — bodyweight (manual)
    # ------------------------------------------------------------------
    bw = _read_existing(PROGRESS_PATH, year, "fitness", "bodyweight_lbs_max")
    rows.append(row("fitness", "bodyweight_lbs_max", bw, notes="manual"))

    # ------------------------------------------------------------------
    # Fitness — squat max (manual)
    # ------------------------------------------------------------------
    sq = _read_existing(PROGRESS_PATH, year, "fitness", "squat_max_lbs")
    rows.append(row("fitness", "squat_max_lbs", sq, notes="manual"))

    # ------------------------------------------------------------------
    # Professional — reading (Hardcover nonfiction)
    # ------------------------------------------------------------------
    r = safe_query(con, "SELECT nonfiction_read FROM hardcover.reading_summary WHERE year = ?", [year])
    nonfiction = int(r[0]) if r else None
    rows.append(row("professional", "nonfiction_books_goal", nonfiction, notes="auto: hardcover"))

    # ------------------------------------------------------------------
    # Personal — fiction reading (Hardcover)
    # ------------------------------------------------------------------
    r = safe_query(con, "SELECT fiction_read FROM hardcover.reading_summary WHERE year = ?", [year])
    fiction = int(r[0]) if r else None
    rows.append(row("personal", "fiction_books_goal", fiction, notes="auto: hardcover"))

    # ------------------------------------------------------------------
    # Family — date nights (calendar metrics CSV)
    # ------------------------------------------------------------------
    dn_csv = ROOT / f"data/calendar/metrics/date_night_summary_{year}.csv"
    date_nights = None
    if dn_csv.exists():
        import csv as _csv
        with dn_csv.open() as f:
            for rec in _csv.DictReader(f):
                v = rec.get("date_nights_ytd") or rec.get("total_date_nights")
                if v:
                    try:
                        date_nights = int(float(v))
                    except ValueError:
                        pass
    rows.append(row("family", "date_night_per_week", date_nights, notes="auto: calendar"))

    # ------------------------------------------------------------------
    # Finance — manual (preserve existing values)
    # ------------------------------------------------------------------
    for goal_key in ["roth_ira", "hsa", "monthly_savings_usd"]:
        val = _read_existing(PROGRESS_PATH, year, "finance", goal_key)
        status = _read_existing_status(PROGRESS_PATH, year, "finance", goal_key) or "in_progress"
        rows.append(row("finance", goal_key, val, status=status, notes="manual"))

    # ------------------------------------------------------------------
    # Professional — other manual goals
    # ------------------------------------------------------------------
    for goal_key in ["migrations_completed", "ps_revenue_usd", "promotion", "github_commits"]:
        val = _read_existing(PROGRESS_PATH, year, "professional", goal_key)
        rows.append(row("professional", goal_key, val, notes="manual"))

    con.close()
    return rows


def _read_existing(path: Path, year: int, domain: str, goal_key: str):
    """Read current_value from existing CSV for a given row, if present."""
    if not path.exists():
        return None
    import csv as _csv
    with path.open() as f:
        for rec in _csv.DictReader(f):
            if (
                str(rec.get("year")) == str(year)
                and rec.get("domain", "").lower() == domain.lower()
                and rec.get("goal_key", "").lower() == goal_key.lower()
            ):
                v = rec.get("current_value", "").strip()
                return v if v else None
    return None


def _read_existing_status(path: Path, year: int, domain: str, goal_key: str):
    if not path.exists():
        return None
    import csv as _csv
    with path.open() as f:
        for rec in _csv.DictReader(f):
            if (
                str(rec.get("year")) == str(year)
                and rec.get("domain", "").lower() == domain.lower()
                and rec.get("goal_key", "").lower() == goal_key.lower()
            ):
                return rec.get("status", "").strip() or None
    return None


def main() -> int:
    p = argparse.ArgumentParser(description="Sync goal progress from DuckDB into goal_progress.csv.")
    p.add_argument("--year", type=int, default=datetime.now().year)
    p.add_argument("--dry-run", action="store_true", help="Print rows without writing.")
    args = p.parse_args()

    if not DB_PATH.exists():
        print("No DuckDB warehouse found. Run pipelines first.", file=sys.stderr)
        return 1

    rows = build_rows(args.year)

    if args.dry_run:
        for r in rows:
            print(r)
        return 0

    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    fields = ["year", "domain", "goal_key", "current_value", "status", "updated_at", "notes"]
    with PROGRESS_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} rows to {PROGRESS_PATH}")

    # Now push into DuckDB
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "load_goal_progress.py")],
        cwd=str(ROOT),
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())