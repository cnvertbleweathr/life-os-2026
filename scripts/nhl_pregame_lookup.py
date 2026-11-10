#!/usr/bin/env python3
"""
nhl_pregame_lookup.py

Pre-game report for one NHL game, modeled on scripts/pregame_lookup.py (CFB):
xG form, starting goalies, schedule spots, team puck-line profiles, the xG model vs
the moneyline, which rules fire, and a bottom line.

Everything is computed as of the game date from games strictly before it, with the
same definitions as mart_nhl_game_features. For a past game the report cross-checks
itself against that game's row in the mart and shows the result at the end.

Starters: pass --home-goalie / --away-goalie (part of the name) when the starters are
confirmed; otherwise the report uses each team's most recent starter and says so.
For a past game with no names given, the actual starters are used.

Rules: Phase 4 (docs/NBA_NHL_ATS_DATA.md -> Edge validation) validated NO NHL rule,
so none can fire and the bottom line is NO BET.

Usage
  uv run python scripts/nhl_pregame_lookup.py --home TOR --away MTL --puckline -1.5 --ml -190 +160 --total 6.5
  uv run python scripts/nhl_pregame_lookup.py --home "Maple Leafs" --away Canadiens --date 2025-02-15 \\
      --ml -190 +160 --home-goalie Stolarz
  (--puckline is the home puck line, -1.5 = home favoured. --ml is HOME AWAY.)

Read-only on DuckDB; safe while the API runs.
"""

from __future__ import annotations

import argparse
import math

import pandas as pd

from nba_nhl_lookup_common import (blend, check_against_mart, connect, find_game, fmt, novig_home,
                                   parse_date, print_profiles, print_schedule, resolve_team,
                                   schedule_features, season_of, sep, site_coords)

METRICS = ["games", "xgf_pct_5v5", "corsi_pct_5v5", "hd_share_5v5", "pp_xgf60", "pk_xga60",
           "finishing_per_game", "xgf_pct_all"]


def xg_rows(con, team: str, season: int, d) -> pd.DataFrame:
    return con.execute("""
        select nhl_game_id, any_value(season) as season, any_value(game_date) as game_date,
               max(xgoalsfor)               filter (where situation = '5on5') as xgf_5v5,
               max(xgoalsagainst)           filter (where situation = '5on5') as xga_5v5,
               max(shotattemptsfor)         filter (where situation = '5on5') as cf_5v5,
               max(shotattemptsagainst)     filter (where situation = '5on5') as ca_5v5,
               max(highdangershotsfor)      filter (where situation = '5on5') as hdf_5v5,
               max(highdangershotsagainst)  filter (where situation = '5on5') as hda_5v5,
               max(xgoalsfor)               filter (where situation = '5on4') as xgf_pp,
               max(icetime)                 filter (where situation = '5on4') as toi_pp,
               max(xgoalsagainst)           filter (where situation = '4on5') as xga_pk,
               max(icetime)                 filter (where situation = '4on5') as toi_pk,
               max(goalsfor)                filter (where situation = 'all')  as gf_all,
               max(xgoalsfor)               filter (where situation = 'all')  as xgf_all,
               max(xgoalsagainst)           filter (where situation = 'all')  as xga_all
        from main_staging.stg_nhl__moneypuck_team_games
        where team_code = ? and (season = ? and game_date < ? or season = ?)
        group by nhl_game_id
        order by game_date, nhl_game_id""", [team, season, d, season - 1]).df()


def metrics(g: pd.DataFrame) -> dict:
    """nhl_xg_metrics (dbt/macros/nba_nhl_features.sql) from a set of team-games."""
    s = g.sum(numeric_only=True)
    n = int(g.xgf_all.notna().sum())
    if n == 0:
        return {m: (0 if m == "games" else None) for m in METRICS}

    def r(a, b):
        return a / b if b else None
    return {
        "games": n,
        "xgf_pct_5v5": r(s.xgf_5v5, s.xgf_5v5 + s.xga_5v5),
        "corsi_pct_5v5": r(s.cf_5v5, s.cf_5v5 + s.ca_5v5),
        "hd_share_5v5": r(s.hdf_5v5, s.hdf_5v5 + s.hda_5v5),
        "pp_xgf60": r(3600 * s.xgf_pp, s.toi_pp), "pk_xga60": r(3600 * s.xga_pk, s.toi_pk),
        "finishing_per_game": (s.gf_all - s.xgf_all) / n,
        "xgf_pct_all": r(s.xgf_all, s.xgf_all + s.xga_all),
    }


def team_form(con, team: str, season: int, d) -> dict[str, dict]:
    g = xg_rows(con, team, season, d)
    cur, prev = g[g.season == season], g[g.season == season - 1]
    return {"l10": metrics(cur.tail(10)), "std": metrics(cur),
            "prior": metrics(prev) if len(prev) else {m: None for m in METRICS}}


def goalie_starts(con, player_id: int, d) -> pd.DataFrame:
    """His starts before d with approximate GSAx (as in int_nhl__goalie_form)."""
    return con.execute("""
        with g as (
            select *, sum(toi_seconds) over (partition by nhl_game_id, team_code) as team_goalie_toi
            from main_staging.stg_nhl__goalie_games)
        select g.nhl_game_id, g.season, g.game_date, g.saves, g.shots_against, g.goals_against,
               x.xgoalsagainst * g.toi_seconds / nullif(g.team_goalie_toi, 0) - g.goals_against as gsax
        from g
        left join main_staging.stg_nhl__moneypuck_team_games x
          on x.nhl_game_id = g.nhl_game_id and x.team_code = g.team_code and x.situation = 'all'
        where g.player_id = ? and g.starter and g.game_date < ?
        order by g.game_date, g.nhl_game_id""", [player_id, d]).df()


def pick_goalie(con, team: str, d, name: str | None, actual_id) -> tuple[int | None, str, str]:
    if name:
        r = con.execute("""select player_id, any_value(goalie_name) from main_staging.stg_nhl__goalie_games
                           where team_code = ? and goalie_name ilike ? and game_date < ?
                           group by 1 order by max(game_date) desc limit 1""", [team, f"%{name}%", d]).fetchone()
        if not r:
            raise SystemExit(f"no {team} goalie matching '{name}' before {d}")
        return int(r[0]), r[1], "confirmed (given)"
    if actual_id is not None and not pd.isna(actual_id):
        r = con.execute("select any_value(goalie_name) from main_staging.stg_nhl__goalie_games where player_id = ?",
                        [int(actual_id)]).fetchone()
        return int(actual_id), r[0], "actual starter (past game)"
    r = con.execute("""select player_id, goalie_name from main_staging.stg_nhl__goalie_games
                       where team_code = ? and starter and game_date < ? order by game_date desc limit 1""",
                    [team, d]).fetchone()
    return (int(r[0]), r[1], "PROBABLE: most recent starter, not confirmed") if r else (None, "-", "no goalie data")


def goalie_form(con, pid: int | None, season: int, d) -> dict:
    if pid is None:
        return {"l10_n": 0, "gsax_l10": None, "sv_l10": None, "std_n": 0, "gsax_std": None, "sv_std": None}
    g = goalie_starts(con, pid, d)
    l10, std = g.tail(10), g[g.season == season]

    def sv(x):
        return x.saves.sum() / x.shots_against.sum() if len(x) and x.shots_against.sum() else None
    return {"l10_n": len(l10), "gsax_l10": l10.gsax.sum() if len(l10) else None, "sv_l10": sv(l10),
            "std_n": len(std), "gsax_std": std.gsax.sum() if len(std) else None, "sv_std": sv(std)}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    p.add_argument("--home", required=True)
    p.add_argument("--away", required=True)
    p.add_argument("--date", help="game date YYYY-MM-DD (US/Eastern); default today")
    p.add_argument("--puckline", type=float, help="home puck line, -1.5 = home favoured")
    p.add_argument("--ml", type=float, nargs=2, metavar=("HOME", "AWAY"))
    p.add_argument("--total", type=float)
    p.add_argument("--home-goalie")
    p.add_argument("--away-goalie")
    p.add_argument("--db")
    a = p.parse_args()

    d = parse_date(a.date)
    season = season_of(d)
    home, away = resolve_team("nhl", a.home, season), resolve_team("nhl", a.away, season)
    con = connect(a.db)
    row = find_game(con, "nhl", home, away, d)

    print(f"\n{'=' * 72}\n  NHL PRE-GAME REPORT   {away} @ {home}   {d}  (season {season - 1}-{str(season)[2:]})")
    if a.puckline is not None:
        print(f"  Puck line: {home} {a.puckline:+g} / {away} {-a.puckline:+g}", end="")
    if a.ml:
        print(f"   ML: {home} {a.ml[0]:+g} / {away} {a.ml[1]:+g}", end="")
    if a.total is not None:
        print(f"   Total: {a.total:g}", end="")
    print(f"\n{'=' * 72}")

    # ── xG form ─────────────────────────────────────────────────────────────
    sep("Team xG form (MoneyPuck, games before this date)")
    fh, fa = team_form(con, home, season, d), team_form(con, away, season, d)
    print(f"  {'':22}{'last 10':>14}{'season':>14}{'prior season':>14}")
    for t, f in ((home, fh), (away, fa)):
        print(f"  {t} ({f['std']['games']} games this season)")
        for m, lab, spec in (("xgf_pct_5v5", "5v5 xGF%", ".3f"), ("corsi_pct_5v5", "5v5 Corsi%", ".3f"),
                             ("hd_share_5v5", "5v5 HD share", ".3f"), ("pp_xgf60", "PP xGF/60", ".2f"),
                             ("pk_xga60", "PK xGA/60", ".2f"), ("finishing_per_game", "goals - xG /gm", "+.2f"),
                             ("xgf_pct_all", "all-sit xGF%", ".3f")):
            print(f"    {lab:18}" + "".join(f"{fmt(f[w][m], spec):>14}" for w in ("l10", "std", "prior")))

    # ── goalies ─────────────────────────────────────────────────────────────
    sep("Starting goalies (GSAx approximate: team xGA share by ice time)")
    gh_id, gh_name, gh_src = pick_goalie(con, home, d, a.home_goalie, row.home_starter_id if row is not None else None)
    ga_id, ga_name, ga_src = pick_goalie(con, away, d, a.away_goalie, row.away_starter_id if row is not None else None)
    gh, ga = goalie_form(con, gh_id, season, d), goalie_form(con, ga_id, season, d)
    for t, nm, src, g in ((home, gh_name, gh_src, gh), (away, ga_name, ga_src, ga)):
        print(f"  {t} {nm} [{src}]: last {g['l10_n']} starts GSAx {fmt(g['gsax_l10'], '+.1f')}, sv% {fmt(g['sv_l10'], '.3f')};"
              f" season {g['std_n']} starts GSAx {fmt(g['gsax_std'], '+.1f')}, sv% {fmt(g['sv_std'], '.3f')}")

    # ── schedule ────────────────────────────────────────────────────────────
    sep("Schedule spots")
    venue = None
    if row is not None and pd.notna(row.espn_game_id):
        v = con.execute("select venue from main_staging.stg_nhl__games where game_id = ?", [row.espn_game_id]).fetchone()
        venue = v[0] if v else None
    site = site_coords(con, "nhl", venue, home, season)
    sh = schedule_features(con, "nhl", home, True, d, season, site)
    sa = schedule_features(con, "nhl", away, False, d, season, site)
    print_schedule(home, away, sh, sa, "puck line")

    # ── profiles ────────────────────────────────────────────────────────────
    sep(f"Team puck-line profiles (walk-forward, mart_nhl_team_profiles season {season})")
    print_profiles(con, "nhl", home, away, season, "puck line")

    # ── xG model vs the moneyline ───────────────────────────────────────────
    sep("xG model vs the market")
    neutral = bool(row.neutral_site) if row is not None else False
    hx = blend(fh["std"]["xgf_pct_all"], fh["std"]["games"], fh["prior"]["xgf_pct_all"])
    ax = blend(fa["std"]["xgf_pct_all"], fa["std"]["games"], fa["prior"]["xgf_pct_all"])
    hw, n = con.execute("""select count(*) filter (where home_score > away_score), count(*)
                           from main_marts.mart_nhl_game_features
                           where season < ? and not neutral_site and home_score <> away_score""", [season]).fetchone()
    hia = math.log(hw / (n - hw)) if n else None
    model_p = None
    if hx is not None and ax is not None and hia is not None:
        log5 = hx * (1 - ax) / (hx * (1 - ax) + ax * (1 - hx))
        model_p = 1 / (1 + math.exp(-(math.log(log5 / (1 - log5)) + (0 if neutral else hia))))
        print(f"  blended all-situations xGF%: {home} {hx:.3f}, {away} {ax:.3f}; home ice {hia:+.3f} log-odds"
              f" (earlier seasons){' (neutral site: not applied)' if neutral else ''}")
        print(f"  xG win probability: {home} {model_p:.1%}")
        if a.ml:
            mkt = novig_home(*a.ml)
            print(f"  no-vig market: {home} {mkt:.1%} -> model {'above' if model_p > mkt else 'below'} market by "
                  f"{abs(model_p - mkt):.1%}  (Phase 4: following or fading this gap had no edge)")
    else:
        print("  not enough data to rate both teams")
    gap = None if gh["gsax_l10"] is None or ga["gsax_l10"] is None else gh["gsax_l10"] - ga["gsax_l10"]
    if gap is not None:
        print(f"  goalie GSAx gap (last 10 starts): {gap:+.1f} toward {home if gap > 0 else away}"
              f"  (Phase 4: no edge; also depends on the starter being confirmed)")

    # ── rules and bottom line ───────────────────────────────────────────────
    sep("Rules")
    print("  BET WHEN / AUTO BET / NEVER BET: none. No NHL rule passed walk-forward validation (Phase 4),")
    print("  so no rule can fire. The closest call (rested team's ML vs a back-to-back opponent) was rejected.")
    spot = (sa["is_b2b"] and not sh["is_b2b"]) or (sh["is_b2b"] and not sa["is_b2b"])
    if spot:
        tired = away if sa["is_b2b"] else home
        print(f"  note: {tired} is on a back-to-back and its opponent is not (informational only)")
    sep("Bottom line")
    print("  NO BET  (no validated rule)")

    # ── cross-check and result ──────────────────────────────────────────────
    mine = {"home_xgf_pct_5v5_l10": fh["l10"]["xgf_pct_5v5"], "away_corsi_pct_5v5_std": fa["std"]["corsi_pct_5v5"],
            "home_pp_xgf60_prior": fh["prior"]["pp_xgf60"], "away_finishing_per_game_l10": fa["l10"]["finishing_per_game"],
            "home_days_rest": sh["days_rest"], "away_is_b2b": int(sa["is_b2b"]), "away_travel_miles": sa["travel_miles"],
            "model_home_win_prob": model_p}
    if row is not None and gh_src.startswith("actual"):
        mine.update(home_starter_gsax_l10=gh["gsax_l10"], away_starter_sv_pct_l10=ga["sv_l10"])
    check_against_mart(row, mine)
    if row is not None:
        res = f"{home} {int(row.home_score)} - {away} {int(row.away_score)}"
        res += " (SO)" if row.shootout else " (OT)" if row.went_ot else ""
        line = ""
        if pd.notna(row.home_spread) and row.is_standard_puck_line:
            line = (f"; puck line {home} {row.home_spread:+g} -> "
                    f"{'covered' if row.home_ats_margin > 0 else 'did not cover'}")
        print(f"  result (known only after the game): {res}{line}")


if __name__ == "__main__":
    main()
