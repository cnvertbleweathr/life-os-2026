#!/usr/bin/env python3
"""
nba_stats_pipeline.py

NBA team box scores + an 18-season historical lines bootstrap, for the
NBA ATS model's efficiency features (the NBA analogue of CFB's PPA gap).

Tables produced (schema: nba)
  nba.team_game_logs    -- one row per (game, team) from stats.nba.com
                           LeagueGameLog: shooting, rebounds, TOV, FTA, pts,
                           plus/minus. Possessions / ORtg / DRtg / four
                           factors are derived in dbt, rolled with no lookahead.
  nba.historical_lines  -- 2007-08 through 2025-26 (partial) single line per
                           game (closing, from SBR via kyleskom's
                           NBA-Machine-Learning-Sports-Betting repo): spread,
                           total, moneylines, final margin, days of rest.
                           Spread is stored unsigned before 2022-23, so the
                           sign here is rebuilt from the moneyline favorite.
                           home_spread is negative when home is favored.

Usage
  python pipelines/nba_stats_pipeline.py --season 2008 --end-season 2026
  python pipelines/nba_stats_pipeline.py --lines-bootstrap
  python pipelines/nba_stats_pipeline.py --season 2026              # daily refresh

Season = year the season ends (2025-26 -> 2026).
"""

from __future__ import annotations

import argparse
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import requests

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")

BOOTSTRAP_URL = ("https://raw.githubusercontent.com/kyleskom/"
                 "NBA-Machine-Learning-Sports-Betting/master/Data/OddsData.sqlite")
SEASON_TYPES = ["Regular Season", "Playoffs"]


def season_str(season: int) -> str:
    return f"{season - 1}-{str(season)[2:]}"


def current_season() -> int:
    now = datetime.now()
    return now.year + 1 if now.month >= 9 else now.year


# ---------------------------------------------------------------------------
# Team game logs (stats.nba.com via nba_api)
# ---------------------------------------------------------------------------

def team_game_logs(season: int) -> Iterator[dict]:
    from nba_api.stats.endpoints import leaguegamelog

    for stype in SEASON_TYPES:
        for attempt in range(3):
            try:
                df = leaguegamelog.LeagueGameLog(
                    season=season_str(season),
                    season_type_all_star=stype,
                    player_or_team_abbreviation="T",
                    timeout=60,
                ).get_data_frames()[0]
                break
            except Exception as e:
                if attempt == 2:
                    raise
                print(f"  retry {season} {stype}: {e}")
                time.sleep(10 * (attempt + 1))
        print(f"  {season_str(season)} {stype}: {len(df)} team-games")
        df.columns = [c.lower() for c in df.columns]
        df["season"] = season
        df["season_type"] = stype
        df["is_home"] = ~df["matchup"].str.contains("@")
        df["opp_abbr"] = df["matchup"].str.split(r" vs\. | @ ", regex=True).str[-1]
        df["loaded_at"] = datetime.now(timezone.utc).isoformat()
        df = df.drop(columns=["video_available"], errors="ignore")
        yield from df.to_dict("records")
        time.sleep(1.5)  # stats.nba.com is touchy


# ---------------------------------------------------------------------------
# Historical lines bootstrap
# ---------------------------------------------------------------------------

def _bootstrap_tables(con: sqlite3.Connection) -> list[tuple[str, int]]:
    names = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    out = []
    for start in range(2007, 2040):
        end2 = str(start + 1)[2:]
        for cand in (f"odds_{start}-{end2}_new", f"{start}-{end2}", f"odds_{start}-{end2}"):
            if cand in names:
                out.append((cand, start + 1))
                break
    return out


def historical_lines() -> Iterator[dict]:
    import numpy as np
    import pandas as pd

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "odds.sqlite"
        r = requests.get(BOOTSTRAP_URL, timeout=120)
        r.raise_for_status()
        path.write_bytes(r.content)
        con = sqlite3.connect(path)
        frames = []
        for table, season in _bootstrap_tables(con):
            df = pd.read_sql(f'select * from "{table}"', con)
            df["season"] = season
            frames.append(df)
        con.close()

    d = pd.concat(frames, ignore_index=True)
    num = ["OU", "Spread", "ML_Home", "ML_Away", "Points", "Win_Margin",
           "Days_Rest_Home", "Days_Rest_Away"]
    for c in num:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["Spread", "ML_Home", "ML_Away"])
    d = d[d.ML_Home != d.ML_Away]
    # unsigned before 2022-23 -> sign from moneyline; home favored => negative home_spread
    home_fav = d.ML_Home < d.ML_Away
    d["home_spread"] = np.where(home_fav, -d.Spread.abs(), d.Spread.abs())
    d = d[d.home_spread.abs() < 30]
    out = pd.DataFrame({
        "season": d.season,
        "game_date": d.Date.astype(str).str[:10],
        "home_team": d.Home, "away_team": d.Away,
        "home_spread": d.home_spread,
        "total": d.OU,
        "home_ml": d.ML_Home, "away_ml": d.ML_Away,
        "total_points": d.Points,
        "home_margin": d.Win_Margin,
        "home_days_rest": d.Days_Rest_Home, "away_days_rest": d.Days_Rest_Away,
        "source": "sbr_via_kyleskom",
    })
    out["home_ats_margin"] = out.home_margin + out.home_spread  # >0 home covered
    out["loaded_at"] = datetime.now(timezone.utc).isoformat()
    print(f"  historical_lines: {len(out)} games, seasons {out.season.min()}-{out.season.max()}")
    yield from out.astype(object).where(out.notna(), None).to_dict("records")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def run(seasons: list[int], bootstrap: bool) -> None:
    import dlt

    pipeline = dlt.pipeline(
        pipeline_name="nba_stats",
        destination=dlt.destinations.duckdb(DB_PATH),
        dataset_name="nba",
    )
    resources = []
    if seasons:
        @dlt.resource(name="team_game_logs", write_disposition="merge",
                      primary_key=["game_id", "team_id"])
        def logs() -> Iterator[dict]:
            for s in seasons:
                yield from team_game_logs(s)
        resources.append(logs())
    if bootstrap:
        @dlt.resource(name="historical_lines", write_disposition="merge",
                      primary_key=["game_date", "home_team", "away_team"])
        def lines() -> Iterator[dict]:
            yield from historical_lines()
        resources.append(lines())
    print(pipeline.run(resources))


def main() -> None:
    p = argparse.ArgumentParser(description="NBA team box scores + historical lines -> DuckDB")
    p.add_argument("--season", type=int, help="season end year (2025-26 -> 2026)")
    p.add_argument("--end-season", type=int)
    p.add_argument("--lines-bootstrap", action="store_true",
                   help="load 2007-08 -> present historical closing lines")
    a = p.parse_args()
    seasons = []
    if a.season:
        seasons = list(range(a.season, (a.end_season or a.season) + 1))
    if not seasons and not a.lines_bootstrap:
        seasons = [current_season()]
    run(seasons, a.lines_bootstrap)


if __name__ == "__main__":
    main()
