#!/usr/bin/env python3
"""
nba_nhl_build_crosswalks.py

Builds the dbt team crosswalk seeds from the distinct team keys actually present
in the raw tables, and reports every key that doesn't map to a franchise.

  dbt/seeds/nba_team_crosswalk.csv
  dbt/seeds/nhl_team_crosswalk.csv

One row per (team_code, source, source_key) with the seasons the key was seen in.
team_code is the canonical franchise code (nba_api abbreviations for the NBA, NHL API
codes for the NHL), so a relocated or renamed team keeps one code across eras:
Seattle -> OKC, New Jersey -> BKN, New Orleans Hornets -> NOP, Bobcats -> CHA,
Atlanta Thrashers -> WPG, Phoenix/Arizona -> UTA.

valid_from_season is blank when the key appears in the source's first loaded season,
valid_to_season is blank when it appears in the source's latest season, so a backfill
or a new season keeps matching. The only hand-written part is the abbreviation
normalisation below; full team names (historical_lines) are mapped through the names
nba_api and ESPN themselves report.

Keys that stay unmapped are exhibition sides (All-Star teams, 4 Nations countries),
which the staging models drop by design.

Usage
  uv run python scripts/nba_nhl_build_crosswalks.py

Read-only on DuckDB; safe while the API runs. Rerun after loading a new season.
"""

from __future__ import annotations

import csv
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "warehouse" / "ons.duckdb"
SEEDS = ROOT / "dbt" / "seeds"

NBA_CODES = {"ATL", "BKN", "BOS", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW", "HOU",
             "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK", "OKC", "ORL",
             "PHI", "PHX", "POR", "SAC", "SAS", "TOR", "UTA", "WAS"}
NHL_CODES = {"ANA", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL", "DAL", "DET", "EDM",
             "FLA", "LAK", "MIN", "MTL", "NJD", "NSH", "NYI", "NYR", "OTT", "PHI", "PIT",
             "SEA", "SJS", "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WPG", "WSH"}

# source abbreviation -> canonical franchise code (anything not listed maps to itself
# when it is a canonical code)
NBA_ABBR = {
    # ESPN
    "GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS", "UTAH": "UTA", "WSH": "WAS",
    # nba_api, former names
    "NJN": "BKN", "NOH": "NOP", "SEA": "OKC",
}
NHL_ABBR = {
    # ESPN
    "LA": "LAK", "NJ": "NJD", "SJ": "SJS", "TB": "TBL", "UTAH": "UTA",
    # MoneyPuck before 2021-22
    "L.A": "LAK", "N.J": "NJD", "S.J": "SJS", "T.B": "TBL",
    # relocations
    "ARI": "UTA",   # Phoenix / Arizona Coyotes -> Utah (2024-25)
}
# per-source overrides: ESPN's NHL "ATL" is the Atlantic division All-Star side
SOURCE_ABBR = {("nhl", "moneypuck"): {"ATL": "WPG"}}   # Atlanta Thrashers -> Winnipeg (2011-12)

# (source, sql returning key, name, season) per league
NBA_SOURCES = {
    "espn_id": """select home_id, home_name, home_abbr, season from nba.games
                  union all select away_id, away_name, away_abbr, season from nba.games""",
    "espn_abbr": """select home_abbr, home_name, home_abbr, season from nba.games
                    union all select away_abbr, away_name, away_abbr, season from nba.games""",
    "nba_api_id": """select cast(team_id as varchar), team_name, team_abbreviation, season
                     from nba.team_game_logs""",
    "nba_api_abbr": """select team_abbreviation, team_name, team_abbreviation, season
                       from nba.team_game_logs""",
    "historical_lines": """select home_team, home_team, null, season from nba.historical_lines
                           union all select away_team, away_team, null, season from nba.historical_lines""",
}
NHL_SOURCES = {
    "espn_id": """select home_id, home_name, home_abbr, season from nhl.games
                  union all select away_id, away_name, away_abbr, season from nhl.games""",
    "espn_abbr": """select home_abbr, home_name, home_abbr, season from nhl.games
                    union all select away_abbr, away_name, away_abbr, season from nhl.games""",
    "moneypuck": """select playerteam, playerteam, playerteam, season_end
                    from nhl.moneypuck_team_games""",
    "nhl_api": """select team, team, team, cast(left(game_id, 4) as int) + 1
                  from nhl.goalie_games""",
}


def build(con, league: str, sources: dict, abbr_map: dict, codes: set) -> tuple[list, list]:
    def canon(abbr, src):
        if abbr is None:
            return None
        c = SOURCE_ABBR.get((league, src), {}).get(abbr) or abbr_map.get(abbr, abbr)
        return c if c in codes else None

    # full name -> code, from the sources that report both a name and an abbreviation
    name_to_code: dict[str, str] = {}
    for src, sql in sources.items():
        if src == "historical_lines":
            continue
        for name, abbr in con.execute(f"select distinct k2, k3 from ({sql}) t(k1, k2, k3, s)").fetchall():
            if canon(abbr, src):
                name_to_code.setdefault(name, canon(abbr, src))

    out, unmapped = [], []
    for src, sql in sources.items():
        lo, hi = con.execute(f"select min(s), max(s) from ({sql}) t(k, n, a, s)").fetchone()
        keys = con.execute(f"""
            select k, a, arg_max(n, s), min(s), max(s), count(*)
            from ({sql}) t(k, n, a, s) where k is not null group by k, a order by k""").fetchall()
        merged: dict[tuple, list] = {}
        for key, abbr, name, smin, smax, n in keys:
            code = canon(abbr, src) if abbr is not None else name_to_code.get(name)
            if code is None:
                unmapped.append((league, src, key, name, smin, smax, n))
                continue
            m = merged.setdefault((code, key), [name, smin, smax])
            m[1], m[2] = min(m[1], smin), max(m[2], smax)
            if smax >= m[2]:
                m[0] = name
        for (code, key), (name, smin, smax) in sorted(merged.items()):
            out.append({
                "team_code": code, "source": src, "source_key": key,
                "valid_from_season": "" if smin == lo else smin,
                "valid_to_season": "" if smax == hi else smax,
                "source_name": name,
            })
    return out, unmapped


def check_overlaps(rows: list, league: str) -> None:
    """A source key must resolve to one franchise in any season."""
    by_key: dict[tuple, list] = {}
    for r in rows:
        by_key.setdefault((r["source"], r["source_key"]), []).append(r)
    for k, rs in by_key.items():
        if len({r["team_code"] for r in rs}) > 1:
            raise SystemExit(f"{league}: key {k} maps to several franchises: {rs}")


def main() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    SEEDS.mkdir(parents=True, exist_ok=True)
    for league, sources, amap, codes in (("nba", NBA_SOURCES, NBA_ABBR, NBA_CODES),
                                         ("nhl", NHL_SOURCES, NHL_ABBR, NHL_CODES)):
        rows, unmapped = build(con, league, sources, amap, codes)
        check_overlaps(rows, league)
        path = SEEDS / f"{league}_team_crosswalk.csv"
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        missing = codes - {r["team_code"] for r in rows}
        print(f"{league}: {len(rows)} rows -> {path.relative_to(ROOT)}"
              f"  ({len({r['team_code'] for r in rows})} franchises"
              f"{', missing ' + ','.join(sorted(missing)) if missing else ''})")
        for src in sources:
            n = sum(r["source"] == src for r in rows)
            print(f"  {src:17} {n:3} keys mapped")
        print(f"  unmapped keys ({len(unmapped)}):")
        for lg, src, key, name, smin, smax, n in unmapped:
            print(f"    {src:17} {key!s:10} {name:28} seasons {smin}-{smax}  {n} team-games")


if __name__ == "__main__":
    main()
