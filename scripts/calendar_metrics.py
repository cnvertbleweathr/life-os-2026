#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml

from dateutil.parser import isoparse
from datetime import timezone

GOALS_PATH = Path("goals/2026.yaml")

DATE_NIGHT_TOKEN = "DATE NIGHT"  # presence anywhere in title counts


def load_clean_csv(year: int) -> Path:
    p = Path("data/calendar/processed") / f"events_clean_{year}.csv"
    if not p.exists():
        raise FileNotFoundError(f"Missing {p}. Run: python3 scripts/calendar_export.py --year {year}")
    return p


def title_has_date_night(title: str) -> bool:
    if not isinstance(title, str):
        return False
    return DATE_NIGHT_TOKEN.lower() in title.lower()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2026)
    args = parser.parse_args()
    year = args.year

    # Load goals
    goals = yaml.safe_load(GOALS_PATH.read_text(encoding="utf-8"))
    date_night_goal = (
        goals.get("domains", {})
        .get("family", {})
        .get("outcomes", {})
        .get("date_night_per_week", 1)
    )
    try:
        date_night_goal = int(date_night_goal)
    except Exception:
        date_night_goal = 1

    # Load events
    df = pd.read_csv(load_clean_csv(year))
    df["summary"] = df.get("summary", "").fillna("")

    # Parse start datetime (works for both dateTime + date rows)
    def parse_start_utc(s: str):
        if not isinstance(s, str) or not s.strip():
            return pd.NaT
        try:
            dt = isoparse(s.strip())
            # If no tzinfo, assume UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return pd.NaT

    df["start_dt"] = df["start"].apply(parse_start_utc)

    df = df.dropna(subset=["start_dt"])

    # Identify DATE NIGHT events
    df["is_date_night"] = df["summary"].apply(title_has_date_night)

    # Weekly completion: any date night in the week => satisfied
    df["iso_week"] = df["start_dt"].dt.isocalendar().week.astype(int)

    weekly = (
        df.groupby("iso_week", as_index=False)
        .agg(
            date_night_events=("is_date_night", "sum"),
            date_night_done=("is_date_night", "any"),
        )
        .sort_values("iso_week")
    )
    weekly["goal_per_week"] = date_night_goal
    weekly["met_goal"] = weekly["date_night_done"]

    weeks_with_goal_met = int(weekly["met_goal"].sum()) if len(weekly) else 0
    weeks_total = int(weekly["iso_week"].nunique()) if len(weekly) else 0

    out_dir = Path("data/calendar/metrics")
    out_dir.mkdir(parents=True, exist_ok=True)

    weekly_out = out_dir / f"date_night_weekly_{year}.csv"
    summary_out = out_dir / f"date_night_summary_{year}.csv"

    weekly.to_csv(weekly_out, index=False)

    summary = pd.DataFrame([{
        "year": year,
        "date_night_goal_per_week": date_night_goal,
        "weeks_with_date_night": weeks_with_goal_met,
        "weeks_observed": weeks_total,
        "completion_rate_pct": round((weeks_with_goal_met / weeks_total) * 100, 2) if weeks_total else "",
    }])
    summary.to_csv(summary_out, index=False)

    print(f"Wrote: {weekly_out} (rows={len(weekly)})")
    print(f"Wrote: {summary_out}")
    print(summary.to_dict(orient="records")[0])


if __name__ == "__main__":
    main()

