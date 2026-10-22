"""
api/store.py — the ONS write path.

DuckDB allows one writer, and FastAPI holds a read-only connection to it, so
the API never writes to the warehouse. Instead, anything entered in the web UI
is appended to a small JSONL log on disk. The daily sync loads those logs into
DuckDB with DLT (pipelines/habits_pipeline.py, checkin_pipeline.py,
inbox_pipeline.py), exactly like the original Streamlit habit tracker did.

Why JSONL rather than SQLite:
  - It is the format habits already use, so no migration.
  - Append-only means every edit is kept; readers take the latest row per key.
  - DLT reads it directly; no extra driver or schema to manage.

Concurrency: appends take an exclusive flock and fsync, so two requests (or a
request and the Streamlit page during the transition) can't interleave lines.

Logs:
  data/habits/habits_log.jsonl     one full-day snapshot per write
  data/checkin/checkin_log.jsonl   one full check-in per write
  data/inbox/capture_inbox.jsonl   one captured item per write

Set ONS_DATA_DIR to point the logs somewhere else (tests do this).
Set ONS_TZ to change what "today" means (defaults to America/Denver, matching
scripts/tz_utils.py).
"""

from __future__ import annotations

import fcntl
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    return Path(os.getenv("ONS_DATA_DIR", ROOT / "data"))


def local_tz() -> ZoneInfo:
    return ZoneInfo(os.getenv("ONS_TZ", "America/Denver"))


def now_local() -> datetime:
    return datetime.now(local_tz())


def today_local() -> date:
    """The user's calendar date. Never date.today(), which is UTC on servers."""
    return now_local().date()


def timestamp() -> str:
    return now_local().isoformat(timespec="seconds")


class JsonlLog:
    """An append-only JSONL file. Reads tolerate blank and corrupt lines."""

    def __init__(self, *parts: str):
        self._parts = parts

    @property
    def path(self) -> Path:
        # Resolved on every access so ONS_DATA_DIR can change between tests.
        return data_dir().joinpath(*self._parts)

    def append(self, record: dict[str, Any]) -> dict[str, Any]:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        with path.open("a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        return record

    def rows(self) -> list[dict[str, Any]]:
        path = self.path
        if not path.exists():
            return []
        out: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    out.append(row)
        return out

    def latest_by(self, key: str) -> dict[Any, dict[str, Any]]:
        """Last row for each value of `key` (later lines win)."""
        latest: dict[Any, dict[str, Any]] = {}
        for row in self.rows():
            k = row.get(key)
            if k is not None:
                latest[k] = row
        return latest


HABITS_LOG  = JsonlLog("habits", "habits_log.jsonl")
CHECKIN_LOG = JsonlLog("checkin", "checkin_log.jsonl")
INBOX_LOG   = JsonlLog("inbox", "capture_inbox.jsonl")


def date_window(days: int, end: date | None = None) -> list[date]:
    """`days` consecutive dates ending at `end` (default today), oldest first."""
    end = end or today_local()
    return [end - timedelta(days=i) for i in range(days - 1, -1, -1)]


def validate_log_date(value: str | None, max_back_days: int = 7) -> str:
    """
    Accept today or a recent past date (for backfilling yesterday).
    Raises ValueError for future dates, bad formats, or dates too far back.
    """
    today = today_local()
    if value is None:
        return today.isoformat()
    d = date.fromisoformat(value)
    if d > today:
        raise ValueError("date is in the future")
    if (today - d).days > max_back_days:
        raise ValueError(f"date is more than {max_back_days} days ago")
    return d.isoformat()


def pick(row: dict[str, Any], keys: Iterable[str]) -> dict[str, Any]:
    return {k: row.get(k) for k in keys}
