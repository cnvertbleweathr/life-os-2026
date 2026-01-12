#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import glob
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple, Optional

ROOT = Path(__file__).resolve().parents[1]

RAW_DIR = ROOT / "data" / "spotify" / "raw" / "streaming_history"
OUT_DIR = ROOT / "data" / "spotify" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_CSV = OUT_DIR / "streams_clean.csv"


def _safe_int(x, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def normalize_timestamp_to_iso(ts: str) -> str:
    """
    Normalizes timestamps across Spotify export formats to ISO8601.

    Supports:
    - "2026-01-03 21:14" (legacy)
    - "2026-01-03T21:14:00Z" (extended)
    - "2026-01-03T21:14:00+00:00" (extended)
    - "2026-01-03T21:14:00-07:00" (other)
    Returns ISO string, preserving timezone offset when present.
    """
    s = (ts or "").strip()
    if not s:
        return ""

    # Legacy format
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            # Keep it naive (local unknown) but ISO formatted
            return dt.isoformat(timespec="seconds")
        except ValueError:
            pass

    # Handle trailing Z (UTC)
    if s.endswith("Z"):
        # Convert "Z" to "+00:00" so fromisoformat can parse it
        s2 = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s2)
            return dt.isoformat(timespec="seconds")
        except Exception:
            return s2

    # Try ISO parse directly
    try:
        dt = datetime.fromisoformat(s)
        return dt.isoformat(timespec="seconds")
    except Exception:
        pass

    # Last resort: replace space with T
    return s.replace(" ", "T")


def iter_rows_from_json(path: Path) -> Iterable[Dict[str, str]]:
    """
    Supports BOTH schemas:

    Legacy streaming history:
      { endTime, artistName, trackName, msPlayed }

    Extended streaming history:
      {
        ts,
        ms_played,
        master_metadata_track_name,
        master_metadata_album_artist_name,
        ... (many other fields)
      }
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return

    if not isinstance(data, list):
        return

    for item in data:
        if not isinstance(item, dict):
            continue

        # --- Detect schema & extract fields ---
        if "endTime" in item or "artistName" in item or "trackName" in item:
            # Legacy schema
            played_at = normalize_timestamp_to_iso(str(item.get("endTime", "") or ""))
            artist = str(item.get("artistName", "") or "").strip()
            track = str(item.get("trackName", "") or "").strip()
            ms_int = _safe_int(item.get("msPlayed", 0), 0)
        else:
            # Extended schema
            played_at = normalize_timestamp_to_iso(str(item.get("ts", "") or ""))
            artist = str(item.get("master_metadata_album_artist_name", "") or "").strip()
            track = str(item.get("master_metadata_track_name", "") or "").strip()
            ms_int = _safe_int(item.get("ms_played", 0), 0)

        # Guard: if we still don't have a timestamp, skip
        if not played_at:
            continue

        yield {
            "played_at": played_at,
            "artist_name": artist,
            "track_name": track,
            "ms_played": str(ms_int),
            "source_file": path.name,
        }


def read_existing_keys(csv_path: Path) -> set[Tuple[str, str, str, str]]:
    """
    De-dupe key: (played_at, artist_name, track_name, ms_played)
    """
    keys: set[Tuple[str, str, str, str]] = set()
    if not csv_path.exists():
        return keys
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            keys.add(
                (
                    (row.get("played_at") or ""),
                    (row.get("artist_name") or ""),
                    (row.get("track_name") or ""),
                    (row.get("ms_played") or ""),
                )
            )
    return keys


def discover_json_files(raw_dir: Path) -> List[Path]:
    patterns = [
        "StreamingHistory_music_*.json",   # old export style
        "Streaming_History_Audio_*.json",  # extended export style
    ]
    files: List[Path] = []
    for pat in patterns:
        files.extend(Path(p).resolve() for p in glob.glob(str(raw_dir / pat)))

    # Ignore video history explicitly
    files = [p for p in files if "Streaming_History_Video" not in p.name]
    return sorted(set(files))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--raw-dir", default=str(RAW_DIR))
    args = p.parse_args()

    raw_dir = Path(args.raw_dir)
    if not raw_dir.exists():
        raise SystemExit(f"Missing raw dir: {raw_dir}")

    json_files = discover_json_files(raw_dir)
    if not json_files:
        raise SystemExit(f"No matching Spotify history JSON files found in {raw_dir}")

    fieldnames = ["played_at", "artist_name", "track_name", "ms_played", "source_file"]

    existing = read_existing_keys(OUT_CSV)
    new_rows: List[Dict[str, str]] = []
    seen_new: set[Tuple[str, str, str, str]] = set()

    per_file_new = {}

    for jf in json_files:
        count_new_for_file = 0
        for row in iter_rows_from_json(jf):
            key = (row["played_at"], row["artist_name"], row["track_name"], row["ms_played"])
            if key in existing or key in seen_new:
                continue
            seen_new.add(key)
            new_rows.append(row)
            count_new_for_file += 1
        per_file_new[jf.name] = count_new_for_file

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
    # show a few file-level counts to confirm extended files are contributing
    sample = list(per_file_new.items())[:8]
    print("Sample per-file new rows:", sample)
    print(f"Wrote: {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
