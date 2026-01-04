#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]

BASE = "https://app.ticketmaster.com/discovery/v2/events.json"

RAW_DIR = ROOT / "data" / "shows" / "raw" / "ticketmaster"
OUT_DIR = ROOT / "data" / "shows" / "processed"
RAW_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

API_KEY = (os.getenv("TICKETMASTER_API_KEY") or "").strip()
if not API_KEY:
    raise SystemExit("Missing TICKETMASTER_API_KEY in environment (.env).")

TM_CITY = (os.getenv("TM_CITY") or "Denver").strip()
TM_STATE = (os.getenv("TM_STATE") or "CO").strip()
TM_COUNTRY = (os.getenv("TM_COUNTRY") or "US").strip()
TM_RADIUS_MILES = (os.getenv("TM_RADIUS_MILES") or "50").strip()
TM_CLASSIFICATION = (os.getenv("TM_CLASSIFICATION") or "music").strip()
TM_SIZE = int((os.getenv("TM_SIZE") or "200").strip())

USER_AGENT = "life-os-2026/1.0 (personal use)"


def _today_yyyymmdd() -> str:
    return datetime.now().strftime("%Y%m%d")


def _safe_get(d: Dict[str, Any], path: List[str], default: Any = "") -> Any:
    cur: Any = d
    for p in path:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return default
    return cur


def _first(items: Any) -> Optional[Dict[str, Any]]:
    if isinstance(items, list) and items:
        v = items[0]
        return v if isinstance(v, dict) else None
    return None


def _pick_venue(event: Dict[str, Any]) -> Tuple[str, str, str, str]:
    """
    Ticketmaster event -> (venue_name, city, state, country)
    """
    venues = _safe_get(event, ["_embedded", "venues"], default=[])
    v0 = _first(venues) or {}

    name = str(v0.get("name") or "").strip()
    city = str(_safe_get(v0, ["city", "name"], default="")).strip()
    state = str(_safe_get(v0, ["state", "stateCode"], default="")).strip()
    country = str(_safe_get(v0, ["country", "countryCode"], default="")).strip()
    return name, city, state, country


def _pick_datetime(event: Dict[str, Any]) -> str:
    """
    Prefer local datetime if present; else fallback.
    Ticketmaster typically gives dates.start.dateTime in UTC (Z).
    Also provides localDate/localTime (no tz).
    We'll store dateTime as-is; shows_metrics can parse ISO.
    """
    dt = str(_safe_get(event, ["dates", "start", "dateTime"], default="")).strip()
    if dt:
        return dt
    local_date = str(_safe_get(event, ["dates", "start", "localDate"], default="")).strip()
    local_time = str(_safe_get(event, ["dates", "start", "localTime"], default="")).strip()
    if local_date and local_time:
        return f"{local_date}T{local_time}"
    return local_date


def _pick_title(event: Dict[str, Any]) -> str:
    return str(event.get("name") or "").strip()


def _pick_url(event: Dict[str, Any]) -> str:
    return str(event.get("url") or "").strip()


def _pick_lineup(event: Dict[str, Any]) -> Tuple[str, str]:
    """
    Return (headliners, supporting) approximations from attractions.
    """
    atts = _safe_get(event, ["_embedded", "attractions"], default=[])
    names = []
    if isinstance(atts, list):
        for a in atts:
            if isinstance(a, dict) and a.get("name"):
                names.append(str(a["name"]).strip())
    headliners = names[0] if names else ""
    supporting = ", ".join(names[1:]) if len(names) > 1 else ""
    return headliners, supporting


def fetch_page(page: int) -> Dict[str, Any]:
    params = {
        "apikey": API_KEY,
        "classificationName": TM_CLASSIFICATION,
        "city": TM_CITY,
        "stateCode": TM_STATE,
        "countryCode": TM_COUNTRY,
        "radius": TM_RADIUS_MILES,
        "unit": "miles",
        "size": str(TM_SIZE),
        "page": str(page),
        "sort": "date,asc",
    }
    r = requests.get(BASE, params=params, timeout=30, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    return r.json()


def main() -> int:
    stamp = _today_yyyymmdd()
    all_events: List[Dict[str, Any]] = []

    page = 0
    total_pages: Optional[int] = None

    while True:
        data = fetch_page(page)

        raw_path = RAW_DIR / f"events_{stamp}_page{page}.json"
        raw_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        embedded = data.get("_embedded") or {}
        events = embedded.get("events") if isinstance(embedded, dict) else None
        if not isinstance(events, list):
            events = []

        for ev in events:
            if isinstance(ev, dict):
                all_events.append(ev)

        page_info = data.get("page") if isinstance(data, dict) else None
        if isinstance(page_info, dict):
            total_pages = int(page_info.get("totalPages") or 0)
        else:
            total_pages = total_pages or 0

        page += 1

        # stop when done
        if total_pages and page >= total_pages:
            break

        # be polite to TM
        time.sleep(0.35)

        # safety cap in case TM lies
        if page > 50:
            break

    # Normalize rows
    rows: List[Dict[str, str]] = []
    for ev in all_events:
        venue_name, venue_city, venue_region, venue_country = _pick_venue(ev)
        title = _pick_title(ev)
        start = _pick_datetime(ev)
        url = _pick_url(ev)
        headliners, supporting = _pick_lineup(ev)

        rows.append({
            "event_id": str(ev.get("id") or ""),
            "source": "ticketmaster",
            "source_venue_id": "",  # not applicable
            "title": title,
            "start_datetime": start,
            "venue_name": venue_name,
            "venue_city": venue_city,
            "venue_region": venue_region,
            "venue_country": venue_country,
            "event_url": url,
            "presented_by": "",
            "headliners": headliners,
            "supporting": supporting,
        })

    out_csv = OUT_DIR / "denver_events_ticketmaster.csv"
    fieldnames = [
        "event_id",
        "source",
        "source_venue_id",
        "title",
        "start_datetime",
        "venue_name",
        "venue_city",
        "venue_region",
        "venue_country",
        "event_url",
        "presented_by",
        "headliners",
        "supporting",
    ]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"Wrote processed: {out_csv} (rows={len(rows)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
