#!/usr/bin/env python3
"""
track_lines.py

Fetches current week's CFB betting lines from CFBD API and appends a
timestamped snapshot to cfbd.line_history in DuckDB.

Run daily Sunday–Saturday during CFB season (Aug–Jan).
Off-season: exits cleanly.

The first pull of the week (Sunday) is tagged line_type='open'.
Subsequent pulls are tagged line_type='current'.
Saturday pulls are tagged line_type='close'.

This builds a time-series that enables line movement analysis:
  spread_movement = close_spread - open_spread
  sharp signal    = movement against public consensus

Usage:
  python scripts/track_lines.py              # current week
  python scripts/track_lines.py --week 3 --year 2026
  python scripts/track_lines.py --dry-run    # print without writing
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb
import requests
from dotenv import load_dotenv

ROOT    = Path(__file__).resolve().parents[1]
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")
load_dotenv(ROOT / ".env")

API_BASE   = "https://api.collegefootballdata.com"
CFBD_TOKEN = os.getenv("CFBD_API_TOKEN", "")

# Preferred providers — consensus first, then major books
PREFERRED_PROVIDERS = [
    "consensus", "DraftKings", "ESPN Bet", "Bovada",
    "FanDuel", "BetMGM", "Caesars",
]


def cfbd_get(endpoint: str, params: dict) -> list[dict]:
    if not CFBD_TOKEN:
        print("⚠️  CFBD_API_TOKEN not set", file=sys.stderr)
        return []
    try:
        r = requests.get(
            f"{API_BASE}{endpoint}",
            headers={"Authorization": f"Bearer {CFBD_TOKEN}"},
            params=params,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"CFBD API error: {e}", file=sys.stderr)
        return []


def current_cfb_week(year: int) -> int | None:
    today = date.today()
    if today.month in (2, 3, 4, 5, 6, 7):
        return None
    season_start = date(year, 8, 24)
    delta = (today - season_start).days
    if delta < 0:
        return None
    return min(delta // 7 + 1, 15)


def line_type_for_today() -> str:
    """Classify today's pull by day of week."""
    dow = date.today().weekday()  # 0=Mon, 6=Sun
    if dow == 6:  return "open"    # Sunday — opening lines
    if dow == 5:  return "close"   # Saturday — closing lines
    return "current"


def ensure_table(con: duckdb.DuckDBPyConnection) -> None:
    """Create cfbd.line_history if it doesn't exist."""
    con.execute("CREATE SCHEMA IF NOT EXISTS cfbd")
    con.execute("""
        CREATE TABLE IF NOT EXISTS cfbd.line_history (
            -- Identity
            game_id         BIGINT,
            season          INTEGER,
            week            INTEGER,
            home_team       VARCHAR,
            away_team       VARCHAR,
            home_conference VARCHAR,
            away_conference VARCHAR,

            -- Provider
            provider        VARCHAR,

            -- Line snapshot
            spread          DOUBLE,
            over_under      DOUBLE,
            home_moneyline  INTEGER,
            away_moneyline  INTEGER,

            -- Opening line (from API — available all week)
            spread_open     DOUBLE,
            over_under_open DOUBLE,

            -- Movement vs open (computed at insert time)
            spread_movement DOUBLE,   -- spread - spread_open (negative = moved toward home)
            ou_movement     DOUBLE,   -- over_under - over_under_open

            -- Snapshot metadata
            line_type       VARCHAR,  -- 'open' | 'current' | 'close'
            snapshot_date   DATE,
            snapshot_ts     TIMESTAMP,
            day_of_week     INTEGER,  -- 0=Mon, 6=Sun

            -- Primary key: one row per game × provider × day
            PRIMARY KEY (game_id, provider, snapshot_date)
        )
    """)


def fetch_and_store(
    year: int,
    week: int,
    dry_run: bool = False,
) -> int:
    """Fetch lines for the given week and upsert into cfbd.line_history."""

    raw = cfbd_get("/lines", {"year": year, "week": week, "seasonType": "regular"})
    if not raw:
        print(f"No lines returned from CFBD for {year} Week {week}")
        return 0

    now       = datetime.now(timezone.utc)
    today     = date.today()
    dow       = today.weekday()
    ltype     = line_type_for_today()
    rows      = []

    for game in raw:
        game_id  = game.get("id")
        home     = game.get("homeTeam")
        away     = game.get("awayTeam")
        home_c   = game.get("homeConference", "")
        away_c   = game.get("awayConference", "")
        gweek    = game.get("week", week)
        lines    = game.get("lines") or []

        if not game_id or not home or not away:
            continue

        # Pick best available provider in priority order
        provider_map: dict[str, dict] = {
            l.get("provider", "unknown"): l for l in lines if l.get("spread") is not None
        }

        for provider_name in PREFERRED_PROVIDERS + list(provider_map.keys()):
            line = provider_map.get(provider_name)
            if not line:
                continue

            spread    = _to_float(line.get("spread"))
            ou        = _to_float(line.get("overUnder"))
            sp_open   = _to_float(line.get("spreadOpen"))
            ou_open   = _to_float(line.get("overUnderOpen"))
            home_ml   = _to_int(line.get("homeMoneyline"))
            away_ml   = _to_int(line.get("awayMoneyline"))

            if spread is None:
                continue

            sp_move = round(spread - sp_open, 1) if spread is not None and sp_open is not None else None
            ou_move = round(ou - ou_open, 1)     if ou     is not None and ou_open is not None else None

            rows.append({
                "game_id":         game_id,
                "season":          year,
                "week":            gweek,
                "home_team":       home,
                "away_team":       away,
                "home_conference": home_c,
                "away_conference": away_c,
                "provider":        provider_name,
                "spread":          spread,
                "over_under":      ou,
                "home_moneyline":  home_ml,
                "away_moneyline":  away_ml,
                "spread_open":     sp_open,
                "over_under_open": ou_open,
                "spread_movement": sp_move,
                "ou_movement":     ou_move,
                "line_type":       ltype,
                "snapshot_date":   today.isoformat(),
                "snapshot_ts":     now.isoformat(),
                "day_of_week":     dow,
            })

        # One row per game is enough for our purposes — take the first valid one
        # (already filtered by preferred_providers above)

    if dry_run:
        print(f"\nDRY RUN — would insert/update {len(rows)} line snapshots")
        for r in rows[:5]:
            print(f"  {r['away_team']} @ {r['home_team']} | "
                  f"spread={r['spread']} (open={r['spread_open']}, "
                  f"move={r['spread_movement']}) | "
                  f"O/U={r['over_under']} | {r['provider']} | {r['line_type']}")
        if len(rows) > 5:
            print(f"  ... and {len(rows) - 5} more")
        return len(rows)

    # Write to DuckDB
    try:
        con = duckdb.connect(DB_PATH)
        ensure_table(con)

        import pandas as pd
        df = pd.DataFrame(rows)

        # Upsert: delete existing rows for same game/provider/date, then insert
        if not df.empty:
            game_ids = df["game_id"].unique().tolist()
            ids_str  = ",".join(str(g) for g in game_ids)
            con.execute(f"""
                DELETE FROM cfbd.line_history
                WHERE game_id IN ({ids_str})
                  AND snapshot_date = '{today.isoformat()}'
            """)
            con.execute("INSERT INTO cfbd.line_history SELECT * FROM df")

        row_count = len(df)
        con.close()
        print(f"✓ Stored {row_count} line snapshots ({ltype}) for {year} Week {week}")
        return row_count

    except Exception as e:
        print(f"DuckDB error: {e}", file=sys.stderr)
        return 0


def _to_float(val) -> float | None:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _to_int(val) -> int | None:
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def main() -> int:
    p = argparse.ArgumentParser(description="Track CFB line movement throughout the week")
    p.add_argument("--year",    type=int, default=date.today().year)
    p.add_argument("--week",    type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    year = args.year
    week = args.week or current_cfb_week(year)

    if week is None:
        print(f"Off-season ({date.today()}) — no lines to track")
        return 0

    print(f"📊 Tracking lines — {year} Week {week} ({line_type_for_today()} snapshot)")
    fetch_and_store(year, week, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
