#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

load_dotenv(dotenv_path=".env")

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]  # read-only is enough

def get_service(credentials_path: str, token_path: str):
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
        creds = flow.run_local_server(port=0)
        os.makedirs(os.path.dirname(token_path), exist_ok=True)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)

def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int, default=2026)
    args = p.parse_args()

    cal_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")
    cred_path = os.getenv("GOOGLE_CALENDAR_CREDENTIALS", "secrets/google_calendar_credentials.json")
    token_path = os.getenv("GOOGLE_CALENDAR_TOKEN", "secrets/google_calendar_token.json")

    service = get_service(cred_path, token_path)

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

if __name__ == "__main__":
    main()

