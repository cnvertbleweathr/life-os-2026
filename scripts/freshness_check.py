#!/usr/bin/env python3
"""
freshness_check.py — notice when ONS quietly stops updating.

Two silent failures in Oct 2026 went unnoticed for days: 2026 CFB scores
stalled at Week 4 for three weeks, and sync_playlist_artists failed every
day for six. Both were visible in the data; nothing was looking.

Checks
  steps     Every sync step in ops.pipeline_runs:
              - ALERT if its latest runs failed 2+ times in a row
              - ALERT if its last success is older than it should be.
                "Should be" is learned from the step's own history (median
                gap between runs), so Mon/Thu or in-season-only steps don't
                need hand-written schedules.
  sync      ALERT if no step has run at all in 30h (the sync itself stopped).
  backups   ALERT if the newest DuckDB backup is older than 36h.
  cfb       In season (Sep–mid Dec): ALERT if the newest final score in
            cfbd.games is more than 9 days old.
  daily10   WARN if the Daily 10 playlist hasn't been rebuilt in 36h.
  shows     WARN if Denver show listings haven't been refreshed in 3 days.

Not checked on purpose: Spotify streaming history (loaded from Spotify's
data-export files, so it only moves when you drop in a new export), and
anything driven by your behaviour (runs, habits, books).

Output: a table on stdout, data/daily/<date>/freshness.json, a row per check
in ops.freshness_checks, and one ntfy push if anything is ALERT or WARN.
Exits 0 unless --strict, so it never blocks the daily sync.

Usage
  python scripts/freshness_check.py              # check, record, notify
  python scripts/freshness_check.py --no-notify --no-record
  python scripts/freshness_check.py --strict     # exit 1 on any ALERT
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo(os.getenv("ONS_TZ", "America/Denver"))

OK, WARN, ALERT = "ok", "warn", "alert"
RANK = {OK: 0, WARN: 1, ALERT: 2}


def data_dir() -> Path:
    return Path(os.getenv("ONS_DATA_DIR", ROOT / "data"))


def db_path() -> str:
    return os.getenv("ONS_DUCKDB_PATH", str(ROOT / "data" / "warehouse" / "ons.duckdb"))


@dataclass
class Finding:
    check: str
    subject: str
    status: str
    detail: str
    last_seen: str | None = None


# ── helpers ───────────────────────────────────────────────────────────────────

def _local(ts: datetime) -> datetime:
    """Naive timestamps (daily_sync writes local time) are taken as local."""
    return ts.replace(tzinfo=TZ) if ts.tzinfo is None else ts.astimezone(TZ)


def _parse(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return _local(value)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=TZ)
    try:
        return _local(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except ValueError:
        return None


def _age(now: datetime, then: datetime) -> str:
    hours = (now - then).total_seconds() / 3600
    return f"{hours:.0f}h ago" if hours < 48 else f"{hours / 24:.1f}d ago"


def _table_exists(con, schema: str, table: str) -> bool:
    return bool(con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = ? AND table_name = ?",
        [schema, table],
    ).fetchone()[0])


# ── checks ────────────────────────────────────────────────────────────────────

def check_steps(con, now: datetime, window_days: int = 45) -> list[Finding]:
    if not _table_exists(con, "ops", "pipeline_runs"):
        return [Finding("sync", "pipeline_runs", WARN,
                        "ops.pipeline_runs doesn't exist yet; step history unavailable")]

    rows = con.execute("""
        SELECT source_name, started_at, status
        FROM ops.pipeline_runs
        WHERE status IN ('ok', 'failed')
    """).fetchall()

    cutoff = now - timedelta(days=window_days)
    runs: dict[str, list[tuple[datetime, str]]] = {}
    for name, started, status in rows:
        ts = _parse(started)
        if ts and ts >= cutoff:
            runs.setdefault(name, []).append((ts, status))

    findings: list[Finding] = []
    latest_any: datetime | None = None

    for name, history in sorted(runs.items()):
        history.sort()
        latest_any = max(latest_any, history[-1][0]) if latest_any else history[-1][0]

        # Consecutive failures at the end of the history.
        streak = 0
        for _, status in reversed(history):
            if status != "failed":
                break
            streak += 1
        oks = [ts for ts, s in history if s == "ok"]
        last_ok = oks[-1] if oks else None

        # Expected interval: median gap between distinct run days.
        days = sorted({ts.date() for ts, _ in history})
        gaps = [(b - a).days for a, b in zip(days, days[1:])]
        typical = statistics.median(gaps) if len(gaps) >= 2 else 1
        allowed = timedelta(days=max(2.0, 2 * typical + 1))

        seen = last_ok.isoformat(timespec="minutes") if last_ok else None
        if streak >= 2:
            first_fail = history[-streak][0]
            findings.append(Finding(
                "steps", name, ALERT,
                f"failed {streak} runs in a row since {first_fail:%b %d}",
                seen,
            ))
        elif last_ok is None:
            findings.append(Finding("steps", name, ALERT,
                                    f"no successful run in {window_days} days", None))
        elif now - last_ok > allowed:
            findings.append(Finding(
                "steps", name, ALERT,
                f"last success {_age(now, last_ok)} (usually runs every {typical:g}d)",
                seen,
            ))
        else:
            findings.append(Finding("steps", name, OK, f"last success {_age(now, last_ok)}", seen))

    if latest_any is None or now - latest_any > timedelta(hours=30):
        detail = (f"last step ran {_age(now, latest_any)}" if latest_any
                  else "no runs recorded")
        findings.append(Finding("sync", "daily_sync", ALERT,
                                f"daily sync hasn't run: {detail}",
                                latest_any.isoformat(timespec="minutes") if latest_any else None))
    else:
        findings.append(Finding("sync", "daily_sync", OK, f"last step ran {_age(now, latest_any)}",
                                latest_any.isoformat(timespec="minutes")))
    return findings


def check_backups(now: datetime) -> Finding:
    files = list((data_dir() / "backups" / "duckdb").glob("ons_*.duckdb"))
    if not files:
        return Finding("backups", "duckdb", ALERT, "no backups found in data/backups/duckdb")
    newest = max(files, key=lambda p: p.stat().st_mtime)
    ts = datetime.fromtimestamp(newest.stat().st_mtime, TZ)
    status = ALERT if now - ts > timedelta(hours=36) else OK
    return Finding("backups", "duckdb", status, f"newest backup {_age(now, ts)} ({newest.name})",
                   ts.isoformat(timespec="minutes"))


def in_cfb_season(d: date) -> bool:
    return (d.month in (9, 10, 11)) or (d.month == 12 and d.day <= 15)


def check_cfb(con, now: datetime) -> Finding | None:
    if not in_cfb_season(now.date()):
        return None
    if not _table_exists(con, "cfbd", "games"):
        return Finding("cfb", "scores", ALERT, "cfbd.games doesn't exist")
    row = con.execute("""
        SELECT max(start_date), max(week)
        FROM cfbd.games
        WHERE season = ? AND home_points IS NOT NULL
    """, [now.year]).fetchone()
    latest = _parse(row[0]) if row else None
    if latest is None:
        return Finding("cfb", "scores", ALERT, f"no {now.year} final scores loaded")
    status = ALERT if now - latest > timedelta(days=9) else OK
    return Finding("cfb", "scores", status,
                   f"newest final score {_age(now, latest)} (through week {row[1]})",
                   latest.isoformat(timespec="minutes"))


def check_daily10(now: datetime) -> Finding:
    path = data_dir() / "spotify" / "processed" / "daily10_latest.json"
    try:
        ts = _parse(json.loads(path.read_text()).get("updated_at_utc"))
    except (OSError, ValueError):
        ts = None
    if ts is None:
        return Finding("daily10", "playlist", WARN, "daily10_latest.json missing or unreadable")
    status = WARN if now - ts > timedelta(hours=36) else OK
    return Finding("daily10", "playlist", status, f"rebuilt {_age(now, ts)}",
                   ts.isoformat(timespec="minutes"))


def check_shows(now: datetime) -> list[Finding]:
    out = []
    for name, fname in [("aeg", "denver_events_upcoming.csv"),
                        ("ticketmaster", "denver_events_ticketmaster.csv")]:
        path = data_dir() / "shows" / "processed" / fname
        if not path.exists():
            out.append(Finding("shows", name, WARN, f"{fname} missing"))
            continue
        ts = datetime.fromtimestamp(path.stat().st_mtime, TZ)
        status = WARN if now - ts > timedelta(days=3) else OK
        out.append(Finding("shows", name, status, f"refreshed {_age(now, ts)}",
                           ts.isoformat(timespec="minutes")))
    return out


def run_checks(con, now: datetime) -> list[Finding]:
    findings = check_steps(con, now)
    findings.append(check_backups(now))
    cfb = check_cfb(con, now)
    if cfb:
        findings.append(cfb)
    findings.append(check_daily10(now))
    findings.extend(check_shows(now))
    return findings


# ── output ────────────────────────────────────────────────────────────────────

def render(findings: list[Finding]) -> str:
    icon = {OK: "✓", WARN: "!", ALERT: "✗"}
    lines = []
    for f in sorted(findings, key=lambda f: (-RANK[f.status], f.check, f.subject)):
        lines.append(f"  {icon[f.status]}  {f.check:<8} {f.subject:<28} {f.detail}")
    return "\n".join(lines)


def record(findings: list[Finding], now: datetime) -> None:
    con = duckdb.connect(db_path())
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS ops")
        con.execute("""
            CREATE TABLE IF NOT EXISTS ops.freshness_checks (
                checked_at TIMESTAMPTZ, check_name VARCHAR, subject VARCHAR,
                status VARCHAR, detail VARCHAR, last_seen VARCHAR
            )
        """)
        con.executemany(
            "INSERT INTO ops.freshness_checks VALUES (?, ?, ?, ?, ?, ?)",
            [(now, f.check, f.subject, f.status, f.detail, f.last_seen) for f in findings],
        )
    finally:
        con.close()

    out = data_dir() / "daily" / now.date().isoformat()
    out.mkdir(parents=True, exist_ok=True)
    (out / "freshness.json").write_text(json.dumps(
        {"checked_at": now.isoformat(timespec="seconds"),
         "findings": [asdict(f) for f in findings]}, indent=2))


def notify(findings: list[Finding]) -> None:
    bad = [f for f in findings if f.status != OK]
    if not bad:
        return
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        from notify import send
    except Exception:
        return
    alerts = [f for f in bad if f.status == ALERT]
    title = (f"ONS: {len(alerts)} stale source{'s' if len(alerts) != 1 else ''}"
             if alerts else "ONS: freshness warnings")
    body = "\n".join(f"{'✗' if f.status == ALERT else '!'} {f.subject}: {f.detail}"
                     for f in sorted(bad, key=lambda f: -RANK[f.status]))
    send(title, body, priority="high" if alerts else "default", tags=["hourglass"])


def main() -> int:
    p = argparse.ArgumentParser(description="Detect ONS data sources that stopped updating.")
    p.add_argument("--no-notify", action="store_true", help="don't send an ntfy push")
    p.add_argument("--no-record", action="store_true",
                   help="don't write ops.freshness_checks or freshness.json (read-only)")
    p.add_argument("--strict", action="store_true", help="exit 1 if any check is ALERT")
    args = p.parse_args()

    now = datetime.now(timezone.utc).astimezone(TZ)
    con = duckdb.connect(db_path(), read_only=True)
    try:
        findings = run_checks(con, now)
    finally:
        con.close()

    print(f"ONS freshness — {now:%Y-%m-%d %H:%M %Z}")
    print(render(findings))

    if not args.no_record:
        record(findings, now)
    if not args.no_notify:
        notify(findings)

    worst = max((RANK[f.status] for f in findings), default=0)
    return 1 if args.strict and worst == RANK[ALERT] else 0


if __name__ == "__main__":
    raise SystemExit(main())
