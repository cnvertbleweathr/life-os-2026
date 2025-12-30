"""
Compute running metrics from Strava activities JSON.

Reads:
  data/running/raw/activities_YYYYMMDD.json  (uses latest if not specified)

Writes:
  data/running/metrics/running_summary_<year>.csv
  data/running/metrics/weekly_miles_<year>.csv
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

RAW_DIR = Path("data/running/raw")
METRICS_DIR = Path("data/running/metrics")

# Treat these Strava types as "running"
RUN_TYPES = {"Run", "VirtualRun", "TrailRun"}


def latest_activities_file() -> Path:
    files = sorted(RAW_DIR.glob("activities_*.json"))
    if not files:
        raise FileNotFoundError(
            f"No activities_*.json found in {RAW_DIR}. "
            "Run scripts/fetch_strava_activities.py first."
        )
    return files[-1]


def parse_activities(path: Path) -> pd.DataFrame:
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError("Expected a JSON list of activities")

    df = pd.json_normalize(data)

    # Expected fields from Strava activities:
    # type, distance (meters), moving_time (seconds), elapsed_time (seconds), start_date (ISO string)
    for col in ["type", "distance", "moving_time", "elapsed_time", "start_date"]:
        if col not in df.columns:
            df[col] = None

    # Parse start_date (Strava typically uses UTC Zulu timestamps)
    df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce", utc=True)

    # Basic normalization
    df["distance_m"] = pd.to_numeric(df["distance"], errors="coerce")
    df["moving_time_s"] = pd.to_numeric(df["moving_time"], errors="coerce")

    # Derived
    df["distance_miles"] = df["distance_m"] / 1609.344
    df["year"] = df["start_date"].dt.year

    return df


def compute_metrics(df: pd.DataFrame, year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Filter to runs in target year
    df_year = df[(df["year"] == year) & (df["type"].isin(RUN_TYPES))].copy()
    df_year = df_year.dropna(subset=["start_date", "distance_miles"])

    # Weekly miles (ISO week)
    if df_year.empty:
        weekly = pd.DataFrame(columns=["week_start", "week_iso", "runs", "miles"])
    else:
        df_year["week_start"] = df_year["start_date"].dt.to_period("W").apply(lambda p: p.start_time)
        df_year["week_iso"] = df_year["start_date"].dt.isocalendar().week.astype(int)

        weekly = (
            df_year.groupby(["week_start", "week_iso"], as_index=False)
            .agg(
                runs=("id", "count") if "id" in df_year.columns else ("type", "count"),
                miles=("distance_miles", "sum"),
            )
            .sort_values("week_start")
        )

    total_miles = float(df_year["distance_miles"].sum()) if not df_year.empty else 0.0
    total_runs = int(len(df_year)) if not df_year.empty else 0

    # Long run = max single run distance
    long_run_miles = float(df_year["distance_miles"].max()) if not df_year.empty else 0.0

    # Avg pace (min/mile) using moving_time
    if not df_year.empty and df_year["moving_time_s"].notna().any() and total_miles > 0:
        total_moving_min = float(df_year["moving_time_s"].sum()) / 60.0
        avg_pace_min_per_mile = total_moving_min / total_miles
    else:
        avg_pace_min_per_mile = None

    # Weeks elapsed in year up to now (for pacing)
    now_utc = datetime.now(timezone.utc)
    if now_utc.year < year:
        weeks_elapsed = 0
    elif now_utc.year > year:
        weeks_elapsed = 52
    else:
        # ISO week number within the current year
        weeks_elapsed = int(now_utc.isocalendar().week)

    goal_miles = 350.0
    required_per_week = goal_miles / 52.0
    miles_per_week = (total_miles / weeks_elapsed) if weeks_elapsed > 0 else 0.0

    summary = {
        "year": year,
        "runs_count": total_runs,
        "miles_total": round(total_miles, 2),
        "miles_goal": goal_miles,
        "miles_progress_pct": round((total_miles / goal_miles) * 100, 2) if goal_miles else 0.0,
        "weeks_elapsed": weeks_elapsed,
        "miles_per_week": round(miles_per_week, 2),
        "required_miles_per_week": round(required_per_week, 2),
        "long_run_miles": round(long_run_miles, 2),
        "avg_pace_min_per_mile": round(avg_pace_min_per_mile, 2) if avg_pace_min_per_mile is not None else "",
        "source_file": str(latest_activities_file()),
        "run_types_counted": ",".join(sorted(RUN_TYPES)),
    }

    return pd.DataFrame([summary]), weekly


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="Path to activities_YYYYMMDD.json (defaults to latest)")
    parser.add_argument("--year", type=int, default=2026, help="Target year (default: 2026)")
    args = parser.parse_args()

    METRICS_DIR.mkdir(parents=True, exist_ok=True)

    input_path = Path(args.input) if args.input else latest_activities_file()
    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    df = parse_activities(input_path)
    summary_df, weekly_df = compute_metrics(df, args.year)

    summary_path = METRICS_DIR / f"running_summary_{args.year}.csv"
    weekly_path = METRICS_DIR / f"weekly_miles_{args.year}.csv"

    summary_df.to_csv(summary_path, index=False)
    weekly_df.to_csv(weekly_path, index=False)

    print(f"Wrote: {summary_path}")
    print(summary_df.to_dict(orient='records')[0])
    print(f"Wrote: {weekly_path} (rows={len(weekly_df)})")


if __name__ == "__main__":
    main()

