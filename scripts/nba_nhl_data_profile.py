#!/usr/bin/env python3
"""
nba_nhl_data_profile.py

Read-only coverage profile of the NBA / NHL raw tables, per league and season:
games, games with any line, with an open / close snapshot, providers seen,
null rates for key columns, and row counts for every stats table. Flags any
season whose regular-season game count is off the expected schedule.

Usage
  uv run python scripts/nba_nhl_data_profile.py            # both leagues
  uv run python scripts/nba_nhl_data_profile.py --league nhl
  uv run python scripts/nba_nhl_data_profile.py --providers  # + provider list per season

Safe while the API is running: opens DuckDB read-only.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "warehouse" / "ons.duckdb"

# Projection sites, aggregates and in-game feeds: not books (docs/NBA_NHL_ATS_DATA.md).
NOT_BOOKS = ("numberfire", "teamrankings", "accuscore", "betegy", "consensus", "Opening")
NOT_BOOK_SQL = ("provider_name in (" + ", ".join(f"'{p}'" for p in NOT_BOOKS) + ")"
                " or provider_name ilike '%live odds%'")


def expected_regular_season(league: str, season: int) -> tuple[int, str]:
    """Scheduled regular-season games, and a note for the irregular seasons."""
    if league == "nba":
        return {2012: (990, "lockout, 66 games"),
                2020: (1059, "COVID pause + bubble"),
                2021: (1080, "72 games")}.get(season, (1230, ""))
    if season == 2013:
        return 720, "lockout, 48 games"
    if season == 2020:
        return 1082, "COVID pause"
    if season == 2021:
        return 868, "56 games, divisional"
    if season <= 2017:
        return 1230, ""
    if season <= 2021:
        return 1271, "31 teams (Vegas)"
    return 1312, "32 teams (Seattle)"


def exists(con, schema: str, table: str) -> bool:
    return con.execute(
        "select count(*) from information_schema.tables where table_schema = ? and table_name = ?",
        [schema, table]).fetchone()[0] > 0


def has_col(con, schema: str, table: str, col: str) -> bool:
    """dlt drops columns that are null on every row (e.g. NBA shootout)."""
    return con.execute(
        "select count(*) from information_schema.columns"
        " where table_schema = ? and table_name = ? and column_name = ?",
        [schema, table, col]).fetchone()[0] > 0


def pct(n, d) -> str:
    return "   -" if not d else f"{100 * n / d:4.0f}"


def rows(con, sql: str) -> dict:
    """First column -> rest of the row."""
    return {r[0]: r[1:] for r in con.execute(sql).fetchall()}


def profile_games_and_odds(con, league: str, show_providers: bool) -> None:
    s = league
    if not exists(con, s, "games"):
        print(f"  {s}.games: missing")
        return
    has_odds = exists(con, s, "odds")
    # ESPN files exhibitions as regular season: NBA All-Star / Rising Stars / World v USA,
    # NHL All-Star 3-on-3 and the 2025 4 Nations Face-Off. A side with < 10 games that
    # season isn't a franchise, so the game is an exhibition.
    shootout = "count(*) filter (where shootout)" if has_col(con, s, "games", "shootout") else "0"
    real = f"""
        with side as (
            select season, home_id as team_id from {s}.games
            union all select season, away_id from {s}.games),
        franchise as (select season, team_id from side group by 1, 2 having count(*) >= 10),
        gx as (
            select g.*, (h.team_id is null or a.team_id is null) as exhibition
            from {s}.games g
            left join franchise h on h.season = g.season and h.team_id = g.home_id
            left join franchise a on a.season = g.season and a.team_id = g.away_id)"""
    g = rows(con, f"""{real}
        select season,
               count(*) filter (where season_type = 2 and completed and not exhibition),
               count(*) filter (where season_type = 3 and completed and not exhibition),
               count(*) filter (where exhibition),
               count(*) filter (where not completed and not exhibition),
               count(*) filter (where completed and (home_score is null or away_score is null)),
               count(*) filter (where went_ot),
               {shootout}
        from gx group by 1 order by 1""")
    o = {}
    if has_odds:
        # lines on real, completed games only
        o = rows(con, f"""{real},
            b as (select o.* from {s}.odds o join gx using (game_id)
                  where gx.completed and not gx.exhibition and not ({NOT_BOOK_SQL}))
            select season,
                   count(distinct game_id),
                   count(distinct game_id) filter (where close_home_spread is not null),
                   count(distinct game_id) filter (where open_home_spread is not null),
                   count(distinct provider_id),
                   count(*),
                   avg((home_spread is null)::int), avg((home_spread_price is null)::int),
                   avg((home_ml is null)::int), avg((total is null)::int),
                   avg((close_home_spread is null)::int)
            from b group by 1 order by 1""")
        allp = rows(con, f"select season, count(distinct game_id) from {s}.odds group by 1")

    print(f"\n{league.upper()}  ESPN games and lines")
    print("  reg/post = completed real games; exh = exhibitions (All-Star etc.); n/p = listed, never played"
          " (canceled / postponed).\n  Line columns: book providers only (projection sites, consensus and"
          " live feeds excluded), on completed real games; % of reg+post.\n  null% is per odds row."
          " 'all-prov' = games with any provider row, exhibitions and unplayed included.")
    print("season  reg  post exh  n/p | exp   flag              | any line   %  open   %  close   % |"
          " books  odds rows | null%: spread price  ML  total close | all-prov")
    for season, (reg, post, exh, notplayed, noscore, ot, so) in g.items():
        exp, note = expected_regular_season(league, season)
        off = abs(reg - exp) > max(2, 0.01 * exp)
        flag = ("OFF " if off else "") + note
        line = f"{season}  {reg:4} {post:4} {exh:3} {notplayed:4} | {exp:4}  {flag[:17]:17} |"
        if season in o:
            lg, cl, op, nprov, nrows, n1, n2, n3, n4, n5 = o[season]
            line += (f" {lg:5} {pct(lg, reg + post)} {op:5} {pct(op, reg + post)} {cl:5} {pct(cl, reg + post)} |"
                     f" {nprov:5} {nrows:9} |       {100*n1:4.0f}  {100*n2:4.0f} {100*n3:4.0f} {100*n4:4.0f}  {100*n5:4.0f} |"
                     f" {allp.get(season, (0,))[0]}")
        else:
            line += "     no lines"
        if noscore:
            line += f"  !! {noscore} completed games with no score"
        print(line)

    if has_odds and show_providers:
        print(f"\n{league.upper()}  providers per season (games covered; * = not a book)")
        for season, in con.execute(f"select distinct season from {s}.odds order by 1").fetchall():
            provs = con.execute(f"""
                select provider_name, provider_id, count(distinct game_id), bool_or({NOT_BOOK_SQL})
                from {s}.odds where season = ? group by 1, 2 order by 3 desc""", [season]).fetchall()
            print(f"  {season}: " + ", ".join(f"{n}{'*' if nb else ''} ({pid}) {k}" for n, pid, k, nb in provs))


def profile_nba_stats(con) -> None:
    print("\nNBA  stats tables")
    print("season | team_game_logs: rows  games reg  games post | historical_lines: rows  null% spread  total  ML")
    tgl = rows(con, """
        select season, count(*),
               count(distinct game_id) filter (where season_type = 'Regular Season'),
               count(distinct game_id) filter (where season_type = 'Playoffs')
        from nba.team_game_logs group by 1""") if exists(con, "nba", "team_game_logs") else {}
    hl = rows(con, """
        select season, count(*), avg((home_spread is null)::int), avg((total is null)::int),
               avg((home_ml is null)::int)
        from nba.historical_lines group by 1""") if exists(con, "nba", "historical_lines") else {}
    for season in sorted(set(tgl) | set(hl)):
        t = tgl.get(season)
        h = hl.get(season)
        exp, note = expected_regular_season("nba", season)
        flag = ""
        if t and abs(t[1] - exp) > max(2, 0.01 * exp):
            flag = f"  OFF: {t[1]} reg games vs {exp} expected {note}"
        elif note:
            flag = f"  ({note})"
        tl = f"{t[0]:6} {t[1]:6} {t[2]:6}" if t else "     -      -      -"
        hlt = f"{h[0]:6}   {100*h[1]:5.1f}  {100*h[2]:5.1f}  {100*h[3]:5.1f}" if h else "     -"
        print(f"{season}   |              {tl}       |            {hlt}{flag}")
    if not tgl:
        print("  nba.team_game_logs: missing")


def profile_nhl_stats(con) -> None:
    print("\nNHL  stats tables")
    print("season | moneypuck: rows    reg  post   all  5on5  5on4  4on5 | null% xgoalsfor corsi | goalie_games: rows  games  starters/game")
    mp = rows(con, """
        select season_end, count(*), count(distinct gameid) filter (where playoffgame = 0),
               count(distinct gameid) filter (where playoffgame = 1),
               count(*) filter (where situation = 'all'), count(*) filter (where situation = '5on5'),
               count(*) filter (where situation = '5on4'), count(*) filter (where situation = '4on5'),
               avg((xgoalsfor is null)::int), avg((corsipercentage is null)::int)
        from nhl.moneypuck_team_games group by 1""") if exists(con, "nhl", "moneypuck_team_games") else {}
    gg = rows(con, """
        select cast(substr(cast(game_id as varchar), 1, 4) as int) + 1 as season,
               count(*), count(distinct game_id),
               count(*) filter (where starter) / nullif(count(distinct game_id), 0)
        from nhl.goalie_games group by 1""") if exists(con, "nhl", "goalie_games") else {}
    for season in sorted(set(mp) | set(gg)):
        m, g = mp.get(season), gg.get(season)
        ml = (f"{m[0]:7} {m[1]:5} {m[2]:5} {m[3]:5} {m[4]:5} {m[5]:5} {m[6]:5} |  {100*m[7]:5.1f}  {100*m[8]:5.1f}"
              if m else "      -     -     -     -     -     -     - |      -      -")
        gl = f"{g[0]:6} {g[1]:6}   {g[2]:.2f}" if g else "     -"
        flag = ""
        if m:
            exp, note = expected_regular_season("nhl", season)
            if abs(m[1] - exp) > max(2, 0.01 * exp):
                flag += f"  OFF: {m[1]} reg games vs {exp} expected"
            elif note:
                flag += f"  ({note})"
        if g and abs(g[2] - 2) > 0.01:
            flag += "  !! starters per game != 2"
        print(f"{season}   | {ml}  |            {gl}{flag}")
    if not mp:
        print("  nhl.moneypuck_team_games: missing")
    if not gg:
        print("  nhl.goalie_games: missing")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    p.add_argument("--league", choices=["nba", "nhl"])
    p.add_argument("--providers", action="store_true", help="list providers per season")
    a = p.parse_args()
    con = duckdb.connect(str(DB_PATH), read_only=True)
    for league in [a.league] if a.league else ["nba", "nhl"]:
        profile_games_and_odds(con, league, a.providers)
        (profile_nba_stats if league == "nba" else profile_nhl_stats)(con)


if __name__ == "__main__":
    main()
