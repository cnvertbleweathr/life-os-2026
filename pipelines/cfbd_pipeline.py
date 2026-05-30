#!/usr/bin/env python3
"""
cfbd_pipeline.py

DLT pipeline for College Football Data API.
Pulls betting lines, game results, advanced box scores, and SP+ ratings
into DuckDB for analysis.

Tables produced (schema: cfbd):
  cfbd.games              — game results (scores, teams, week, season)
  cfbd.lines              — betting lines merged with actual results
  cfbd.advanced_box_scores — EPA, success rate, efficiency metrics
  cfbd.sp_ratings         — SP+ pregame ratings per team per season

Usage:
  python pipelines/cfbd_pipeline.py --year 2024
  python pipelines/cfbd_pipeline.py --year 2021 --end-year 2025  # historical pull
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Iterator

import requests
import dlt
from dotenv import load_dotenv

ROOT    = Path(__file__).resolve().parents[1]
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")
load_dotenv(ROOT / ".env")

API_BASE = "https://api.collegefootballdata.com"
CFBD_TOKEN = os.getenv("CFBD_API_TOKEN", "")

SEASON_TYPES = ["regular", "postseason"]


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def cfbd_get(endpoint: str, params: dict = None, retries: int = 3) -> list | dict:
    if not CFBD_TOKEN:
        raise RuntimeError("Missing CFBD_API_TOKEN in .env")

    headers = {"Authorization": f"Bearer {CFBD_TOKEN}"}
    url = f"{API_BASE}{endpoint}"

    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, params=params or {}, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.HTTPError as e:
            if r.status_code == 429:
                wait = 60 * (attempt + 1)
                print(f"  Rate limited — waiting {wait}s...")
                time.sleep(wait)
            else:
                raise
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(5)
    return []


# ---------------------------------------------------------------------------
# DLT resources
# ---------------------------------------------------------------------------

@dlt.resource(
    name="games",
    write_disposition="merge",
    primary_key="game_id",
)
def games_resource(year: int) -> Iterator[dict]:
    """Fetch all FBS game results for a season."""
    for season_type in SEASON_TYPES:
        data = cfbd_get("/games", {
            "year": year,
            "seasonType": season_type,
            "division": "fbs",
        })
        for g in data:
            yield {
                "game_id":          g.get("id"),
                "season":           g.get("season"),
                "week":             g.get("week"),
                "season_type":      g.get("seasonType"),
                "start_date":       g.get("startDate"),
                "neutral_site":     g.get("neutralSite"),
                "conference_game":  g.get("conferenceGame"),
                "home_team":        g.get("homeTeam"),
                "home_conference":  g.get("homeConference"),
                "home_points":      g.get("homePoints"),
                "home_pregame_elo": g.get("homePregameElo"),
                "away_team":        g.get("awayTeam"),
                "away_conference":  g.get("awayConference"),
                "away_points":      g.get("awayPoints"),
                "away_pregame_elo": g.get("awayPregameElo"),
                "excitement_index": g.get("excitementIndex"),
            }


@dlt.resource(
    name="lines",
    write_disposition="merge",
    primary_key=["game_id", "provider"],
)
def lines_resource(year: int) -> Iterator[dict]:
    """Fetch betting lines merged with game results."""
    for season_type in SEASON_TYPES:
        data = cfbd_get("/lines", {
            "year": year,
            "seasonType": season_type,
        })
        for game in data:
            game_id     = game.get("id")
            home_team   = game.get("homeTeam")
            away_team   = game.get("awayTeam")
            home_score  = game.get("homeScore")
            away_score  = game.get("awayScore")
            week        = game.get("week")
            season_type_val = game.get("season_type", season_type)

            # Actual result calculations
            total_points = None
            actual_margin = None
            home_win = None
            if home_score is not None and away_score is not None:
                total_points  = home_score + away_score
                actual_margin = home_score - away_score  # positive = home team won by this
                home_win      = home_score > away_score

            for line in (game.get("lines") or []):
                spread     = line.get("spread")
                over_under = line.get("overUnder")

                # Spread accuracy: negative spread = home favored
                spread_covered = None
                spread_push    = None
                if spread is not None and actual_margin is not None:
                    try:
                        s = float(spread)
                        # Home team covers if actual_margin > -spread (home perspective)
                        if s + actual_margin == 0:
                            spread_push = True
                            spread_covered = None
                        else:
                            spread_push = False
                            spread_covered = actual_margin > -s
                    except (ValueError, TypeError):
                        pass

                # Over/under accuracy
                ou_result = None
                ou_push   = None
                if over_under is not None and total_points is not None:
                    try:
                        ou = float(over_under)
                        if total_points == ou:
                            ou_push   = True
                            ou_result = None
                        else:
                            ou_push   = False
                            ou_result = "over" if total_points > ou else "under"
                    except (ValueError, TypeError):
                        pass

                yield {
                    "game_id":           game_id,
                    "season":            year,
                    "week":              week,
                    "season_type":       season_type_val,
                    "home_team":         home_team,
                    "away_team":         away_team,
                    "home_score":        home_score,
                    "away_score":        away_score,
                    "total_points":      total_points,
                    "actual_margin":     actual_margin,
                    "home_win":          home_win,
                    "provider":          line.get("provider"),
                    "spread":            spread,
                    "spread_open":       line.get("spreadOpen"),
                    "over_under":        over_under,
                    "over_under_open":   line.get("overUnderOpen"),
                    "home_moneyline":    line.get("homeMoneyline"),
                    "away_moneyline":    line.get("awayMoneyline"),
                    "spread_covered":    spread_covered,
                    "spread_push":       spread_push,
                    "ou_result":         ou_result,
                    "ou_push":           ou_push,
                }


@dlt.resource(
    name="advanced_box_scores",
    write_disposition="merge",
    primary_key=["game_id", "team"],
)
def advanced_box_scores_resource(year: int) -> Iterator[dict]:
    """
    Fetch advanced box score metrics per game per team.
    These are the key factors for understanding WHY lines hit or miss:
    EPA, success rate, explosiveness, rushing/passing efficiency.
    """
    # Get game IDs first
    games = cfbd_get("/games", {
        "year": year,
        "seasonType": "regular",
        "division": "fbs",
    })

    for game in games:
        game_id = game.get("id")
        if not game_id:
            continue
        try:
            data = cfbd_get("/game/box/advanced", {"gameId": game_id})
            if not data:
                continue

            for team_key in ["homeTeam", "awayTeam"]:
                team_data = data.get(team_key, {})
                if not team_data:
                    continue

                team_name = (
                    game.get("homeTeam") if team_key == "homeTeam"
                    else game.get("awayTeam")
                )
                is_home = team_key == "homeTeam"

                # Flatten the nested structure
                offense = team_data.get("offense", {}) or {}
                defense = team_data.get("defense", {}) or {}

                yield {
                    "game_id":                  game_id,
                    "season":                   year,
                    "team":                     team_name,
                    "is_home":                  is_home,

                    # Offensive EPA
                    "off_epa_per_play":          offense.get("epaPerPlay"),
                    "off_epa_per_rush":          offense.get("epaPerRush"),
                    "off_epa_per_pass":          offense.get("epaPerPass"),
                    "off_success_rate":          offense.get("successRate"),
                    "off_explosiveness":         offense.get("explosiveness"),
                    "off_total_yards":           offense.get("totalYards"),
                    "off_rushing_yards":         offense.get("rushingYards"),
                    "off_passing_yards":         offense.get("passingYards"),

                    # Defensive EPA (opponent offense)
                    "def_epa_per_play":          defense.get("epaPerPlay"),
                    "def_success_rate":          defense.get("successRate"),
                    "def_explosiveness":         defense.get("explosiveness"),

                    # Turnovers
                    "turnovers":                 team_data.get("turnovers"),
                    "fumbles_lost":              team_data.get("fumblesLost"),
                    "interceptions_thrown":      team_data.get("interceptionsThrown"),
                }
            time.sleep(0.2)  # be polite to the API
        except Exception as e:
            print(f"  Warning: advanced box score failed for game {game_id}: {e}")
            continue


@dlt.resource(
    name="sp_ratings",
    write_disposition="merge",
    primary_key=["season", "team"],
)
def sp_ratings_resource(year: int) -> Iterator[dict]:
    """
    SP+ ratings — the gold standard predictive metric in CFB.
    Critical for understanding if the line reflects true team quality.
    """
    data = cfbd_get("/ratings/sp", {"year": year})
    for r in data:
        yield {
            "season":          year,
            "team":            r.get("team"),
            "conference":      r.get("conference"),
            "rating":          r.get("rating"),
            "offense":         r.get("offense", {}).get("rating") if isinstance(r.get("offense"), dict) else r.get("offense"),
            "defense":         r.get("defense", {}).get("rating") if isinstance(r.get("defense"), dict) else r.get("defense"),
            "special_teams":   r.get("specialTeams", {}).get("rating") if isinstance(r.get("specialTeams"), dict) else None,
        }


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run(year: int, skip_advanced: bool = False) -> None:
    pipeline = dlt.pipeline(
        pipeline_name="cfbd",
        destination=dlt.destinations.duckdb(DB_PATH),
        dataset_name="cfbd",
    )

    resources = [
        games_resource(year=year),
        lines_resource(year=year),
        sp_ratings_resource(year=year),
    ]
    if not skip_advanced:
        resources.append(advanced_box_scores_resource(year=year))

    print(f"Loading CFBD data for {year}...")
    load_info = pipeline.run(resources)
    print(load_info)


def main() -> None:
    p = argparse.ArgumentParser(description="Load CFBD data into DuckDB via DLT.")
    p.add_argument("--year",         type=int, default=datetime.now().year)
    p.add_argument("--end-year",     type=int, default=None,
                   help="Pull multiple seasons (--year 2021 --end-year 2025)")
    p.add_argument("--skip-advanced", action="store_true",
                   help="Skip advanced box scores (faster, fewer API calls)")
    args = p.parse_args()

    end = args.end_year or args.year
    for yr in range(args.year, end + 1):
        print(f"\n{'='*50}")
        print(f"Season: {yr}")
        print(f"{'='*50}")
        run(year=yr, skip_advanced=args.skip_advanced)


if __name__ == "__main__":
    main()
