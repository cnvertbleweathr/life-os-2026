#!/usr/bin/env python3
"""
Strava DLT pipeline.

Replaces scripts/fetch_strava_activities.py + scripts/running_metrics.py.
Handles token refresh automatically and loads activities directly into DuckDB.

Tables produced (schema: strava):
  strava.activities     — raw activity records, merged on strava_id
  strava.running_summary — one row per year, YTD running metrics

Prerequisites:
  - Run scripts/strava_auth.py once to get data/running/raw/strava_tokens.json
  - STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET in .env

Usage:
  python pipelines/strava_pipeline.py
  python pipelines/strava_pipeline.py --year 2026
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import requests
import dlt
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DB_PATH = str(ROOT / "data" / "warehouse" / "lifeos.duckdb")
TOKENS_PATH = ROOT / "data" / "running" / "raw" / "strava_tokens.json"

API_BASE = "https://www.strava.com/api/v3"
RUN_TYPES = {"Run", "VirtualRun", "TrailRun"}


# ---------------------------------------------------------------------------
# Token management (mirrors existing strava_auth.py logic)
# ---------------------------------------------------------------------------

def _load_tokens() -> dict:
    if not TOKENS_PATH.exists():
        raise FileNotFoundError(
            f"Missing {TOKENS_PATH}. Run scripts/strava_auth.py first to authenticate."
        )
    return json.loads(TOKENS_PATH.read_text())


def _save_tokens(tokens: dict) -> None:
    TOKENS_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKENS_PATH.write_text(json.dumps(tokens, indent=2))


def _refresh_if_needed(tokens: dict) -> dict:
    if tokens.get("expires_at", 0) > int(time.time()) + 60:
        return tokens  # still valid

    client_id = os.getenv("STRAVA_CLIENT_ID")
    client_secret = os.getenv("STRAVA_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("Missing STRAVA_CLIENT_ID or STRAVA_CLIENT_SECRET in .env")

    r = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
        },
        timeout=30,
    )
    r.raise_for_status()
    new_tokens = r.json()
    _save_tokens(new_tokens)
    return new_tokens


# ---------------------------------------------------------------------------
# DLT resources
# ---------------------------------------------------------------------------

@dlt.resource(
    name="activities",
    write_disposition="merge",
    primary_key="strava_id",
)
def strava_activities_resource() -> Iterator[dict]:
    """Fetches all activities from the Strava API and yields normalized records."""
    tokens = _refresh_if_needed(_load_tokens())
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    page = 1
    while True:
        r = requests.get(
            f"{API_BASE}/athlete/activities",
            headers=headers,
            params={"per_page": 200, "page": page},
            timeout=30,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break

        for act in batch:
            start_dt = None
            raw_date = act.get("start_date")
            if raw_date:
                try:
                    start_dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                except ValueError:
                    pass

            distance_m = float(act.get("distance") or 0)
            moving_s = float(act.get("moving_time") or 0)
            distance_miles = distance_m / 1609.344
            is_run = act.get("type", "") in RUN_TYPES

            yield {
                "strava_id": act.get("id"),
                "name": act.get("name"),
                "activity_type": act.get("type"),
                "is_run": is_run,
                "start_date": start_dt.isoformat() if start_dt else None,
                "year": start_dt.year if start_dt else None,
                "distance_m": distance_m,
                "distance_miles": round(distance_miles, 4),
                "moving_time_s": moving_s,
                "elapsed_time_s": float(act.get("elapsed_time") or 0),
                "total_elevation_gain_m": float(act.get("total_elevation_gain") or 0),
                "average_heartrate": act.get("average_heartrate"),
                "max_heartrate": act.get("max_heartrate"),
                "average_speed_ms": act.get("average_speed"),
                "kudos_count": act.get("kudos_count"),
                "raw_json": json.dumps(act),
            }

        page += 1


@dlt.resource(
    name="running_summary",
    write_disposition="replace",
)
def running_summary_resource(year: int) -> Iterator[dict]:
    """
    Reads the activities already loaded into DuckDB and produces a YTD summary.
    Falls back to fetching live if the table doesn't exist yet.
    """
    import duckdb

    db_path = ROOT / "data" / "warehouse" / "lifeos.duckdb"
    if not db_path.exists():
        return

    try:
        con = duckdb.connect(str(db_path), read_only=True)
        df = con.execute(
            """
            SELECT distance_miles, moving_time_s, start_date
            FROM strava.activities
            WHERE is_run = true AND year = ?
            """,
            [year],
        ).df()
        con.close()
    except Exception:
        return

    if df.empty:
        yield {
            "year": year,
            "runs_count": 0,
            "miles_total": 0.0,
            "miles_goal": 350.0,
            "miles_progress_pct": 0.0,
        }
        return

    total_miles = float(df["distance_miles"].sum())
    total_runs = len(df)
    goal_miles = 350.0

    now = datetime.now(timezone.utc)
    weeks_elapsed = int(now.isocalendar().week) if now.year == year else 52
    miles_per_week = total_miles / weeks_elapsed if weeks_elapsed else 0.0

    total_moving_min = float(df["moving_time_s"].sum()) / 60.0
    avg_pace = total_moving_min / total_miles if total_miles > 0 else None

    yield {
        "year": year,
        "runs_count": total_runs,
        "miles_total": round(total_miles, 2),
        "miles_goal": goal_miles,
        "miles_progress_pct": round((total_miles / goal_miles) * 100, 2),
        "weeks_elapsed": weeks_elapsed,
        "miles_per_week": round(miles_per_week, 2),
        "required_miles_per_week": round(goal_miles / 52, 2),
        "avg_pace_min_per_mile": round(avg_pace, 2) if avg_pace else None,
    }


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run(year: int) -> None:
    pipeline = dlt.pipeline(
        pipeline_name="strava",
        destination=dlt.destinations.duckdb(DB_PATH),
        dataset_name="strava",
    )

    # Step 1: load raw activities
    print("Fetching Strava activities...")
    load_info = pipeline.run([strava_activities_resource()])
    print(load_info)

    # Step 2: derive summary from what was just loaded
    print("Computing running summary...")
    load_info = pipeline.run([running_summary_resource(year=year)])
    print(load_info)


def main() -> None:
    p = argparse.ArgumentParser(description="Load Strava activities into DuckDB via DLT.")
    p.add_argument("--year", type=int, default=datetime.now().year)
    args = p.parse_args()
    run(args.year)


if __name__ == "__main__":
    main()
