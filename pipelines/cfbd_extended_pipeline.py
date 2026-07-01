#!/usr/bin/env python3
"""
cfbd_extended_pipeline.py

Pulls all additional context factors for betting analysis:
  - Weather per game (temp, wind, precipitation, dome)
  - Coaches per team per season (+ ATS record by coach)
  - Returning production % (NIL/transfer portal net effect)
  - Venue data (location for travel distance calculation)
  - Recruiting rankings per team per season
  - NFL draft production per college
  - Player usage (proxy for injuries via week-over-week drop)
  - Head-to-head rivalry history

Tables produced (schema: cfbd):
  cfbd.weather              — per game weather conditions
  cfbd.coaches              — coach name + seasons per team
  cfbd.returning_production — % EPA returning by team/season
  cfbd.venues               — venue lat/long, dome flag
  cfbd.recruiting_rankings  — avg stars + composite rating by team/season
  cfbd.draft_production     — NFL picks per college per year
  cfbd.player_usage         — usage % by player (injury proxy)
  cfbd.matchup_history      — H2H record between team pairs

Usage:
  python pipelines/cfbd_extended_pipeline.py --year 2024
  python pipelines/cfbd_extended_pipeline.py --year 2021 --end-year 2024
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

API_BASE   = "https://api.collegefootballdata.com"
CFBD_TOKEN = os.getenv("CFBD_API_TOKEN", "")


# ---------------------------------------------------------------------------
# API helper
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
                time.sleep(60 * (attempt + 1))
            else:
                raise
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(5)
    return []


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------

@dlt.resource(
    name="weather",
    write_disposition="merge",
    primary_key="game_id",
)
def weather_resource(year: int) -> Iterator[dict]:
    for season_type in ["regular", "postseason"]:
        for week in range(1, 16):
            data = cfbd_get("/games/weather", {
                "year": year,
                "week": week,
                "seasonType": season_type,
            })
            if not data:
                continue
            for g in data:
                yield {
                    "game_id":              g.get("id"),
                    "season":               g.get("season"),
                    "week":                 g.get("week"),
                    "season_type":          g.get("seasonType"),
                    "home_team":            g.get("homeTeam"),
                    "away_team":            g.get("awayTeam"),
                    "venue_id":             g.get("venueId"),
                    "venue":                g.get("venue"),
                    "game_indoors":         g.get("gameIndoors"),
                    "temperature":          g.get("temperature"),       # Fahrenheit
                    "dew_point":            g.get("dewPoint"),
                    "humidity":             g.get("humidity"),
                    "precipitation":        g.get("precipitation"),     # inches
                    "snowfall":             g.get("snowfall"),           # inches
                    "wind_direction":       g.get("windDirection"),
                    "wind_speed":           g.get("windSpeed"),          # mph
                    "pressure":             g.get("pressure"),
                    "weather_condition":    g.get("weatherCondition"),
                    "weather_condition_code": g.get("weatherConditionCode"),
                }
            time.sleep(0.2)


# ---------------------------------------------------------------------------
# Coaches
# ---------------------------------------------------------------------------

@dlt.resource(
    name="coaches",
    write_disposition="merge",
    primary_key=["first_name", "last_name", "school", "year"],
    columns={
        # FIXED 2026-06-30 -- confirmed missing from the live cfbd.coaches
        # table despite being correctly yielded below. Root cause: same
        # DLT silent-column-drop pattern found earlier tonight in
        # live_picks_pipeline.py. preseason_rank/postseason_rank are
        # legitimately NULL for most teams (only the AP-poll-ranked ~25
        # of ~130 FBS teams have a real value each season) -- confirmed
        # directly against CFBD's raw API: Ohio 2023 (10-3, unranked) has
        # both fields null; Michigan 2023 (the actual national champion)
        # has postseasonRank=1. The data is real and correct from CFBD;
        # DLT dropped the column because some load had too few non-null
        # values to infer a type from.
        "preseason_rank":  {"data_type": "bigint", "nullable": True},
        "postseason_rank": {"data_type": "bigint", "nullable": True},
    },
)
def coaches_resource(year: int) -> Iterator[dict]:
    data = cfbd_get("/coaches", {"year": year})
    for coach in data:
        first = coach.get("firstName", "")
        last  = coach.get("lastName", "")
        for season in (coach.get("seasons") or []):
            yield {
                "first_name":   first,
                "last_name":    last,
                "full_name":    f"{first} {last}",
                "school":       season.get("school"),
                "year":         season.get("year"),
                "games":        season.get("games"),
                "wins":         season.get("wins"),
                "losses":       season.get("losses"),
                "ties":         season.get("ties"),
                "preseason_rank": season.get("preSeasonRank"),
                "postseason_rank": season.get("postSeasonRank"),
                "srs":          season.get("srs"),
                "sp_overall":   season.get("spOverall"),
                "sp_offense":   season.get("spOffense"),
                "sp_defense":   season.get("spDefense"),
            }


# ---------------------------------------------------------------------------
# Returning production (NIL / transfer portal net effect)
# ---------------------------------------------------------------------------

@dlt.resource(
    name="returning_production",
    write_disposition="merge",
    primary_key=["season", "team"],
)
def returning_production_resource(year: int) -> Iterator[dict]:
    data = cfbd_get("/player/returning", {"year": year})
    for r in data:
        yield {
            "season":                   r.get("season"),
            "team":                     r.get("team"),
            "conference":               r.get("conference"),
            "total_ppa":                r.get("totalPPA"),
            "total_passing_ppa":        r.get("totalPassingPPA"),
            "total_receiving_ppa":      r.get("totalReceivingPPA"),
            "total_rushing_ppa":        r.get("totalRushingPPA"),
            "percent_ppa":              r.get("percentPPA"),           # % of last year's production returning
            "percent_passing_ppa":      r.get("percentPassingPPA"),
            "percent_receiving_ppa":    r.get("percentReceivingPPA"),
            "percent_rushing_ppa":      r.get("percentRushingPPA"),
            "usage":                    r.get("usage"),
            "passing_usage":            r.get("passingUsage"),
            "receiving_usage":          r.get("receivingUsage"),
            "rushing_usage":            r.get("rushingUsage"),
        }


# ---------------------------------------------------------------------------
# Venues (for travel distance calculation)
# ---------------------------------------------------------------------------

@dlt.resource(
    name="venues",
    write_disposition="replace",
)
def venues_resource() -> Iterator[dict]:
    data = cfbd_get("/venues")
    for v in data:
        yield {
            "venue_id":          v.get("id"),
            "name":              v.get("name"),
            "capacity":          v.get("capacity"),
            "grass":             v.get("grass"),
            "dome":              v.get("dome"),
            "city":              v.get("city"),
            "state":             v.get("state"),
            "country_code":      v.get("countryCode"),
            "timezone":          v.get("timezone"),
            "latitude":          v.get("latitude"),
            "longitude":         v.get("longitude"),
            "elevation":         v.get("elevation"),
            "construction_year": v.get("constructionYear"),
        }


# ---------------------------------------------------------------------------
# Recruiting rankings (talent gap between teams)
# ---------------------------------------------------------------------------

@dlt.resource(
    name="recruiting_rankings",
    write_disposition="merge",
    primary_key=["year", "team"],
)
def recruiting_rankings_resource(year: int) -> Iterator[dict]:
    """
    Team-level recruiting composite — pull last 4 years and aggregate.
    A team's avg recruit rating over 4 years reflects talent on roster.
    """
    data = cfbd_get("/recruiting/teams", {"year": year})
    for r in data:
        yield {
            "year":         r.get("year"),
            "team":         r.get("team"),
            "rank":         r.get("rank"),
            "points":       r.get("points"),
        }


# ---------------------------------------------------------------------------
# Draft production (NFL pipeline quality)
# ---------------------------------------------------------------------------

@dlt.resource(
    name="draft_production",
    write_disposition="merge",
    primary_key=["nfl_athlete_id", "year"],
)
def draft_production_resource(year: int) -> Iterator[dict]:
    """NFL draft picks by college — measures program talent development."""
    data = cfbd_get("/draft/picks", {"year": year})
    for pick in data:
        yield {
            "college_athlete_id":   pick.get("collegeAthleteId"),
            "nfl_athlete_id":       pick.get("nflAthleteId"),
            "college_team":         pick.get("collegeTeam"),
            "college_conference":   pick.get("collegeConference"),
            "nfl_team":             pick.get("nflTeam"),
            "year":                 pick.get("year"),
            "overall":              pick.get("overall"),
            "round":                pick.get("round"),
            "pick":                 pick.get("pick"),
            "name":                 pick.get("name"),
            "position":             pick.get("position"),
            "pre_draft_ranking":    pick.get("preDraftRanking"),
            "pre_draft_grade":      pick.get("preDraftGrade"),
        }


# ---------------------------------------------------------------------------
# Player usage (injury proxy — week over week drop signals injury)
# ---------------------------------------------------------------------------

@dlt.resource(
    name="player_usage",
    write_disposition="merge",
    primary_key=["season", "player_id"],
)
def player_usage_resource(year: int) -> Iterator[dict]:
    """
    Season-level usage by player. Compare to prior year to detect roster changes.
    High usage players missing = injury/transfer signal.
    """
    # Get all FBS teams
    teams = cfbd_get("/teams/fbs", {"year": year})
    team_names = [t.get("school") for t in teams if t.get("school")]

    for team in team_names:
        try:
            data = cfbd_get("/player/usage", {"year": year, "team": team})
            for p in data:
                usage = p.get("usage") or {}
                yield {
                    "season":       year,
                    "player_id":    p.get("id"),
                    "name":         p.get("name"),
                    "position":     p.get("position"),
                    "team":         p.get("team"),
                    "conference":   p.get("conference"),
                    "usage_overall":    usage.get("overall"),
                    "usage_pass":       usage.get("pass"),
                    "usage_rush":       usage.get("rush"),
                    "usage_firstdown":  usage.get("firstDown"),
                    "usage_seconddown": usage.get("secondDown"),
                    "usage_thirddown":  usage.get("thirdDown"),
                    "usage_standarddown": usage.get("standardDowns"),
                    "usage_passingdown":  usage.get("passingDowns"),
                }
            time.sleep(0.1)
        except Exception as e:
            print(f"  Warning: usage failed for {team}: {e}")
            continue


# ---------------------------------------------------------------------------
# Matchup history (rivalry factor)
# ---------------------------------------------------------------------------

@dlt.resource(
    name="matchup_history",
    write_disposition="merge",
    primary_key=["team1", "team2"],
)
def matchup_history_resource(rivalries: list[tuple[str, str]]) -> Iterator[dict]:
    """
    Head-to-head records for known rivalry pairs.
    Extend the rivalries list as needed.
    """
    for team1, team2 in rivalries:
        try:
            data = cfbd_get("/teams/matchup", {"team1": team1, "team2": team2})
            if not data:
                continue
            games = data.get("games", [])
            last10 = games[-10:] if len(games) >= 10 else games

            # Count last 10 outcomes
            t1_last10 = sum(1 for g in last10 if g.get("winner") == team1)
            t2_last10 = sum(1 for g in last10 if g.get("winner") == team2)

            yield {
                "team1":         data.get("team1"),
                "team2":         data.get("team2"),
                "team1_wins":    data.get("team1Wins"),
                "team2_wins":    data.get("team2Wins"),
                "ties":          data.get("ties"),
                "total_games":   data.get("team1Wins", 0) + data.get("team2Wins", 0) + data.get("ties", 0),
                "team1_last10_wins": t1_last10,
                "team2_last10_wins": t2_last10,
                "most_recent_winner": games[-1].get("winner") if games else None,
                "most_recent_season": games[-1].get("season") if games else None,
            }
            time.sleep(0.2)
        except Exception as e:
            print(f"  Warning: matchup failed for {team1} vs {team2}: {e}")
            continue


# ---------------------------------------------------------------------------
# Known rivalries
# ---------------------------------------------------------------------------

KNOWN_RIVALRIES = [
    # SEC
    ("Alabama", "Auburn"),           # Iron Bowl
    ("Alabama", "Tennessee"),
    ("Alabama", "LSU"),
    ("Georgia", "Florida"),          # World's Largest Cocktail Party
    ("Georgia", "Georgia Tech"),
    ("LSU", "Ole Miss"),
    ("Ole Miss", "Mississippi State"), # Egg Bowl
    ("Tennessee", "Kentucky"),
    ("Florida", "Florida State"),
    # Big Ten
    ("Ohio State", "Michigan"),      # The Game
    ("Ohio State", "Penn State"),
    ("Michigan", "Michigan State"),
    ("Iowa", "Iowa State"),
    ("Minnesota", "Wisconsin"),      # Paul Bunyan's Axe
    # Big 12
    ("Oklahoma", "Texas"),           # Red River Rivalry
    ("Oklahoma", "Oklahoma State"),  # Bedlam
    ("Kansas", "Kansas State"),      # Sunflower Showdown
    ("TCU", "SMU"),
    # ACC
    ("Florida State", "Miami"),
    ("Clemson", "South Carolina"),
    ("Duke", "North Carolina"),      # South's Oldest Rivalry
    # Pac-12 (now remnants)
    ("USC", "UCLA"),                 # crosstown
    ("Oregon", "Oregon State"),      # Civil War
    ("Washington", "Washington State"), # Apple Cup
    # Mountain West / other
    ("Boise State", "Nevada"),
    ("Air Force", "Army"),           # Commander in Chief
    ("Army", "Navy"),                # The Game
    ("BYU", "Utah"),                 # Holy War
]


# ---------------------------------------------------------------------------
# PPA team metrics (offensive/defensive efficiency per play)
# ---------------------------------------------------------------------------

@dlt.resource(
    name="ppa_teams",
    write_disposition="merge",
    primary_key=["season", "team"],
)
def ppa_teams_resource(year: int) -> Iterator[dict]:
    """
    Team-level PPA (Predicted Points Added) per play.
    Key efficiency metric — how many predicted points does each play generate?
    Positive offense PPA = efficient offense. Low defense PPA = stout defense.
    """
    data = cfbd_get("/ppa/teams", {"year": year})
    for r in data:
        off = r.get("offense") or {}
        deff = r.get("defense") or {}
        off_cum = off.get("cumulative") or {}
        def_cum = deff.get("cumulative") or {}

        yield {
            "season":               year,
            "team":                 r.get("team"),
            "conference":           r.get("conference"),

            # Offensive PPA
            "off_ppa_overall":      off.get("overall"),
            "off_ppa_passing":      off.get("passing"),
            "off_ppa_rushing":      off.get("rushing"),
            "off_ppa_first_down":   off.get("firstDown"),
            "off_ppa_second_down":  off.get("secondDown"),
            "off_ppa_third_down":   off.get("thirdDown"),
            "off_ppa_cumulative":   off_cum.get("total"),

            # Defensive PPA (lower = better defense)
            "def_ppa_overall":      deff.get("overall"),
            "def_ppa_passing":      deff.get("passing"),
            "def_ppa_rushing":      deff.get("rushing"),
            "def_ppa_first_down":   deff.get("firstDown"),
            "def_ppa_second_down":  deff.get("secondDown"),
            "def_ppa_third_down":   deff.get("thirdDown"),
            "def_ppa_cumulative":   def_cum.get("total"),
        }


# ---------------------------------------------------------------------------
# Advanced season stats (success rate, explosiveness, havoc, line yards)
# ---------------------------------------------------------------------------

@dlt.resource(
    name="advanced_stats",
    write_disposition="merge",
    primary_key=["season", "team"],
)
def advanced_stats_resource(year: int) -> Iterator[dict]:
    """
    Advanced team stats per season. Directly answers:
      - Strength of defense: def_success_rate, def_havoc_total, def_ppa
      - Strength of running game: off_rushing_ppa, off_line_yards, off_power_success
      - Overall offensive efficiency: off_success_rate, off_explosiveness
    """
    data = cfbd_get("/stats/season/advanced", {"year": year})
    for r in data:
        off  = r.get("offense") or {}
        deff = r.get("defense") or {}
        off_rush  = off.get("rushingPlays") or {}
        off_pass  = off.get("passingPlays") or {}
        def_rush  = deff.get("rushingPlays") or {}
        def_pass  = deff.get("passingPlays") or {}
        off_std   = off.get("standardDowns") or {}
        off_pass_dwn = off.get("passingDowns") or {}
        def_havoc = deff.get("havoc") or {}
        off_havoc = off.get("havoc") or {}
        off_fp    = off.get("fieldPosition") or {}
        def_fp    = deff.get("fieldPosition") or {}

        yield {
            "season":                    year,
            "team":                      r.get("team"),
            "conference":                r.get("conference"),

            # Offensive efficiency
            "off_plays":                 off.get("plays"),
            "off_ppa":                   off.get("ppa"),
            "off_success_rate":          off.get("successRate"),
            "off_explosiveness":         off.get("explosiveness"),
            "off_power_success":         off.get("powerSuccess"),
            "off_stuff_rate":            off.get("stuffRate"),
            "off_line_yards":            off.get("lineYards"),
            "off_second_level_yards":    off.get("secondLevelYards"),
            "off_open_field_yards":      off.get("openFieldYards"),
            "off_points_per_opportunity": off.get("pointsPerOpportunity"),
            "off_field_pos_avg_start":   off_fp.get("averageStart"),
            "off_havoc_total":           off_havoc.get("total"),

            # Rushing offense (running game strength)
            "off_rush_rate":             off_rush.get("rate"),
            "off_rush_ppa":              off_rush.get("ppa"),
            "off_rush_success_rate":     off_rush.get("successRate"),
            "off_rush_explosiveness":    off_rush.get("explosiveness"),

            # Passing offense
            "off_pass_ppa":              off_pass.get("ppa"),
            "off_pass_success_rate":     off_pass.get("successRate"),
            "off_pass_explosiveness":    off_pass.get("explosiveness"),

            # Standard/passing down efficiency
            "off_standard_down_ppa":     off_std.get("ppa"),
            "off_standard_down_sr":      off_std.get("successRate"),
            "off_passing_down_ppa":      off_pass_dwn.get("ppa"),
            "off_passing_down_sr":       off_pass_dwn.get("successRate"),

            # Defensive efficiency (lower success rate allowed = better defense)
            "def_plays":                 deff.get("plays"),
            "def_ppa":                   deff.get("ppa"),
            "def_success_rate":          deff.get("successRate"),
            "def_explosiveness":         deff.get("explosiveness"),
            "def_power_success":         deff.get("powerSuccess"),
            "def_stuff_rate":            deff.get("stuffRate"),
            "def_line_yards":            deff.get("lineYards"),
            "def_points_per_opportunity": deff.get("pointsPerOpportunity"),
            "def_field_pos_avg_start":   def_fp.get("averagePredictedPoints"),

            # Defensive havoc (pressure, TFLs, PBUs — disruption rate)
            "def_havoc_total":           def_havoc.get("total"),
            "def_havoc_front_seven":     def_havoc.get("frontSeven"),
            "def_havoc_db":              def_havoc.get("db"),

            # Rush defense
            "def_rush_ppa":              def_rush.get("ppa"),
            "def_rush_success_rate":     def_rush.get("successRate"),
            "def_rush_explosiveness":    def_rush.get("explosiveness"),

            # Pass defense
            "def_pass_ppa":              def_pass.get("ppa"),
            "def_pass_success_rate":     def_pass.get("successRate"),
            "def_pass_explosiveness":    def_pass.get("explosiveness"),
        }


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run(year: int, skip_usage: bool = False) -> None:
    pipeline = dlt.pipeline(
        pipeline_name="cfbd_extended",
        destination=dlt.destinations.duckdb(DB_PATH),
        dataset_name="cfbd",
    )

    resources = [
        weather_resource(year=year),
        coaches_resource(year=year),
        returning_production_resource(year=year),
        recruiting_rankings_resource(year=year),
        draft_production_resource(year=year),
    ]

    # Venues only need to be loaded once
    resources.append(venues_resource())

    # Rivalries are static
    resources.append(matchup_history_resource(KNOWN_RIVALRIES))

    # PPA team metrics
    resources.append(ppa_teams_resource(year=year))

    # Advanced season stats (defense/rushing strength)
    resources.append(advanced_stats_resource(year=year))

    # Player usage is slow (one request per team)
    if not skip_usage:
        resources.append(player_usage_resource(year=year))

    print(f"Loading extended CFBD data for {year}...")
    load_info = pipeline.run(resources)
    print(load_info)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--year",       type=int, default=datetime.now().year)
    p.add_argument("--end-year",   type=int, default=None)
    p.add_argument("--skip-usage", action="store_true",
                   help="Skip player usage (slow — one request per team)")
    args = p.parse_args()

    end = args.end_year or args.year
    for yr in range(args.year, end + 1):
        print(f"\n{'='*50}\nSeason: {yr}\n{'='*50}")
        run(year=yr, skip_usage=args.skip_usage)


if __name__ == "__main__":
    main()
