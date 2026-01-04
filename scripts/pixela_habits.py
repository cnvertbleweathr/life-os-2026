#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Ensure repo root is on sys.path so `scripts.*` imports work
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.pixela_client import PixelaClient

HABITS = {
    "meditation": "meditation",
    "pushups100": "pushups100",
    "nonfiction10": "nonfiction10",
    "fiction10": "fiction10",
}

def yyyymmdd_from_arg(s: str | None) -> str:
    if not s:
        return datetime.now().strftime("%Y%m%d")
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        return s
    # allow YYYY-MM-DD
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%Y%m%d")
    except ValueError:
        raise SystemExit("Invalid --date. Use YYYYMMDD or YYYY-MM-DD.")

def main() -> int:
    p = argparse.ArgumentParser(description="Mark Pixela habits as done (quantity=1).")
    p.add_argument("--date", default=None, help="Date as YYYYMMDD or YYYY-MM-DD (default: today)")
    p.add_argument("--value", type=int, default=1, help="Quantity to set (default: 1). Use 0 to clear.")
    for k in HABITS.keys():
        p.add_argument(f"--{k}", action="store_true", help=f"Mark {k} as done")
    p.add_argument("--all", action="store_true", help="Mark all habits")
    args = p.parse_args()

    date = yyyymmdd_from_arg(args.date)

    selected = []
    if args.all:
        selected = list(HABITS.keys())
    else:
        selected = [k for k in HABITS.keys() if getattr(args, k)]

    if not selected:
        print("No habits selected. Use --all or one of: " + ", ".join(f"--{k}" for k in HABITS.keys()))
        return 2

    px = PixelaClient.from_env()

    for key in selected:
        gid = HABITS[key]
        res = px.upsert_pixel(gid, date, args.value)
        print(f"{date} {gid}={args.value} -> {res.get('message', res)}")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
