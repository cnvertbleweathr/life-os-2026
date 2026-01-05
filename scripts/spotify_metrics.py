#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
IN_CSV = ROOT / "data" / "spotify" / "processed" / "streams_clean.csv"
OUT_DIR = ROOT / "data" / "spotify" / "metrics"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def parse_played_at(s: str) -> Optional[datetime]:
    if not s:
        return None
    s = s.strip()
    # our ingest outputs ISO like 2026-01-03T21:14:00
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    # fallback
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int, required=True)
    args = p.parse_args()

    if not IN_CSV.exists():
        raise SystemExit(f"Missing {IN_CSV}. Run scripts/spotify_ingest_streaming.py first.")

    now = datetime.now()
    today = now.date()

    ms_ytd = 0
    ms_today = 0
    artists_ytd = set()
    days_listened_ytd = set()

    artist_ms_ytd = defaultdict(int)
    artist_ms_today = defaultdict(int)

    rows_seen = 0
    rows_year = 0

    with open(IN_CSV, "r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            rows_seen += 1
            dt = parse_played_at(row.get("played_at", "") or "")
            if not dt:
                continue
            if dt.year != args.year:
                continue

            rows_year += 1
            artist = (row.get("artist_name") or "").strip()
            try:
                ms = int(row.get("ms_played") or 0)
            except Exception:
                ms = 0

            ms_ytd += ms
            if artist:
                artists_ytd.add(artist)
                artist_ms_ytd[artist] += ms

            days_listened_ytd.add(dt.date().isoformat())

            if dt.date() == today:
                ms_today += ms
                if artist:
                    artist_ms_today[artist] += ms

    def top_artist(d: Dict[str, int]) -> str:
        if not d:
            return ""
        return sorted(d.items(), key=lambda x: x[1], reverse=True)[0][0]

    summary = {
        "year": str(args.year),
        "rows_total_seen": str(rows_seen),
        "rows_in_year": str(rows_year),
        "spotify_minutes_ytd": f"{ms_ytd/60000:.2f}",
        "spotify_minutes_today": f"{ms_today/60000:.2f}",
        "unique_artists_ytd": str(len(artists_ytd)),
        "days_listened_ytd": str(len(days_listened_ytd)),
        "top_artist_ytd": top_artist(artist_ms_ytd),
        "top_artist_today": top_artist(artist_ms_today),
        "computed_at_local": now.isoformat(timespec="seconds"),
    }

    out_path = OUT_DIR / f"spotify_summary_{args.year}.csv"
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary.keys()))
        w.writeheader()
        w.writerow(summary)

    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
