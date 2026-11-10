#!/usr/bin/env python3
"""
nba_edge_validation.py

Walk-forward validation of NBA spread and total signals, modeled on
scripts/cfb_edge_validation.py (threshold sweeps, per-season consistency) and
scripts/backtest_walk_forward.py (choices made on prior seasons only).

Reads only main_marts.mart_nba_game_features (DuckDB read-only). For each candidate
and each season S, the threshold is chosen on seasons < S and the bets are scored
on S; only those out-of-sample bets are reported (engine: scripts/nba_nhl_edges.py).

Candidates (direction fixed in advance; the grid is what walk-forward chooses):
  model_spread_follow / _fade   |home_spread_edge| >= t: back (or fade) the side the
                                ratings model likes vs the market     t in 1..8 pts
  rest_away_2plus               away has 2+ more days of rest -> away (the lead in
                                docs/NBA_NHL_ATS_DATA.md)
  rest_diff_more_rested         rest difference >= t -> the more rested team
  b2b_vs_rested                 team on a back-to-back vs an opponent who is not ->
                                opponent; the tired team travelled >= t miles
  home_b2b_vs_rested_away       home on a B2B, away not -> away
  three_in_four_fade            team on its 3rd game in 4 nights, opponent not -> opponent
  away_long_travel              away travelled >= t miles -> home
  away_long_road_trip           away on game >= t of a road trip -> home
  ats_form_fade                 last-10 (covers - losses) gap >= t -> fade the hot team
  big_dog                       underdog of >= t points -> underdog
  total_model                   predicted total - market total >= t -> over, <= -t -> under
                                (bias removed using earlier seasons only)
  total_b2b_under               either team on a back-to-back -> under

Prices: ESPN rows carry the actual spread / total price; nba.historical_lines rows
(2007-08 to 2012-13 and gaps) have none and settle at -110.

Usage
  uv run python scripts/nba_edge_validation.py
  uv run python scripts/nba_edge_validation.py --db /path/to/copy.duckdb

Writes data/betting/nba_edges.csv and appends to data/betting/nba_trials.jsonl.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from nba_nhl_edges import DB_PATH, Candidate, baselines, load, new_run_id, report, walk_forward

MIN_TRAIN_BETS = 100
MIN_TRAIN_SEASONS = 3
MIN_OOS_BETS = 200      # the skill's bar for NBA
K_PRIOR = 10            # prior season weighted as 10 games, as in the mart


def side_where(df: pd.DataFrame, home: pd.Series, away: pd.Series,
               a: str = "home", b: str = "away") -> pd.Series:
    out = pd.Series(None, index=df.index, dtype=object)
    out[home.fillna(False).astype(bool)] = a
    out[away.fillna(False).astype(bool) & out.isna()] = b
    return out


def blend(df: pd.DataFrame, side: str, metric: str) -> pd.Series:
    std, prior = df[f"{side}_{metric}_std"], df[f"{side}_{metric}_prior"]
    gp = df[f"{side}_games_std"].fillna(0)
    both = (std * gp + prior * K_PRIOR) / (gp + K_PRIOR)
    return both.where(std.notna() & prior.notna(), std.fillna(prior))


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # predicted total from blended ratings and pace; bias removed with an
    # expanding mean over EARLIER seasons only
    pace = (blend(df, "home", "pace") + blend(df, "away", "pace")) / 2
    home_pp100 = (blend(df, "home", "ortg") + blend(df, "away", "drtg")) / 2
    away_pp100 = (blend(df, "away", "ortg") + blend(df, "home", "drtg")) / 2
    df["pred_total_raw"] = pace / 100 * (home_pp100 + away_pp100)
    resid = (df.pred_total_raw - df.total).groupby(df.season).agg(["sum", "count"]).sort_index()
    prior_bias = (resid["sum"].cumsum().shift(1) / resid["count"].cumsum().shift(1)).rename("total_bias")
    df = df.merge(prior_bias, left_on="season", right_index=True, how="left")
    df["total_edge"] = df.pred_total_raw - df.total_bias - df.total
    df["rest_diff"] = df.home_days_rest - df.away_days_rest            # > 0 home more rested
    df["ats_form_gap"] = ((df.home_ats_covers_l10 - df.home_ats_losses_l10)
                          - (df.away_ats_covers_l10 - df.away_ats_losses_l10))
    return df


def candidates() -> list[Candidate]:
    C = []
    e = "home_spread_edge"
    C.append(Candidate("model_spread_follow", "ratings_vs_market", "spread", [1, 2, 3, 4, 5, 6, 8],
                       lambda d, t: side_where(d, d[e] >= t, d[e] <= -t),
                       "ratings-implied spread differs from the market by >= t: bet the side the ratings like"))
    C.append(Candidate("model_spread_fade", "ratings_vs_market", "spread", [1, 2, 3, 4, 5, 6, 8],
                       lambda d, t: side_where(d, d[e] <= -t, d[e] >= t),
                       "ratings-implied spread differs from the market by >= t: bet against the ratings"))
    C.append(Candidate("rest_away_2plus", "rest", "spread", [None],
                       lambda d, _: side_where(d, pd.Series(False, index=d.index), d.rest_diff <= -2),
                       "away team has 2+ more days of rest: bet away"))
    C.append(Candidate("rest_diff_more_rested", "rest", "spread", [1, 2, 3],
                       lambda d, t: side_where(d, d.rest_diff >= t, d.rest_diff <= -t),
                       "rest difference >= t days: bet the more rested team"))
    C.append(Candidate("b2b_vs_rested", "back_to_back", "spread", [0, 500, 1000],
                       lambda d, t: side_where(
                           d, d.away_is_b2b & ~d.home_is_b2b & (d.away_travel_miles.fillna(0) >= t),
                           d.home_is_b2b & ~d.away_is_b2b & (d.home_travel_miles.fillna(0) >= t)),
                       "team on a back-to-back (after travelling >= t miles) vs an opponent who is not: bet the opponent"))
    C.append(Candidate("home_b2b_vs_rested_away", "back_to_back", "spread", [None],
                       lambda d, _: side_where(d, pd.Series(False, index=d.index),
                                               d.home_is_b2b & ~d.away_is_b2b & (d.away_days_rest >= 1)),
                       "home on a back-to-back, away rested 1+ days: bet away"))
    C.append(Candidate("three_in_four_fade", "back_to_back", "spread", [None],
                       lambda d, _: side_where(d, d.away_is_3in4 & ~d.home_is_3in4, d.home_is_3in4 & ~d.away_is_3in4),
                       "team on its 3rd game in 4 nights, opponent not: bet the opponent"))
    C.append(Candidate("away_long_travel", "travel", "spread", [500, 1000, 1500, 2000],
                       lambda d, t: side_where(d, d.away_travel_miles >= t, pd.Series(False, index=d.index)),
                       "away team travelled >= t miles since its last game: bet home"))
    C.append(Candidate("away_long_road_trip", "travel", "spread", [3, 4, 5, 6],
                       lambda d, t: side_where(d, d.away_road_trip_game >= t, pd.Series(False, index=d.index)),
                       "away team on game >= t of a road trip: bet home"))
    C.append(Candidate("ats_form_fade", "ats_form", "spread", [4, 6, 8],
                       lambda d, t: side_where(d, d.ats_form_gap <= -t, d.ats_form_gap >= t),
                       "last-10 ATS (covers - losses) gap >= t: bet against the hot team"))
    C.append(Candidate("big_dog", "line_size", "spread", [7, 9, 11, 13],
                       lambda d, t: side_where(d, d.home_spread >= t, d.home_spread <= -t),
                       "underdog of >= t points: bet the underdog"))
    C.append(Candidate("total_model", "totals", "total", [2, 4, 6, 8, 10],
                       lambda d, t: side_where(d, d.total_edge >= t, d.total_edge <= -t, "over", "under"),
                       "ratings/pace predicted total (bias from earlier seasons removed) vs market >= t: over / under"))
    C.append(Candidate("total_b2b_under", "totals", "total", [None],
                       lambda d, _: side_where(d, pd.Series(False, index=d.index), d.home_is_b2b | d.away_is_b2b,
                                               "over", "under"),
                       "either team on a back-to-back: under"))
    return C


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    p.add_argument("--db", default=str(DB_PATH))
    a = p.parse_args()
    df = prepare(load("nba", a.db))
    run_id = new_run_id()
    lined = df[df.home_spread.notna()]
    print(f"NBA: {len(df):,} games, {len(lined):,} with a spread, seasons {df.season.min()}-{df.season.max()}; "
          f"baseline home ATS {100 * (lined.home_ats_margin > 0).sum() / (lined.home_ats_margin != 0).sum():.1f}%")
    baselines(df, ["spread", "total"])
    res, oos = walk_forward(df, candidates(), "nba", MIN_TRAIN_BETS, MIN_TRAIN_SEASONS, MIN_OOS_BETS, run_id)
    report(res, oos, "nba", MIN_OOS_BETS, len(df), run_id)


if __name__ == "__main__":
    main()
