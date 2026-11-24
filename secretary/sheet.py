"""
Secretary day sheet: what the paper and the check-in packet show for one day.

Written by the sync right after the heads-up refresh (secretary/headsups.py
--refresh), to data/secretary/days/<date>.json (gitignored). The paper and the
packet read this file, never the warehouse, so a reprint of an old edition shows
that day's heads-ups and printing at 5am never needs DuckDB. The website reads
secretary.headsups live instead (it has done/dismiss buttons).

  lead          critical day-of heads-ups (surface paper_lead): the paper's top bar
  today         heads-ups picked today for the paper (nag limit already applied)
  coming_up     next `coming_up_days` (14) days, critical → nice_to_know, no trivia,
                minus anything already in today/lead; the paper shows the first 8
  weekend       Fridays only: critical and important events on Saturday and Sunday
  checkin_today heads-ups picked today for the Slack packet
  checkin_coming_up  next 30 days, critical and important only (the packet)
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from secretary import config as SC
from secretary import headsups as H

PACKET_DAYS = 30


def days_dir() -> Path:
    return SC.secretary_dir() / "days"


def sheet_path(day: date) -> Path:
    return days_dir() / f"{day.isoformat()}.json"


def _label(d: date) -> str:
    return f"{d:%a %b} {d.day}"


def _rel(d: date, today: date) -> str:
    n = (d - today).days
    return "today" if n == 0 else "tomorrow" if n == 1 else f"in {n} days"


def _time(start_at: Any, all_day: bool) -> str | None:
    if all_day or not isinstance(start_at, datetime):
        return None
    t = start_at.astimezone(SC.TZ)
    return f"{t:%-I:%M%p}".lower().replace(":00", "")


def _events(con, start: date, end: date) -> list[dict]:
    try:
        rows = con.execute(
            """SELECT event_key, display_title, tier, event_date, start_at, all_day
               FROM main_intermediate.int_events_tiered
               WHERE event_date BETWEEN ? AND ? AND tier <> 'trivia'""", [start, end]).fetchall()
    except Exception:                                      # dbt hasn't built it (yet): no listings
        return []
    out = [{"event_key": k, "title": t, "tier": tier, "date": d, "time": _time(s, a)}
           for k, t, tier, d, s, a in rows]
    return sorted(out, key=lambda e: (H.TIER_RANK[e["tier"]], e["date"], e["time"] or "", e["title"]))


def _listing(e: dict, today: date) -> dict:
    return {"title": e["title"], "tier": e["tier"], "date": e["date"].isoformat(), "label": _label(e["date"]),
            "time": e["time"], "rel": _rel(e["date"], today)}


def _headsup(h: dict, today: date) -> dict:
    return {"id": h["headsup_id"], "text": h["text"], "title": h["title"], "tier": h["tier"],
            "date": h["event_date"].isoformat(), "label": _label(h["event_date"]),
            "rel": _rel(h["event_date"], today), "shown_count": h["shown_count"]}


def build(con, cfg: SC.Config, today: date) -> dict[str, Any]:
    picked = H.shown_today(con, today)
    lead = [h for h in picked if "paper_lead" in h["surfaces"]]
    paper = [h for h in picked if "paper" in h["surfaces"] and h not in lead]
    on_paper = {h["event_key"] for h in lead + paper}

    weekend: list[dict] = []
    if today.weekday() == 4:                               # Friday
        sat, sun = today + timedelta(days=1), today + timedelta(days=2)
        weekend = [e for e in _events(con, sat, sun) if e["tier"] in ("critical", "important")]
    in_weekend = {e["event_key"] for e in weekend}

    horizon = int(cfg.settings["coming_up_days"])
    coming = [e for e in _events(con, today + timedelta(days=1), today + timedelta(days=horizon))
              if e["event_key"] not in on_paper and e["event_key"] not in in_weekend]
    packet = [e for e in _events(con, today + timedelta(days=1), today + timedelta(days=PACKET_DAYS))
              if e["tier"] in ("critical", "important")]

    return {
        "date": today.isoformat(),
        "lead": [_headsup(h, today) for h in lead],
        "today": [_headsup(h, today) for h in paper],
        "coming_up": [_listing(e, today) for e in coming],
        "weekend": [_listing(e, today) for e in weekend],
        "checkin_today": [_headsup(h, today) for h in picked if "checkin" in h["surfaces"]],
        "checkin_coming_up": [_listing(e, today) for e in packet],
    }


def write(sheet: dict[str, Any]) -> Path:
    path = sheet_path(date.fromisoformat(sheet["date"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(sheet, indent=2, ensure_ascii=False))
    tmp.replace(path)
    return path


def load(day: date) -> dict[str, Any] | None:
    path = sheet_path(day)
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def build_and_write(today: date, *, cfg: SC.Config | None = None, path: Path | None = None) -> Path:
    import duckdb
    con = duckdb.connect(str(path or SC.db_path()), read_only=True)
    try:
        return write(build(con, cfg or SC.load(), today))
    finally:
        con.close()
