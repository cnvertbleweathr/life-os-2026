#!/usr/bin/env python3
"""
nba_nhl_spine_report.py

Read-only report on the NBA / NHL game spines (dbt: int_nba__game_spine,
int_nhl__game_spine): per season, games, stats match rate, line coverage by
source, close snapshots, prices, and home cover rate; then the unmatched games,
score agreement between ESPN and the stats source, ESPN vs SBR spread agreement,
and which books supplied the chosen lines.

Usage
  uv run python scripts/nba_nhl_spine_report.py
  uv run python scripts/nba_nhl_spine_report.py --db path/to/copy.duckdb

Safe while the API is running: opens DuckDB read-only. Run after `dbt build`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "warehouse" / "ons.duckdb"
SPINE = "main_intermediate.int_{lg}__game_spine"


def show(con, title: str, sql: str) -> None:
    print(f"\n{title}")
    df = con.execute(sql).df()
    print(df.to_string(index=False) if len(df) else "  (none)")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    p.add_argument("--db", default=str(DB_PATH))
    a = p.parse_args()
    con = duckdb.connect(a.db, read_only=True)

    for lg, key in (("nba", "nba_game_id"), ("nhl", "nhl_game_id")):
        show(con, f"{lg.upper()} spine per season (pct = % of games; home_cover excludes pushes)", f"""
            select season, game_source as src, count(*) as games,
                   count(*) filter (where season_type = 3) as post,
                   round(100.0 * count({key}) / count(*), 1) as stats_match_pct,
                   count(*) - count({key}) as unmatched,
                   count(*) filter (where line_source like 'espn%') as espn_line,
                   count(*) filter (where line_source = 'historical_lines') as sbr_line,
                   round(100.0 * count(home_spread) / count(*), 1) as line_pct,
                   count(*) filter (where line_snapshot = 'close') as close_n,
                   round(100.0 * count(home_spread_price) / count(*), 1) as price_pct,
                   round(100.0 * count(home_ml) / count(*), 1) as ml_pct,
                   round(100.0 * count(total) / count(*), 1) as total_pct,
                   round(100.0 * count(*) filter (where home_ats_margin > 0)
                         / nullif(count(*) filter (where home_ats_margin <> 0), 0), 1) as home_cover_pct
            from {SPINE.format(lg=lg)} group by 1, 2 order by 1""")
        show(con, f"{lg.upper()} ESPN games with no stats match", f"""
            select season, season_type, game_date, home_team, away_team, home_score, away_score, neutral_site
            from {SPINE.format(lg=lg)} where game_source = 'espn' and {key} is null order by game_date""")
        show(con, f"{lg.upper()} books supplying the chosen spread", f"""
            select line_book, count(*) as games, min(season) as first, max(season) as last
            from {SPINE.format(lg=lg)} where line_book is not null group by 1 order by 2 desc""")

    show(con, "NBA score agreement, ESPN vs nba_api (neutral-site games have no nba_api home side)", """
        select count(*) as matched,
               count(*) filter (where s.home_score = l.home_pts and s.away_score = l.away_pts) as agree,
               count(*) filter (where l.home_pts is null) as no_home_side
        from main_intermediate.int_nba__game_spine s
        join (select nba_game_id, max(pts) filter (where is_home) as home_pts,
                     max(pts) filter (where not is_home) as away_pts
              from main_staging.stg_nba__team_game_logs group by 1) l using (nba_game_id)
        where s.game_source = 'espn'""")
    show(con, "NHL score agreement, ESPN vs MoneyPuck (ESPN counts the shootout goal)", """
        select count(*) as matched,
               count(*) filter (where s.home_score = m.hg and s.away_score = m.ag) as agree,
               count(*) filter (where s.shootout) as shootouts,
               count(*) filter (where not s.shootout and (s.home_score <> m.hg or s.away_score <> m.ag)) as other_diff
        from main_intermediate.int_nhl__game_spine s
        join (select nhl_game_id, max(goalsfor) filter (where is_home) as hg,
                     max(goalsfor) filter (where not is_home) as ag
              from main_staging.stg_nhl__moneypuck_team_games where situation = 'all' group by 1) m
          using (nhl_game_id)
        where s.game_source = 'espn'""")
    show(con, "NBA chosen ESPN spread vs SBR closing spread, same games", """
        select s.season, count(*) as games, round(avg(abs(s.home_spread - h.home_spread)), 2) as mean_abs_diff,
               count(*) filter (where sign(s.home_spread) <> sign(h.home_spread)
                                and abs(h.home_spread) >= 2) as sign_flips
        from main_intermediate.int_nba__game_spine s
        join main_staging.stg_nba__historical_lines h
          on h.game_date = s.game_date and h.home_team = s.home_team and h.away_team = s.away_team
        where s.line_source like 'espn%' group by 1 order by 1""")
    show(con, "NHL lines to filter in backtests", """
        select count(*) filter (where not is_standard_puck_line) as non_standard_puck_line,
               count(*) filter (where not line_consistent) as spread_vs_ml_disagree
        from main_intermediate.int_nhl__game_spine""")


if __name__ == "__main__":
    main()
