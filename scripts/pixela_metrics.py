#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.pixela_client import PixelaClient

HABITS = {
    "meditation": "meditation",
    "pushups100": "pushups100",
    "nonfiction10": "nonfiction10",
    "fiction10": "fiction10",
}

def yyyymmdd(dt: datetime) -> str:
    return dt.strftime("%Y%m%d")

def main() -> int:
    p = argparse.ArgumentParser(description="Pull Pixela habit pixels and write metrics.")
    p.add_argument("--year", type=int, default=datetime.now().year)
    args = p.parse_args()

    year = args.year
    date_from = f"{year}0101"
    date_to = f"{year}1231"

    px = PixelaClient.from_env()

    out_dir = ROOT / "data" / "pixela" / "metrics"
    out_dir.mkdir(parents=True, exist_ok=True)

    daily_path = out_dir / f"habits_daily_{year}.csv"
    summary_path = out_dir / f"habits_summary_{year}.csv"

    # Build a map: date -> habit -> quantity
    # We'll output one row per date with 0/1 columns.
    # Pixela returns only days with pixels, so missing = 0.
    all_dates = {}
    for habit, gid in HABITS.items():
        resp = px.get_pixels_range(gid, date_from, date_to)
        pixels = resp.get("pixels", []) if isinstance(resp, dict) else []
        for pz in pixels:
            d = pz.get("date")
            q = pz.get("quantity", "0")
            if not d:
                continue
            all_dates.setdefault(d, {})[habit] = int(q) if str(q).isdigit() else 0

    # Ensure stable columns
    habit_cols = list(HABITS.keys())

    # Write daily file (only dates that appear OR you can expand later)
    dates_sorted = sorted(all_dates.keys())
    with open(daily_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date"] + habit_cols)
        w.writeheader()
        for d in dates_sorted:
            row = {"date": d}
            for h in habit_cols:
                row[h] = all_dates.get(d, {}).get(h, 0)
            w.writerow(row)

    # Summary counts + completion rates (based on days observed)
    # We define "days_observed" as number of dates we have *any* habit entry for.
    # (Works well early-year; later we can switch to calendar days elapsed.)
    days_observed = len(dates_sorted)
    summary = {"year": year, "days_observed": days_observed}
    for h in habit_cols:
        done_days = sum(1 for d in dates_sorted if all_dates.get(d, {}).get(h, 0) > 0)
        summary[f"{h}_done_days"] = done_days
        summary[f"{h}_completion_rate_pct"] = round((done_days / days_observed) * 100, 2) if days_observed else ""

    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary.keys()))
        w.writeheader()
        w.writerow(summary)

    print(f"Wrote: {daily_path} (rows={days_observed})")
    print(f"Wrote: {summary_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
