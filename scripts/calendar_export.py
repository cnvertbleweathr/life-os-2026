#!/usr/bin/env python3
"""
calendar_export.py: sync every Google Calendar into ONS.

What it fetches (daily, from daily_sync):
  - Every calendar on the account (primary, shared, holidays, and the contacts
    Birthdays calendar), from 7 days back to 60 days ahead.
  - The primary calendar for the whole --year as well, so calendar_metrics
    (date nights for goals/2026.yaml) keeps its full-year CSV.

What it writes:
  calendar.events                         DuckDB table, one row per event occurrence
  data/calendar/processed/events_clean_<year>.csv   primary calendar only (unchanged format)
  data/calendar/raw/events_<year>_<yyyymmdd>.json  raw API response, all calendars
  data/calendar/status.json               {"ok", "checked_at", "message", ...}: read by the
                                          paper ("Calendar unavailable today") and the secretary

Auth:
  - Unattended runs never open a browser; the saved refresh token is used.
  - If Google rejects it, status.json says so, the last line on stderr says
    "Calendar unavailable today: ..." (that line lands in health.txt), the
    previous calendar.events table is kept, and the script exits 2.
  - Sign in by hand once with:  python scripts/calendar_export.py --auth
  - The token file is written owner-only (0600) in the gitignored secrets/ folder.

Refresh tokens that die about 7 days after sign-in mean the Google Cloud OAuth
app is in "Testing". Publish it: Google Cloud Console → Google Auth Platform →
Audience → Publish app. (Unverified is fine for a personal app: you'll click
through an "unverified app" warning once at sign-in.)

Phone notifications are off. ONS_PHONE_NOTIFICATIONS=1 in .env re-enables the
ntfy push on a sign-in failure (opt-in, for later).

DuckDB single-writer: daily_sync stops the API before this step runs.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parents[1]

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]  # read-only is enough
REAUTH_HELP = "Fix: run once at the Mac mini: python scripts/calendar_export.py --auth"
DAYS_BACK, DAYS_AHEAD = 7, 60
BIRTHDAYS_ID = "addressbook#contacts@group.v.calendar.google.com"
TZ = ZoneInfo(os.getenv("ONS_TZ", "America/Denver"))

COLUMNS = ["calendar_id", "calendar_name", "calendar_kind", "event_id", "title", "event_type",
           "all_day", "start_date", "start_at", "end_at", "location", "status", "synced_at"]


class AuthRequired(RuntimeError):
    """Google needs an interactive sign-in; never attempted unattended."""


def data_dir() -> Path:
    return Path(os.getenv("ONS_DATA_DIR") or ROOT / "data")


def db_path() -> Path:
    return Path(os.getenv("ONS_DB_PATH") or ROOT / "data" / "warehouse" / "ons.duckdb")


def status_path() -> Path:
    return data_dir() / "calendar" / "status.json"


# ── auth ──────────────────────────────────────────────────────────────────────

def _owner_only(path: str | Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _save(creds: Any, token_path: str) -> None:
    folder = os.path.dirname(token_path) or "."
    os.makedirs(folder, exist_ok=True)
    try:
        os.chmod(folder, 0o700)
    except OSError:
        pass
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(creds.to_json())
    _owner_only(token_path)


def get_credentials(credentials_path: str, token_path: str, interactive: bool = False):
    creds = None
    if os.path.exists(token_path):
        _owner_only(token_path)
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except (ValueError, json.JSONDecodeError):
            creds = None

    if creds and creds.valid and not interactive:
        return creds

    if creds and creds.refresh_token and not interactive:
        try:
            creds.refresh(Request())
            _save(creds, token_path)           # keep the new access token
            return creds
        except RefreshError as e:
            reason = f"Google sign-in expired or was revoked ({_short(e)})"
    else:
        reason = "no saved Google sign-in" if creds is None else "saved sign-in has no refresh token"

    if not interactive:
        raise AuthRequired(reason)

    _owner_only(credentials_path)
    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
    # access_type=offline + prompt=consent guarantees a refresh token is issued.
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    _save(creds, token_path)
    return creds


def _short(e: Exception) -> str:
    args = getattr(e, "args", ())
    text = args[0] if args and isinstance(args[0], str) else str(e)
    return text.split(":", 1)[0] if text.startswith("invalid_grant") else text[:120]


def get_service(credentials_path: str, token_path: str, interactive: bool = False):
    creds = get_credentials(credentials_path, token_path, interactive)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _notify_reauth(message: str) -> None:
    """Phone push, opt-in only (ONS_PHONE_NOTIFICATIONS=1). Off by default."""
    if os.getenv("ONS_PHONE_NOTIFICATIONS", "0") != "1":
        return
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from notify import send
        send("ONS: Google Calendar needs sign-in", message, priority="high", tags=["calendar"])
    except Exception:
        pass


# ── fetch ─────────────────────────────────────────────────────────────────────

def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def calendar_kind(cal: dict) -> str:
    cid = cal.get("id", "")
    if cal.get("primary"):
        return "primary"
    if cid == BIRTHDAYS_ID:
        return "birthdays"
    if "#holiday@" in cid:
        return "holidays"
    return "other"


def list_calendars(service) -> list[dict]:
    cals, token = [], None
    while True:
        resp = service.calendarList().list(pageToken=token, showHidden=False).execute()
        cals.extend(resp.get("items", []))
        token = resp.get("nextPageToken")
        if not token:
            return cals


def list_events(service, calendar_id: str, start: datetime, end: datetime) -> list[dict]:
    events, token = [], None
    while True:
        resp = service.events().list(
            calendarId=calendar_id, timeMin=iso(start), timeMax=iso(end),
            singleEvents=True, orderBy="startTime", maxResults=2500, pageToken=token,
        ).execute()
        events.extend(resp.get("items", []))
        token = resp.get("nextPageToken")
        if not token:
            return events


@dataclass
class Fetched:
    calendars: list[dict]
    events: dict[str, list[dict]] = field(default_factory=dict)   # calendar id → events


def window(today: date, back: int = DAYS_BACK, ahead: int = DAYS_AHEAD) -> tuple[datetime, datetime]:
    start = datetime.combine(today - timedelta(days=back), datetime.min.time(), TZ)
    end = datetime.combine(today + timedelta(days=ahead + 1), datetime.min.time(), TZ)
    return start, end


def fetch_all(service, today: date, year: int) -> Fetched:
    start, end = window(today)
    y_start = datetime(year, 1, 1, tzinfo=TZ)
    y_end = datetime(year + 1, 1, 1, tzinfo=TZ)
    out = Fetched(calendars=list_calendars(service))
    for cal in out.calendars:
        if calendar_kind(cal) == "primary":
            s, e = min(start, y_start), max(end, y_end)       # the year for metrics + the rolling window
        else:
            s, e = start, end
        out.events[cal["id"]] = list_events(service, cal["id"], s, e)
    return out


# ── shape ─────────────────────────────────────────────────────────────────────

def to_rows(fetched: Fetched, synced_at: datetime) -> list[dict]:
    rows = []
    for cal in fetched.calendars:
        kind = calendar_kind(cal)
        name = cal.get("summaryOverride") or cal.get("summary") or cal["id"]
        for e in fetched.events.get(cal["id"], []):
            if e.get("status") == "cancelled":
                continue
            s, en = e.get("start", {}), e.get("end", {})
            all_day = "date" in s and "dateTime" not in s
            if all_day:
                start_date, start_at, end_at = date.fromisoformat(s["date"]), None, None
            else:
                start_at = datetime.fromisoformat(s["dateTime"]).astimezone(TZ)
                end_at = datetime.fromisoformat(en["dateTime"]).astimezone(TZ) if en.get("dateTime") else None
                start_date = start_at.date()
            event_type = e.get("eventType") or "default"
            rows.append({
                "calendar_id": cal["id"], "calendar_name": name,
                # birthdays now also live on the primary calendar as eventType=birthday
                "calendar_kind": "birthdays" if event_type == "birthday" else kind,
                "event_id": e.get("id"), "title": (e.get("summary") or "").strip(),
                "event_type": event_type, "all_day": all_day, "start_date": start_date,
                "start_at": start_at, "end_at": end_at, "location": e.get("location"),
                "status": e.get("status") or "confirmed", "synced_at": synced_at,
            })
    # the same birthday can come from the Birthdays calendar and the primary one
    seen, unique = set(), []
    for r in rows:
        key = (r["calendar_kind"], r["title"], r["start_date"]) if r["calendar_kind"] == "birthdays" else (r["calendar_id"], r["event_id"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def write_year_csv(fetched: Fetched, year: int, folder: Path) -> Path:
    """Primary calendar, events in `year`, same columns as before (calendar_metrics reads it)."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"events_clean_{year}.csv"
    primary = next((c["id"] for c in fetched.calendars if calendar_kind(c) == "primary"), None)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["start", "end", "all_day", "summary", "description", "location"])
        for e in fetched.events.get(primary, []):
            s, en = e.get("start", {}), e.get("end", {})
            start_val = s.get("dateTime") or s.get("date") or ""
            if not start_val.startswith(str(year)) or e.get("status") == "cancelled":
                continue
            w.writerow([start_val, en.get("dateTime") or en.get("date") or "",
                        "date" in s and "dateTime" not in s, e.get("summary", "") or "",
                        e.get("description", "") or "", e.get("location", "") or ""])
    return path


def write_warehouse(rows: list[dict], path: Path) -> int:
    import duckdb
    import pandas as pd

    df = pd.DataFrame(rows, columns=COLUMNS)
    con = duckdb.connect(str(path))
    try:
        con.register("incoming", df)
        con.execute("BEGIN")
        con.execute("CREATE SCHEMA IF NOT EXISTS calendar")
        con.execute("""
            CREATE OR REPLACE TABLE calendar.events AS
            SELECT CAST(calendar_id AS VARCHAR) AS calendar_id,
                   CAST(calendar_name AS VARCHAR) AS calendar_name,
                   CAST(calendar_kind AS VARCHAR) AS calendar_kind,
                   CAST(event_id AS VARCHAR) AS event_id,
                   CAST(title AS VARCHAR) AS title,
                   CAST(event_type AS VARCHAR) AS event_type,
                   CAST(all_day AS BOOLEAN) AS all_day,
                   CAST(start_date AS DATE) AS start_date,
                   CAST(start_at AS TIMESTAMPTZ) AS start_at,
                   CAST(end_at AS TIMESTAMPTZ) AS end_at,
                   CAST(location AS VARCHAR) AS location,
                   CAST(status AS VARCHAR) AS status,
                   CAST(synced_at AS TIMESTAMPTZ) AS synced_at
            FROM incoming
        """)
        con.execute("COMMIT")
        return con.execute("SELECT count(*) FROM calendar.events").fetchone()[0]
    finally:
        con.close()


# ── status ────────────────────────────────────────────────────────────────────

def write_status(ok: bool, message: str, now: datetime, **extra: Any) -> dict:
    path = status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    status = {"ok": ok, "checked_at": now.isoformat(timespec="seconds"), "message": message, **extra}
    if ok:
        status["last_ok_at"] = status["checked_at"]
    else:
        try:
            status["last_ok_at"] = json.loads(path.read_text()).get("last_ok_at")
        except (OSError, json.JSONDecodeError):
            status["last_ok_at"] = None
    path.write_text(json.dumps(status, indent=2) + "\n")
    return status


def read_status(today: date | None = None) -> dict:
    """What the paper and the secretary show. Missing or not checked today = unavailable."""
    today = today or datetime.now(TZ).date()
    try:
        status = json.loads(status_path().read_text())
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "message": "the calendar has never synced"}
    checked = status.get("checked_at", "")[:10]
    if status.get("ok") and checked != today.isoformat():
        return {**status, "ok": False, "message": f"the calendar hasn't synced since {checked or 'never'}"}
    return status


# ── main ──────────────────────────────────────────────────────────────────────

def run(service_factory: Callable[[], Any], *, today: date, year: int, now: datetime,
        warehouse: Path | None = None) -> int:
    def fail(code: int, reason: str) -> int:
        msg = f"Calendar unavailable today: {reason}."
        write_status(False, msg, now)
        print(f"✗ {msg}" + (f" {REAUTH_HELP}" if code == 2 else ""), file=sys.stderr)
        if code == 2:
            _notify_reauth(f"{msg} {REAUTH_HELP}")
        return code

    try:
        service = service_factory()
    except AuthRequired as e:
        return fail(2, str(e))

    try:
        fetched = fetch_all(service, today, year)
    except Exception as e:                       # HttpError, network: say so, keep yesterday's table
        return fail(1, f"Google Calendar API error ({type(e).__name__}: {str(e)[:160]})")

    raw_dir = data_dir() / "calendar" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw = raw_dir / f"events_{year}_{today:%Y%m%d}.json"
    raw.write_text(json.dumps({"calendars": fetched.calendars, "events": fetched.events}, ensure_ascii=False))
    csv_path = write_year_csv(fetched, year, data_dir() / "calendar" / "processed")

    rows = to_rows(fetched, now)
    try:
        stored = write_warehouse(rows, warehouse or db_path())
    except Exception as e:
        return fail(1, f"couldn't save events to the warehouse ({type(e).__name__}: {str(e)[:160]})")

    names = sorted({f"{r['calendar_name']} ({r['calendar_kind']})" for r in rows} |
                   {f"{c.get('summaryOverride') or c.get('summary')} ({calendar_kind(c)})" for c in fetched.calendars})
    start, end = window(today)
    write_status(True, "ok", now, calendars=len(fetched.calendars), events=stored,
                 window=[start.date().isoformat(), (end.date() - timedelta(days=1)).isoformat()])
    print(f"✓ {len(fetched.calendars)} calendars, {stored} events in calendar.events "
          f"({start.date()} → {end.date() - timedelta(days=1)} + primary {year})")
    for n in names:
        print(f"    {n}")
    print(f"Wrote raw: {raw}\nWrote clean: {csv_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Sync all Google Calendars into ONS.")
    p.add_argument("--year", type=int, default=datetime.now(TZ).year)
    p.add_argument("--auth", action="store_true",
                   help="sign in to Google in a browser (interactive; never used by daily_sync)")
    args = p.parse_args(argv)

    load_dotenv(dotenv_path=ROOT / ".env")
    cred_path = os.getenv("GOOGLE_CALENDAR_CREDENTIALS", str(ROOT / "secrets/google_calendar_credentials.json"))
    token_path = os.getenv("GOOGLE_CALENDAR_TOKEN", str(ROOT / "secrets/google_calendar_token.json"))

    if args.auth:
        try:
            get_service(cred_path, token_path, interactive=True)
        except Exception as e:
            print(f"✗ Sign-in failed: {e}", file=sys.stderr)
            return 2
        print(f"✓ Signed in. Token saved (owner-only) to {token_path}")

    now = datetime.now(TZ)
    return run(lambda: get_service(cred_path, token_path), today=now.date(), year=args.year, now=now)


if __name__ == "__main__":
    raise SystemExit(main())
