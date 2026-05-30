#!/usr/bin/env python3
"""
Run Operating Narcisystem DLT pipelines.

Usage:
  python run_pipelines.py                    # run all
  python run_pipelines.py --only habits      # run one
  python run_pipelines.py --only strava hardcover
  python run_pipelines.py --year 2026
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

PIPELINES = ["habits", "strava", "hardcover"]


def run_pipeline(name: str, year: int) -> bool:
    print(f"\n{'='*50}")
    print(f"Running pipeline: {name}")
    print(f"{'='*50}")
    try:
        if name == "habits":
            from pipelines.habits_pipeline import run
        elif name == "strava":
            from pipelines.strava_pipeline import run
        elif name == "hardcover":
            from pipelines.hardcover_pipeline import run
        else:
            print(f"Unknown pipeline: {name}", file=sys.stderr)
            return False

        run(year=year)
        print(f"✓ {name} complete")
        return True

    except Exception as e:
        print(f"✗ {name} failed: {e}", file=sys.stderr)
        return False


def main() -> int:
    p = argparse.ArgumentParser(description="Run Operating Narcisystem DLT pipelines.")
    p.add_argument(
        "--only",
        nargs="+",
        choices=PIPELINES,
        default=PIPELINES,
        help="Which pipelines to run (default: all)",
    )
    p.add_argument("--year", type=int, default=datetime.now().year)
    args = p.parse_args()

    results = {}
    for name in args.only:
        results[name] = run_pipeline(name, year=args.year)

    print(f"\n{'='*50}")
    print("Pipeline summary:")
    for name, ok in results.items():
        status = "✓" if ok else "✗"
        print(f"  {status} {name}")

    failed = [n for n, ok in results.items() if not ok]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
