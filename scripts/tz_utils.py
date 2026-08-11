"""
tz_utils.py — shared timezone helpers for ONS.

Problem this solves:
  Scripts that call datetime.now() or datetime.utcnow() get UTC-based dates.
  Since Karey is in America/Denver (UTC-6/UTC-7), any job that runs, or any
  event that gets logged, between midnight UTC and midnight Denver time gets
  stamped with tomorrow's date. Habits, daily syncs, and the morning brief
  have all shown this bug as "today's habit shows up as not-yet-logged" or
  "the brief runs for the wrong day."

Use this module everywhere a script needs "what day is it for the user,"
"what year is it for the user," or "how far through the year are we."
Do not call datetime.now() / datetime.today() / date.today() directly for
anything user-facing — import from here instead.

Usage:
    from tz_utils import today_denver, denver_year, year_progress_pct, log_timestamp

    today = today_denver()                # date(2026, 7, 3)
    year = denver_year()                  # 2026
    pct = year_progress_pct()             # 50.4
    ts = log_timestamp()                  # "2026-07-03T14:32:01-06:00"
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

# Change this once if Karey ever relocates; every helper below derives from it.
LOCAL_TZ = ZoneInfo("America/Denver")


def now_denver() -> datetime:
    """Current timezone-aware datetime in America/Denver."""
    return datetime.now(LOCAL_TZ)


def today_denver() -> date:
    """Current calendar date in America/Denver (not UTC)."""
    return now_denver().date()


def denver_year() -> int:
    """Current calendar year in America/Denver."""
    return today_denver().year


def denver_iso_week() -> int:
    """Current ISO week number in America/Denver."""
    return today_denver().isocalendar().week


def year_progress_pct(year: int | None = None) -> float:
    """
    Percent of the given year (default: current Denver year) that has elapsed,
    based on today's date in America/Denver. Correctly handles leap years.

    year_progress_pct(2026) on 2026-07-03 -> ~50.1
    """
    if year is None:
        year = denver_year()

    start = date(year, 1, 1)
    end = date(year + 1, 1, 1)
    total_days = (end - start).days

    today = today_denver()
    if today < start:
        return 0.0
    if today >= end:
        return 100.0

    elapsed_days = (today - start).days + 1  # inclusive of today
    return round(100 * elapsed_days / total_days, 2)


def log_timestamp() -> str:
    """
    ISO-8601 timestamp in America/Denver, suitable for writing into logs,
    CSVs, or DuckDB tables where you want a human-legible local timestamp
    rather than a bare UTC one. Includes the UTC offset so it's unambiguous.
    """
    return now_denver().isoformat(timespec="seconds")


def to_denver(dt: datetime) -> datetime:
    """
    Convert any datetime (naive or tz-aware) to America/Denver.
    Naive datetimes are assumed to already be UTC (matches how most of
    the DLT pipelines in this repo store timestamps).
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(LOCAL_TZ)


if __name__ == "__main__":
    # Quick manual sanity check: python scripts/tz_utils.py
    print("now_denver:      ", now_denver())
    print("today_denver:    ", today_denver())
    print("denver_year:     ", denver_year())
    print("denver_iso_week: ", denver_iso_week())
    print("year_progress_pct:", year_progress_pct())
    print("log_timestamp:   ", log_timestamp())
