#!/usr/bin/env python3
"""
nhl_stats_pipeline.py

NHL team-game process stats + starting goalies, for the NHL puck-line /
moneyline model's efficiency features.

Tables produced (schema: nhl)
  nhl.moneypuck_team_games -- MoneyPuck game-by-game team stats, 2008-09 on,
                              one row per (gameId, team, situation) for
                              situations all / 5on5 / 5on4 / 4on5: xGoals,
                              Corsi, Fenwick, high-danger chances, goals,
                              shots, etc. MoneyPuck data is free for
                              non-commercial use -- credit MoneyPuck.com.
  nhl.goalie_games         -- one row per (game, goalie) from the NHL API
                              boxscore: starter flag, TOI, shots against,
                              saves, goals against, decision. Goalie starts
                              are the single biggest NHL pricing lever.

MoneyPuck `season` is the start year (2024-25 -> 2024). The `season_end`
column added here matches the ESPN / NBA convention (2024-25 -> 2025).

Usage
  python pipelines/nhl_stats_pipeline.py --season 2022 --end-season 2026          # MoneyPuck only
  python pipelines/nhl_stats_pipeline.py --season 2022 --end-season 2026 --goalies
  python pipelines/nhl_stats_pipeline.py --goalies                                # current season
"""

from __future__ import annotations

import argparse
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import requests

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")
CACHE = ROOT / "data" / "raw" / "nhl" / "boxscore"

MONEYPUCK_ALL_TEAMS = ("https://moneypuck.com/moneypuck/playerData/careers/"
                       "gameByGame/all_teams.csv")
NHL_BOXSCORE = "https://api-web.nhle.com/v1/gamecenter/{gid}/boxscore"
SITUATIONS = {"all", "5on5", "5on4", "4on5"}
UA = {"User-Agent": "ons/1.0 (personal analytics)"}


def current_season() -> int:
    now = datetime.now()
    return now.year + 1 if now.month >= 9 else now.year


# ---------------------------------------------------------------------------
# MoneyPuck
# ---------------------------------------------------------------------------

def moneypuck_frame(seasons: list[int]):
    import pandas as pd

    print("  downloading MoneyPuck all_teams.csv (large, ~1-2 min)...")
    r = requests.get(MONEYPUCK_ALL_TEAMS, headers=UA, timeout=600)
    r.raise_for_status()
    df = pd.read_csv(io.BytesIO(r.content), low_memory=False)
    df.columns = [c.lower() for c in df.columns]
    df["season_end"] = df["season"].astype(int) + 1
    df = df[df["situation"].isin(SITUATIONS) & df["season_end"].isin(seasons)]
    df["gameid"] = df["gameid"].astype("int64").astype(str)
    df["game_date"] = pd.to_datetime(df["gamedate"].astype(str), format="%Y%m%d").dt.date.astype(str)
    df["loaded_at"] = datetime.now(timezone.utc).isoformat()
    print(f"  MoneyPuck: {len(df)} team-game-situation rows for seasons {min(seasons)}-{max(seasons)}")
    return df


def moneypuck_rows(df) -> Iterator[dict]:
    yield from df.astype(object).where(df.notna(), None).to_dict("records")


# ---------------------------------------------------------------------------
# Goalies (NHL API boxscores)
# ---------------------------------------------------------------------------

def _boxscore(gid: str) -> dict | None:
    p = CACHE / f"{gid}.json"
    if p.exists():
        return json.loads(p.read_text())
    for attempt in range(3):
        try:
            r = requests.get(NHL_BOXSCORE.format(gid=gid), headers=UA, timeout=30)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            data = r.json()
            if data.get("gameState") in ("OFF", "FINAL"):
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(data))
            return data
        except requests.RequestException:
            time.sleep(3 * (attempt + 1))
    return None


def goalie_rows(game_ids: list[str]) -> Iterator[dict]:
    def one(gid: str) -> list[dict]:
        b = _boxscore(gid)
        if not b:
            return []
        rows = []
        for side in ("homeTeam", "awayTeam"):
            team = (b.get(side) or {}).get("abbrev")
            opp = (b.get("awayTeam" if side == "homeTeam" else "homeTeam") or {}).get("abbrev")
            goalies = ((b.get("playerByGameStats") or {}).get(side) or {}).get("goalies", [])
            for g in goalies:
                rows.append({
                    "game_id": gid,
                    "game_date": b.get("gameDate"),
                    "team": team, "opponent": opp, "is_home": side == "homeTeam",
                    "player_id": g.get("playerId"),
                    "name": (g.get("name") or {}).get("default"),
                    "starter": g.get("starter"),
                    "toi": g.get("toi"),
                    "shots_against": g.get("shotsAgainst"),
                    "saves": g.get("saves"),
                    "goals_against": g.get("goalsAgainst"),
                    "save_pct": g.get("savePctg"),
                    "decision": g.get("decision"),
                    "loaded_at": datetime.now(timezone.utc).isoformat(),
                })
        return rows

    with ThreadPoolExecutor(6) as ex:
        for i, rows in enumerate(ex.map(one, game_ids)):
            yield from rows
            if i and i % 500 == 0:
                print(f"    goalies: {i}/{len(game_ids)} games")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def run(seasons: list[int], goalies: bool) -> None:
    import dlt

    df = moneypuck_frame(seasons)
    pipeline = dlt.pipeline(
        pipeline_name="nhl_stats",
        destination=dlt.destinations.duckdb(DB_PATH),
        dataset_name="nhl",
    )

    @dlt.resource(name="moneypuck_team_games", write_disposition="merge",
                  primary_key=["gameid", "playerteam", "situation"])
    def mp() -> Iterator[dict]:
        yield from moneypuck_rows(df)

    resources = [mp()]
    if goalies:
        game_ids = sorted(df["gameid"].unique().tolist())
        print(f"  goalies: {len(game_ids)} games (cached boxscores reused)")

        @dlt.resource(name="goalie_games", write_disposition="merge",
                      primary_key=["game_id", "player_id"])
        def gg() -> Iterator[dict]:
            yield from goalie_rows(game_ids)
        resources.append(gg())

    print(pipeline.run(resources))


def main() -> None:
    p = argparse.ArgumentParser(description="NHL MoneyPuck team stats + goalie starts -> DuckDB")
    p.add_argument("--season", type=int, help="season end year (2025-26 -> 2026)")
    p.add_argument("--end-season", type=int)
    p.add_argument("--goalies", action="store_true", help="also load starting goalies (NHL API)")
    a = p.parse_args()
    start = a.season or current_season()
    run(list(range(start, (a.end_season or start) + 1)), a.goalies)


if __name__ == "__main__":
    main()
