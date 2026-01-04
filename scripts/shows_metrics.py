#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]

IN_AEG = ROOT / "data" / "shows" / "processed" / "denver_events_upcoming.csv"
IN_TM = ROOT / "data" / "shows" / "processed" / "denver_events_ticketmaster.csv"

OUT_DIR = ROOT / "data" / "shows" / "metrics"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DENVER_TZ = ZoneInfo("America/Denver")
UTC = ZoneInfo("UTC")


def _parse_dt(value: str) -> Optional[datetime]:
    """
    Parse ISO-ish datetime strings:
      - AEG: 2026-01-09T20:00:00-07:00
      - TM:  2026-01-09T03:00:00Z  (UTC)
      - TM alt: 2026-01-09T20:00:00  (naive)
      - TM alt: 2026-01-09  (date-only)

    Returns a datetime that may be naive or aware.
    """
    if not value:
        return None

    s = value.strip()

    # Handle trailing Z (UTC)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    # Try fromisoformat
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass

    # Fallback date-only
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue

    return None


def _as_aware_denver(dt: datetime) -> datetime:
    """
    Ensure dt is timezone-aware in America/Denver.
    - If naive: assume it is already local Denver time.
    - If aware: convert to Denver.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=DENVER_TZ)
    return dt.astimezone(DENVER_TZ)


def _utc_ts(dt: datetime) -> float:
    """
    Convert datetime to a comparable UTC timestamp.
    """
    aware_denver = _as_aware_denver(dt)
    return aware_denver.astimezone(UTC).timestamp()


def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    rows: List[Dict[str, str]] = []
    with open(path, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append({k: (v or "").strip() for k, v in row.items()})
    return rows


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def _dedupe_key(row: Dict[str, str]) -> str:
    """
    Prefer event_url as stable key when present.
    Otherwise fall back to normalized (title, venue, start_datetime).
    """
    url = row.get("event_url", "").strip()
    if url:
        return f"url:{url}"

    title = _norm(row.get("title", ""))
    venue = _norm(row.get("venue_name", ""))
    start = row.get("start_datetime", "").strip()
    base = f"{title}|{venue}|{start}"
    return "sig:" + hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def main() -> int:
    p = argparse.ArgumentParser(description="Compute combined Denver shows metrics (AEG + Ticketmaster).")
    p.add_argument("--year", type=int, required=True)
    args = p.parse_args()

    rows_aeg = _read_csv(IN_AEG)
    rows_tm = _read_csv(IN_TM)
    rows = rows_aeg + rows_tm

    # De-dupe across sources
    dedup: Dict[str, Dict[str, str]] = {}
    for row in rows:
        k = _dedupe_key(row)
        if k not in dedup:
            dedup[k] = row
    rows = list(dedup.values())

    # Filter to year (using Denver-local year), and prepare sortable tuples
    filtered: List[Tuple[float, datetime, Dict[str, str]]] = []
    for row in rows:
        dt_raw = _parse_dt(row.get("start_datetime", ""))
        if not dt_raw:
            continue

        dt_denver = _as_aware_denver(dt_raw)
        if dt_denver.year != args.year:
            continue

        filtered.append((_utc_ts(dt_raw), dt_denver, row))

    filtered.sort(key=lambda x: x[0])

    upcoming_count = len(filtered)

    if filtered:
        _, next_dt_denver, next_row = filtered[0]
        next_show_date = next_dt_denver.date().isoformat()
        next_show_datetime = next_dt_denver.isoformat()
        next_show_title = next_row.get("title", "")
        next_show_venue = next_row.get("venue_name", "")
        next_show_url = next_row.get("event_url", "")
    else:
        next_show_date = ""
        next_show_datetime = ""
        next_show_title = ""
        next_show_venue = ""
        next_show_url = ""

    unique_venues = {r.get("venue_name", "").strip() for _, _, r in filtered if r.get("venue_name", "").strip()}

    sources_present = sorted({(r.get("source") or "").strip() for r in rows if (r.get("source") or "").strip()})

    summary = {
        "year": str(args.year),
        "denver_upcoming_show_count": str(upcoming_count),
        "next_show_date": next_show_date,
        "next_show_datetime": next_show_datetime,
        "next_show_title": next_show_title,
        "next_show_venue": next_show_venue,
        "next_show_url": next_show_url,
        "unique_venues_count": str(len(unique_venues)),
        "sources_present": ",".join(sources_present),
        "aeg_rows": str(len(rows_aeg)),
        "ticketmaster_rows": str(len(rows_tm)),
        "combined_deduped_rows": str(len(rows)),
    }

    out_path = OUT_DIR / f"shows_summary_{args.year}.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary.keys()))
        w.writeheader()
        w.writerow(summary)

    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
