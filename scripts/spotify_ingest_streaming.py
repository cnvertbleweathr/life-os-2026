#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import glob
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]

RAW_DIR = ROOT / "data" / "spotify" / "raw" / "streaming_history"
OUT_DIR = ROOT / "data" / "spotify" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_CSV = OUT_DIR / "streams_clean.csv"


def parse_end_time(end_time: str) -> str:
    """
    Spotify streaming history typically has endTime like: "2026-01-03 21:14"
    Store as ISO8601 without timezone: "2026-01-03T21:14:00"
    """
    s = (end_time or "").strip()
    if not s:
        return ""
    # common formats
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.isoformat(timespec="seconds")
        except ValueError:
            continue
    # fallback: best effort
    return s.replace(" ", "T")


def iter_rows_from_json(path: Path) -> Iterable[Dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return

    for item in data:
        if not isinstance(item, dict):
            continue
        end_time = parse_end_time(str(item.get("endTime", "") or ""))
        artist = str(item.get("artistName", "") or "").strip()
        track = str(item.get("trackName", "") or "").strip()
        ms = item.get("msPlayed", "")
        try:
            ms_int = int(ms)
        except Exception:
            ms_int = 0

        yield {
            "played_at": end_time,
            "artist_name": artist,
            "track_name": track,
            "ms_played": str(ms_int),
            "source_file": path.name,
        }


def read_existing_keys(csv_path: Path) -> set[Tuple[str, str, str, str]]:
    """
    De-dupe key: (played_at, artist_name, track_name, ms_played)
    """
    keys = set()
    if not csv_path.exists():
        return keys
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            keys.add((
                (row.get("played_at") or ""),
                (row.get("artist_name") or ""),
                (row.get("track_name") or ""),
                (row.get("ms_played") or ""),
            ))
    return keys


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--raw-dir", default=str(RAW_DIR))
    args = p.parse_args()

    raw_dir = Path(args.raw_dir)
    if not raw_dir.exists():
        raise SystemExit(f"Missing raw dir: {raw_dir}")

    json_files = sorted(Path(p).resolve() for p in glob.glob(str(raw_dir / "StreamingHistory_music_*.json")))
    if not json_files:
        raise SystemExit(f"No StreamingHistory_music_*.json files found in {raw_dir}")

    fieldnames = ["played_at", "artist_name", "track_name", "ms_played", "source_file"]

    existing = read_existing_keys(OUT_CSV)
    new_rows: List[Dict[str, str]] = []
    seen_new = set()

    for jf in json_files:
        for row in iter_rows_from_json(jf):
            key = (row["played_at"], row["artist_name"], row["track_name"], row["ms_played"])
            if key in existing or key in seen_new:
                continue
            seen_new.add(key)
            new_rows.append(row)

    # Write / append
    write_header = not OUT_CSV.exists()
    with open(OUT_CSV, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            w.writeheader()
        for r in new_rows:
            w.writerow(r)

    print(f"Input files: {len(json_files)}")
    print(f"New rows appended: {len(new_rows)}")
    print(f"Wrote: {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
