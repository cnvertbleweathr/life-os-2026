#!/usr/bin/env python3
"""
nba_pregame_lookup.py

Pre-game report for one NBA game, modeled on scripts/pregame_lookup.py (CFB):
team form, schedule spots, team ATS profiles, the ratings model vs the line, which
rules fire, and a bottom line.

Everything is computed as of the game date from games strictly before it, with the
same definitions as mart_nba_game_features. For a past game the report cross-checks
itself against that game's row in the mart and shows the result at the end.

Rules: Phase 4 (docs/NBA_NHL_ATS_DATA.md -> Edge validation) validated NO rule, so
none can fire and the bottom line is NO BET. The paper forward test (regular-season
totals vs the opening total, |predicted - total| >= 12) is shown as a paper entry,
never as a bet.

Usage
  uv run python scripts/nba_pregame_lookup.py --home BOS --away NYK --spread -6.5 --total 221.5
  uv run python scripts/nba_pregame_lookup.py --home Celtics --away Knicks --date 2025-03-08 \\
      --spread -6.5 --total 221.5 --ml -260 +210
  (--spread is the home spread: negative = home favoured. --ml is HOME AWAY.)

Read-only on DuckDB; safe while the API runs.
"""

from __future__ import annotations

import argparse

import pandas as pd

from nba_nhl_lookup_common import (blend, check_against_mart, connect, find_game, fmt, novig_home,
                                   parse_date, print_profiles, print_schedule, resolve_team,
                                   schedule_features, season_of, sep, site_coords)

PAPER_TOTAL_T = 12.0
METRICS = ["games", "ortg", "drtg", "net", "pace", "efg", "tov_pct", "orb_pct", "ft_rate",
           "opp_efg", "opp_tov_pct", "opp_orb_pct", "opp_ft_rate"]


def box_rows(con, team: str, season: int, d) -> pd.DataFrame:
    return con.execute("""
        select t.season, t.game_date, t.nba_game_id, t.pts, t.fgm, t.fga, t.fg3m, t.fta, t.ftm,
               t.oreb, t.dreb, t.tov, t.minutes as team_minutes,
               o.pts as opp_pts, o.fgm as opp_fgm, o.fga as opp_fga, o.fg3m as opp_fg3m,
               o.fta as opp_fta, o.ftm as opp_ftm, o.oreb as opp_oreb, o.dreb as opp_dreb, o.tov as opp_tov,
               0.5 * ((t.fga - t.oreb + t.tov + 0.44 * t.fta) + (o.fga - o.oreb + o.tov + 0.44 * o.fta)) as poss
        from main_staging.stg_nba__team_game_logs t
        join main_staging.stg_nba__team_game_logs o on o.nba_game_id = t.nba_game_id and o.team_code <> t.team_code
        where t.team_code = ? and (t.season = ? and t.game_date < ? or t.season = ?)
        order by t.game_date, t.nba_game_id""", [team, season, d, season - 1]).df()


def metrics(g: pd.DataFrame) -> dict:
    """nba_box_metrics (dbt/macros/nba_nhl_features.sql) from a set of team-games."""
    s = g.sum(numeric_only=True)
    n = int(g.poss.notna().sum())
    if n == 0:
        return {m: (0 if m == "games" else None) for m in METRICS}

    def r(a, b):
        return a / b if b else None
    return {
        "games": n,
        "ortg": r(100 * s.pts, s.poss), "drtg": r(100 * s.opp_pts, s.poss),
        "net": r(100 * (s.pts - s.opp_pts), s.poss), "pace": r(240 * s.poss, s.team_minutes),
        "efg": r(s.fgm + 0.5 * s.fg3m, s.fga), "tov_pct": r(s.tov, s.fga + 0.44 * s.fta + s.tov),
        "orb_pct": r(s.oreb, s.oreb + s.opp_dreb), "ft_rate": r(s.ftm, s.fga),
        "opp_efg": r(s.opp_fgm + 0.5 * s.opp_fg3m, s.opp_fga),
        "opp_tov_pct": r(s.opp_tov, s.opp_fga + 0.44 * s.opp_fta + s.opp_tov),
        "opp_orb_pct": r(s.opp_oreb, s.opp_oreb + s.dreb), "opp_ft_rate": r(s.opp_ftm, s.opp_fga),
    }


def team_form(con, team: str, season: int, d) -> dict[str, dict]:
    g = box_rows(con, team, season, d)
    cur, prev = g[g.season == season], g[g.season == season - 1]
    return {"l5": metrics(cur.tail(5)), "l10": metrics(cur.tail(10)),
            "std": metrics(cur), "prior": metrics(prev) if len(prev) else {m: None for m in METRICS}}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    p.add_argument("--home", required=True)
    p.add_argument("--away", required=True)
    p.add_argument("--date", help="game date YYYY-MM-DD (US/Eastern); default today")
    p.add_argument("--spread", type=float, help="home spread, negative = home favoured")
    p.add_argument("--total", type=float, help="total (for the paper test, the opening total)")
    p.add_argument("--ml", type=float, nargs=2, metavar=("HOME", "AWAY"))
    p.add_argument("--playoffs", action="store_true", help="playoff game (paper totals test is regular season only)")
    p.add_argument("--db")
    a = p.parse_args()

    d = parse_date(a.date)
    season = season_of(d)
    home, away = resolve_team("nba", a.home, season), resolve_team("nba", a.away, season)
    con = connect(a.db)
    row = find_game(con, "nba", home, away, d)
    playoffs = a.playoffs or (row is not None and int(row.season_type) == 3)

    print(f"\n{'=' * 72}\n  NBA PRE-GAME REPORT   {away} @ {home}   {d}  (season {season - 1}-{str(season)[2:]})")
    if a.spread is not None:
        fav, dog = (home, away) if a.spread < 0 else (away, home)
        print(f"  Spread: {fav} -{abs(a.spread):g} / {dog} +{abs(a.spread):g}", end="")
    if a.total is not None:
        print(f"   Total: {a.total:g}", end="")
    if a.ml:
        print(f"   ML: {home} {a.ml[0]:+g} / {away} {a.ml[1]:+g}", end="")
    print(f"\n{'=' * 72}")

    # ── form ────────────────────────────────────────────────────────────────
    sep("Team form (possession-based, games before this date)")
    fh, fa = team_form(con, home, season, d), team_form(con, away, season, d)
    print(f"  {'':16}{'last 5':>16}{'last 10':>16}{'season':>16}{'prior season':>16}")
    for t, f in ((home, fh), (away, fa)):
        print(f"  {t} ({f['std']['games']} games this season)")
        for m, lab, spec in (("net", "net rtg", "+.1f"), ("ortg", "off rtg", ".1f"), ("drtg", "def rtg", ".1f"),
                             ("pace", "pace", ".1f"), ("efg", "eFG%", ".3f"), ("tov_pct", "TOV%", ".3f"),
                             ("orb_pct", "ORB%", ".3f"), ("ft_rate", "FT rate", ".3f"), ("opp_efg", "opp eFG%", ".3f")):
            print(f"    {lab:12}" + "".join(f"{fmt(f[w][m], spec):>16}" for w in ("l5", "l10", "std", "prior")))

    # ── schedule ────────────────────────────────────────────────────────────
    sep("Schedule spots")
    venue = None
    if row is not None and pd.notna(row.espn_game_id):
        v = con.execute("select venue from main_staging.stg_nba__games where game_id = ?", [row.espn_game_id]).fetchone()
        venue = v[0] if v else None
    site = site_coords(con, "nba", venue, home, season)
    sh = schedule_features(con, "nba", home, True, d, season, site)
    sa = schedule_features(con, "nba", away, False, d, season, site)
    print_schedule(home, away, sh, sa)

    # ── profiles ────────────────────────────────────────────────────────────
    sep(f"Team ATS profiles (walk-forward, mart_nba_team_profiles season {season})")
    print_profiles(con, "nba", home, away, season, "ATS")

    # ── ratings model vs the line ───────────────────────────────────────────
    sep("Ratings model vs the market")
    neutral = bool(row.neutral_site) if row is not None else False
    hnet = blend(fh["std"]["net"], fh["std"]["games"], fh["prior"]["net"])
    anet = blend(fa["std"]["net"], fa["std"]["games"], fa["prior"]["net"])
    hpace = blend(fh["std"]["pace"], fh["std"]["games"], fh["prior"]["pace"])
    apace = blend(fa["std"]["pace"], fa["std"]["games"], fa["prior"]["pace"])
    hca = con.execute("""select sum(home_margin - rating_margin) / count(*) from main_marts.mart_nba_game_features
                         where season < ? and not neutral_site and rating_margin is not null
                           and home_margin is not null""", [season]).fetchone()[0]
    implied_spread = None
    if None not in (hnet, anet, hpace, apace):
        rating_margin = (hnet - anet) * (hpace + apace) / 2 / 100
        implied_margin = rating_margin + (0 if neutral else (hca or 0))
        implied_spread = -implied_margin
        print(f"  blended net rating: {home} {hnet:+.1f}, {away} {anet:+.1f}; pace {(hpace + apace) / 2:.1f}; "
              f"home court {fmt(hca, '+.2f')} pts (earlier seasons){' (neutral site: not applied)' if neutral else ''}")
        print(f"  ratings-implied spread: {home} {implied_spread:+.1f}")
        if a.spread is not None:
            edge = a.spread - implied_spread
            print(f"  market {home} {a.spread:+g} -> ratings like {home if edge > 0 else away} by {abs(edge):.1f} pts"
                  f"  (Phase 4: following or fading this gap had no out-of-sample edge)")
    else:
        print("  not enough games to rate both teams")

    # totals paper test
    pred_total = None
    if None not in (hpace, apace):
        def b(f, m):
            return blend(f["std"][m], f["std"]["games"], f["prior"][m])
        hp100 = (b(fh, "ortg") + b(fa, "drtg")) / 2
        ap100 = (b(fa, "ortg") + b(fh, "drtg")) / 2
        pred_raw = (hpace + apace) / 2 / 100 * (hp100 + ap100)
        bias = total_bias(con, season, 3 if playoffs else 2)
        pred_total = pred_raw - (bias or 0)
        print(f"  ratings/pace predicted total: {pred_total:.1f} (bias {fmt(bias, '+.1f')} from earlier seasons removed)")

    # ── rules and bottom line ───────────────────────────────────────────────
    sep("Rules")
    print("  BET WHEN / AUTO BET / NEVER BET: none. No NBA rule passed walk-forward validation (Phase 4),")
    print("  so no rule can fire. Team tiers are descriptive and lose about the vig out of sample.")
    paper = None
    if a.total is not None and pred_total is not None and not playoffs:
        gap = pred_total - a.total
        if abs(gap) >= PAPER_TOTAL_T:
            paper = ("OVER" if gap > 0 else "UNDER", gap)
    sep("Bottom line")
    print("  NO BET  (no validated rule)")
    if paper:
        print(f"  paper forward test: predicted total {pred_total:.1f} vs {a.total:g} ({paper[1]:+.1f}) -> log {paper[0]}"
              f" as a PAPER entry only, at a captured opening price within -135..+115")

    # ── cross-check and result ──────────────────────────────────────────────
    mine = {"home_ortg_l10": fh["l10"]["ortg"], "away_ortg_l10": fa["l10"]["ortg"],
            "home_net_std": fh["std"]["net"], "away_net_prior": fa["prior"]["net"],
            "home_efg_l5": fh["l5"]["efg"], "away_pace_l10": fa["l10"]["pace"],
            "home_days_rest": sh["days_rest"], "away_days_rest": sa["days_rest"],
            "away_games_last7": sa["games_last7"], "away_road_trip_game": sa["road_trip_game"],
            "away_travel_miles": sa["travel_miles"], "home_ats_covers_l10": sh["ats_covers_l10"],
            "implied_home_spread": implied_spread}
    check_against_mart(row, mine)
    if row is not None:
        print(f"  result (known only after the game): {home} {int(row.home_score)} - {away} {int(row.away_score)};"
              f" closing line {home} {fmt(row.home_spread, '+g')} -> {home} "
              f"{'covered' if row.home_ats_margin > 0 else 'push' if row.home_ats_margin == 0 else 'did not cover'};"
              f" total {fmt(row.total, 'g')} -> {'over' if row.total_margin > 0 else 'push' if row.total_margin == 0 else 'under'}")


def total_bias(con, season: int, season_type: int) -> float | None:
    """Mean (predicted - closing total) over earlier seasons of the same type (as in Phase 4)."""
    df = con.execute("""
        select season, season_type, total,
               home_ortg_std, home_drtg_std, home_pace_std, home_ortg_prior, home_drtg_prior, home_pace_prior, home_games_std,
               away_ortg_std, away_drtg_std, away_pace_std, away_ortg_prior, away_drtg_prior, away_pace_prior, away_games_std
        from main_marts.mart_nba_game_features where season < ? and season_type = ? and total is not null""",
                     [season, season_type]).df()
    if df.empty:
        return None

    def bl(side, m):
        std, prior, gp = df[f"{side}_{m}_std"], df[f"{side}_{m}_prior"], df[f"{side}_games_std"].fillna(0)
        both = (std * gp + prior * 10) / (gp + 10)
        return both.where(std.notna() & prior.notna(), std.fillna(prior))
    pace = (bl("home", "pace") + bl("away", "pace")) / 2
    pred = pace / 100 * ((bl("home", "ortg") + bl("away", "drtg")) / 2 + (bl("away", "ortg") + bl("home", "drtg")) / 2)
    return float((pred - df.total).mean())


if __name__ == "__main__":
    main()
