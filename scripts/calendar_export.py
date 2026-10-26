#!/usr/bin/env python3
"""
calendar_export.py — export Google Calendar events for a year.

Auth:
  - Normal runs (daily_sync, 9am) never open a browser. An expired access
    token is refreshed silently with the saved refresh token.
  - If Google needs you to sign in again (no token, or the refresh token was
    revoked/expired), the script exits 2 straight away with instructions and
    an ntfy push, instead of waiting for a browser login that nobody sees —
    which used to stall the whole daily sync.
  - Sign in by hand once with:  python scripts/calendar_export.py --auth
    (at the Mac mini or over Screen Sharing; it opens a browser).

If you're asked to sign in about once a week, the Google Cloud OAuth app is
in "Testing" mode, where refresh tokens expire after 7 days. Publish it
(Google Cloud Console → Google Auth Platform → Audience → Publish app).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

load_dotenv(dotenv_path=".env")

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]  # read-only is enough
REAUTH_HELP = "Run once at the Mac mini: python scripts/calendar_export.py --auth"


class AuthRequired(RuntimeError):
    """Google needs an interactive sign-in; never attempted unattended."""


def _save(creds: Credentials, token_path: str) -> None:
    os.makedirs(os.path.dirname(token_path) or ".", exist_ok=True)
    with open(token_path, "w") as f:
        f.write(creds.to_json())


def get_credentials(credentials_path: str, token_path: str, interactive: bool = False) -> Credentials:
    creds = None
    if os.path.exists(token_path):
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
            reason = f"refresh token rejected by Google ({e})"
    else:
        reason = "no saved token" if creds is None else "saved token has no refresh token"

    if not interactive:
        raise AuthRequired(f"Google Calendar needs you to sign in again: {reason}. {REAUTH_HELP}")

    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
    # access_type=offline + prompt=consent guarantees a refresh token is issued.
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    _save(creds, token_path)
    return creds


def get_service(credentials_path: str, token_path: str, interactive: bool = False):
    creds = get_credentials(credentials_path, token_path, interactive)
    return build("calendar", "v3", credentials=creds)


def _notify_reauth(message: str) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from notify import send
        send("ONS: Google Calendar needs sign-in", message, priority="high", tags=["calendar"])
    except Exception:
        pass

def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int, default=datetime.now().year)
    p.add_argument("--auth", action="store_true",
                   help="sign in to Google in a browser (interactive; never used by daily_sync)")
    args = p.parse_args()

    cal_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")
    cred_path = os.getenv("GOOGLE_CALENDAR_CREDENTIALS", "secrets/google_calendar_credentials.json")
    token_path = os.getenv("GOOGLE_CALENDAR_TOKEN", "secrets/google_calendar_token.json")

    try:
        service = get_service(cred_path, token_path, interactive=args.auth)
    except AuthRequired as e:
        print(f"✗ {e}", file=sys.stderr)
        _notify_reauth(str(e))
        return 2
    if args.auth:
        print(f"✓ Signed in. Token saved to {token_path}")

    start = datetime(args.year, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(args.year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    # Uses Events.list endpoint with timeMin/timeMax paging. :contentReference[oaicite:2]{index=2}
    events = []
    page_token = None
    while True:
        resp = service.events().list(
            calendarId=cal_id,
            timeMin=iso(start),
            timeMax=iso(end),
            singleEvents=True,
            orderBy="startTime",
            maxResults=2500,
            pageToken=page_token,
        ).execute()
        events.extend(resp.get("items", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    os.makedirs("data/calendar/raw", exist_ok=True)
    os.makedirs("data/calendar/processed", exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d")
    raw_path = f"data/calendar/raw/events_{args.year}_{ts}.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)

    clean_path = f"data/calendar/processed/events_clean_{args.year}.csv"
    with open(clean_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["start", "end", "all_day", "summary", "description", "location"])
        for e in events:
            summary = e.get("summary", "") or ""
            description = e.get("description", "") or ""
            location = e.get("location", "") or ""

            start_obj = e.get("start", {})
            end_obj = e.get("end", {})

            # all-day events use "date"; timed use "dateTime"
            all_day = "date" in start_obj and "dateTime" not in start_obj
            start_val = start_obj.get("dateTime") or start_obj.get("date") or ""
            end_val = end_obj.get("dateTime") or end_obj.get("date") or ""

            w.writerow([start_val, end_val, all_day, summary, description, location])

    print(f"Fetched events: {len(events)}")
    print(f"Wrote raw: {raw_path}")
    print(f"Wrote clean: {clean_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

