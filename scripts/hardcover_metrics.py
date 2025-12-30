#!/usr/bin/env python3
import argparse
import csv
from datetime import datetime
from pathlib import Path

import yaml

GOALS_PATH = Path("goals/2026.yaml")
CLEAN_PATH = Path("data/hardcover/processed/books_read_clean.csv")
OUT_PATH = Path("data/hardcover/metrics/reading_summary_2026.csv")

def parse_year(dt_str: str):
    if not dt_str:
        return None
    # Hardcover timestamps are typically ISO-like; we only need year
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).year
    except Exception:
        return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2026)
    args = parser.parse_args()
    year = args.year

    if not GOALS_PATH.exists():
        raise SystemExit(f"Missing {GOALS_PATH}")
    if not CLEAN_PATH.exists():
        raise SystemExit(f"Missing {CLEAN_PATH}. Run scripts/hardcover_fetch.py first.")

    goals = yaml.safe_load(GOALS_PATH.read_text(encoding="utf-8"))
    domains = goals.get("domains", {})

    prof_nf_goal = (
        domains.get("professional", {})
        .get("outcomes", {})
        .get("nonfiction_books_goal", 0)
    )

    personal_f_goal = (
        domains.get("personal", {})
        .get("outcomes", {})
        .get("fiction_books_goal", 0)
    )

    fiction = 0
    nonfiction = 0
    unknown = 0
    total = 0

    with CLEAN_PATH.open("r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            y = parse_year(row.get("marked_read_at", ""))
            if y != year:
                continue
            total += 1
            c = (row.get("classification") or "").strip().lower()
            if c == "fiction":
                fiction += 1
            elif c == "nonfiction":
                nonfiction += 1
            else:
                unknown += 1

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "year",
            "fiction_read",
            "fiction_goal",
            "fiction_progress_pct",
            "nonfiction_read",
            "nonfiction_goal",
            "nonfiction_progress_pct",
            "unknown_classification",
            "total_read",
        ])
        w.writerow([
            year,
            fiction,
            personal_f_goal,
            round((fiction / personal_f_goal) * 100, 2) if personal_f_goal else "",
            nonfiction,
            prof_nf_goal,
            round((nonfiction / prof_nf_goal) * 100, 2) if prof_nf_goal else "",
            unknown,
            total,
        ])

    print(f"Wrote: {OUT_PATH}")
    print({
        "fiction_read": fiction,
        "fiction_goal": personal_f_goal,
        "nonfiction_read": nonfiction,
        "nonfiction_goal": prof_nf_goal,
        "unknown": unknown,
        "total_read": total
    })

if __name__ == "__main__":
    main()

