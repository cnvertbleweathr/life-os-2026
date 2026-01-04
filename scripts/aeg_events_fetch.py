#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urljoin

import requests
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]

# Prefer multi-feed env var
AEG_URLS_RAW = (os.getenv("AEG_EVENTS_URLS") or "").strip()
SINGLE_URL = (os.getenv("AEG_EVENTS_URL") or "").strip()

if AEG_URLS_RAW:
    AEG_URLS = [u.strip() for u in AEG_URLS_RAW.split("|") if u.strip()]
elif SINGLE_URL:
    AEG_URLS = [SINGLE_URL]
else:
    raise SystemExit("Missing AEG_EVENTS_URLS (preferred) or AEG_EVENTS_URL in environment (.env).")

# Optional venue-name filter (usually not needed when URLs are explicit)
VENUES_RAW = (os.getenv("AEG_VENUES") or "").strip()
VENUE_FILTERS = [v.strip().lower() for v in VENUES_RAW.split("|") if v.strip()] if VENUES_RAW else []

RAW_DIR = ROOT / "data" / "shows" / "raw" / "aeg"
OUT_DIR = ROOT / "data" / "shows" / "processed"
RAW_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_SITE = "https://www.axs.com"


def _today_yyyymmdd() -> str:
    return datetime.now().strftime("%Y%m%d")


def _as_list(obj: Any) -> List[Any]:
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        v = obj.get("events")
        if isinstance(v, list):
            return v
    return []


def _get_first(d: Dict[str, Any], keys: List[str]) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def _normalize_venue(ev: Dict[str, Any]) -> Dict[str, str]:
    venue_obj = ev.get("venue") or {}
    if not isinstance(venue_obj, dict):
        venue_obj = {}

    name = str(_get_first(venue_obj, ["name", "title", "venueName", "displayName"]) or "")
    city = str(_get_first(venue_obj, ["city"]) or "")
    region = str(_get_first(venue_obj, ["region", "state", "province", "stateCode"]) or "")
    country = str(_get_first(venue_obj, ["country"]) or "")

    return {
        "venue_name": name,
        "venue_city": city,
        "venue_region": region,
        "venue_country": country,
    }


def _normalize_title(ev: Dict[str, Any]) -> str:
    t = ev.get("title")
    if isinstance(t, dict):
        return str(_get_first(t, ["eventTitleText", "headlinersText", "presentedByText"]) or "").strip()
    if isinstance(t, str):
        return t.strip()
    return str(_get_first(ev, ["name", "eventName", "headline"]) or "").strip()


def _normalize_lineup(ev: Dict[str, Any]) -> Dict[str, str]:
    t = ev.get("title")
    if not isinstance(t, dict):
        return {"presented_by": "", "headliners": "", "supporting": ""}
    return {
        "presented_by": str(t.get("presentedByText") or "").strip(),
        "headliners": str(t.get("headlinersText") or t.get("eventTitleText") or "").strip(),
        "supporting": str(t.get("supportingText") or "").strip(),
    }


def _normalize_start(ev: Dict[str, Any]) -> str:
    s = _get_first(ev, ["eventDateTimeISO", "eventDateTime", "eventDateTimeUTC"])
    return str(s or "").strip()


def _normalize_url(ev: Dict[str, Any]) -> str:
    links = ev.get("links")

    if isinstance(links, dict):
        for k in ["event", "tickets", "axs", "url", "eventUrl", "purchase"]:
            v = links.get(k)
            if isinstance(v, str) and v.strip():
                return urljoin(BASE_SITE, v.strip())
        for v in links.values():
            if isinstance(v, str) and v.strip().startswith("http"):
                return v.strip()

    if isinstance(links, list):
        for item in links:
            if isinstance(item, str) and item.strip():
                return urljoin(BASE_SITE, item.strip())
            if isinstance(item, dict):
                u = item.get("url") or item.get("href")
                if isinstance(u, str) and u.strip():
                    return urljoin(BASE_SITE, u.strip())

    ticketing = ev.get("ticketing")
    if isinstance(ticketing, dict):
        u = ticketing.get("url") or ticketing.get("purchaseUrl")
        if isinstance(u, str) and u.strip():
            return urljoin(BASE_SITE, u.strip())

    return ""


def _hash_id(source: str, title: str, start: str, venue: str, url: str) -> str:
    base = f"{source}|{title}|{start}|{venue}|{url}".encode("utf-8")
    return hashlib.sha1(base).hexdigest()[:16]


def _matches_venue_filter(venue_name: str) -> bool:
    if not VENUE_FILTERS:
        return True
    v = (venue_name or "").lower()
    return any(f in v for f in VENUE_FILTERS)


def fetch_json(url: str) -> Dict[str, Any]:
    r = requests.get(url, timeout=30, headers={"User-Agent": "life-os-2026/1.0 (personal use)"})
    r.raise_for_status()
    return r.json()


def _venue_id_from_url(url: str) -> str:
    # .../events/<id>/events.json
    parts = url.split("/events/")
    if len(parts) >= 2:
        tail = parts[1]
        return tail.split("/")[0]
    return ""


def main() -> int:
    stamp = _today_yyyymmdd()
    all_rows: List[Dict[str, str]] = []

    for url in AEG_URLS:
        venue_id = _venue_id_from_url(url)
        raw_path = RAW_DIR / f"events_{venue_id}_{stamp}.json" if venue_id else RAW_DIR / f"events_{stamp}.json"

        data = fetch_json(url)
        raw_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        events = _as_list(data)
        for ev in events:
            if not isinstance(ev, dict):
                continue

            venue_info = _normalize_venue(ev)
            venue_name = venue_info["venue_name"]
            if not _matches_venue_filter(venue_name):
                continue

            title = _normalize_title(ev)
            lineup = _normalize_lineup(ev)
            start = _normalize_start(ev)
            event_url = _normalize_url(ev)

            event_id = str(ev.get("eventId") or ev.get("id") or "")
            if not event_id:
                event_id = _hash_id("aeg", title, start, venue_name, event_url)

            all_rows.append({
                "event_id": event_id,
                "source": "aeg",
                "source_venue_id": venue_id,
                "title": title,
                "start_datetime": start,
                "venue_name": venue_name,
                "venue_city": venue_info["venue_city"],
                "venue_region": venue_info["venue_region"],
                "venue_country": venue_info["venue_country"],
                "event_url": event_url,
                "presented_by": lineup["presented_by"],
                "headliners": lineup["headliners"],
                "supporting": lineup["supporting"],
            })

    # de-dupe by (event_id, source) just in case
    seen = set()
    deduped = []
    for r in all_rows:
        k = (r["source"], r["event_id"])
        if k in seen:
            continue
        seen.add(k)
        deduped.append(r)

    out_csv = OUT_DIR / "denver_events_upcoming.csv"
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
        for r in deduped:
            w.writerow(r)

    print(f"Wrote processed: {out_csv} (rows={len(deduped)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
