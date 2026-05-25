#!/usr/bin/env python3
"""
export_for_insights.py

Dumps key DuckDB mart data to data/exports/ as flat CSVs.
Designed to be readable by Claude Cowork or any downstream insight job
without requiring direct DuckDB access.

Usage:
  python scripts/export_for_insights.py
  python scripts/export_for_insights.py --year 2026
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

ROOT     = Path(__file__).resolve().parents[1]
DB_PATH  = ROOT / "data" / "warehouse" / "lifeos.duckdb"
OUT_DIR  = ROOT / "data" / "exports"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def safe_query(con: duckdb.DuckDBPyConnection, sql: str, params=None) -> pd.DataFrame:
    try:
        return con.execute(sql, params or []).df()
    except Exception as e:
        print(f"  Warning: query failed — {e}")
        return pd.DataFrame()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int, default=datetime.now().year)
    args = p.parse_args()
    year = args.year

    if not DB_PATH.exists():
        raise SystemExit(f"No DuckDB warehouse at {DB_PATH}. Run pipelines first.")

    con = duckdb.connect(str(DB_PATH), read_only=True)
    exports = {}

    # ------------------------------------------------------------------
    # Goal progress
    # ------------------------------------------------------------------
    exports["goal_progress"] = safe_query(con, """
        SELECT domain, goal_key, current_value, target_numeric,
               progress_percent, status
        FROM main_marts.mart_goal_progress
        ORDER BY domain, goal_key
    """)

    # ------------------------------------------------------------------
    # Habit summary
    # ------------------------------------------------------------------
    exports["habit_summary"] = safe_query(con, """
        SELECT habit, done_days, days_observed, completion_rate_pct
        FROM habits.habit_summary
        WHERE year = ?
    """, [year])

    # ------------------------------------------------------------------
    # Habit daily (last 60 days for correlation analysis)
    # ------------------------------------------------------------------
    exports["habit_daily"] = safe_query(con, """
        SELECT log_date, meditation, pushups_100,
               nonfiction_pages_10, fiction_pages_10,
               habits_completed_count, daily_completion_pct
        FROM main_marts.mart_habit_performance
        WHERE year = ?
        ORDER BY log_date DESC
        LIMIT 60
    """, [year])

    # ------------------------------------------------------------------
    # Running — weekly
    # ------------------------------------------------------------------
    exports["running_weekly"] = safe_query(con, """
        SELECT
            strftime(start_date::date, '%Y-W%W') as week,
            sum(distance_miles) as miles,
            count(*) as runs,
            avg(moving_time_s / 60.0 / nullif(distance_miles, 0)) as avg_pace_min_per_mile
        FROM strava.activities
        WHERE is_run = true AND year = ?
        GROUP BY week
        ORDER BY week DESC
        LIMIT 20
    """, [year])

    exports["running_summary"] = safe_query(con, """
        SELECT * FROM strava.running_summary WHERE year = ?
    """, [year])

    # ------------------------------------------------------------------
    # CrossFit — recent classes + PRs
    # ------------------------------------------------------------------
    sugarwod_clean = ROOT / "data" / "sugarwod" / "processed" / "workouts_clean.csv"
    if sugarwod_clean.exists():
        import csv as _csv
        wods = pd.read_csv(sugarwod_clean)
        wods["date"] = pd.to_datetime(wods["date"], errors="coerce")
        wods_yr = wods[wods["date"].dt.year == year].copy()

        # Classes per week
        wods_yr["week"] = wods_yr["date"].dt.strftime("%Y-W%W")
        classes_weekly = (
            wods_yr.groupby("week")["date"]
            .nunique()
            .reset_index()
            .rename(columns={"date": "classes"})
            .sort_values("week", ascending=False)
            .head(20)
        )
        exports["crossfit_weekly"] = classes_weekly

        # PRs
        prs = wods_yr[wods_yr["pr"].astype(str).str.upper() == "PR"][
            ["date", "title", "barbell_lift", "best_result_display"]
        ].sort_values("date", ascending=False)
        exports["crossfit_prs"] = prs

        # Lift progressions
        lifts = wods_yr[
            (wods_yr["score_type"] == "Load") &
            wods_yr["barbell_lift"].notna() &
            (wods_yr["barbell_lift"].str.strip() != "")
        ][["date", "barbell_lift", "best_result_raw"]].copy()
        lifts["best_result_raw"] = pd.to_numeric(lifts["best_result_raw"], errors="coerce")
        exports["crossfit_lifts"] = lifts.sort_values("date", ascending=False).head(50)

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------
    exports["reading_summary"] = safe_query(con, """
        SELECT * FROM hardcover.reading_summary WHERE year = ?
    """, [year])

    exports["books_read"] = safe_query(con, """
        SELECT title, authors, classification, marked_read_at
        FROM hardcover.books_read
        WHERE year = ?
        ORDER BY marked_read_at DESC
    """, [year])

    # ------------------------------------------------------------------
    # Spotify
    # ------------------------------------------------------------------
    spotify_summary = ROOT / "data" / "spotify" / "metrics" / f"spotify_summary_{year}.csv"
    if spotify_summary.exists():
        exports["spotify_summary"] = pd.read_csv(spotify_summary)

    # ------------------------------------------------------------------
    # Write all exports
    # ------------------------------------------------------------------
    con.close()

    manifest = {"exported_at": datetime.now().isoformat(), "year": year, "files": []}
    for name, df in exports.items():
        if df is None or df.empty:
            print(f"  skipped (empty): {name}")
            continue
        path = OUT_DIR / f"{name}.csv"
        df.to_csv(path, index=False)
        manifest["files"].append({"name": name, "rows": len(df), "path": str(path)})
        print(f"  ✓ {name}: {len(df)} rows → {path.name}")

    import json
    manifest_path = OUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\nExported {len(manifest['files'])} files to {OUT_DIR}")


if __name__ == "__main__":
    main()
