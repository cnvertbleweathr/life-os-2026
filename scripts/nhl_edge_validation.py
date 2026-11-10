#!/usr/bin/env python3
"""
nhl_edge_validation.py

Walk-forward validation of NHL moneyline, puck-line and total signals, modeled on
scripts/cfb_edge_validation.py and scripts/backtest_walk_forward.py.

Reads only main_marts.mart_nhl_game_features (DuckDB read-only). Lines exist from
2019-20, so with two training seasons the out-of-sample seasons are 2021-22 on.
For each candidate and season S the grid value is chosen on seasons < S and scored
on S; only those bets are reported (engine: scripts/nba_nhl_edges.py).

Puck-line bets use only standard +-1.5 lines whose sign agrees with the moneyline
favourite (is_standard_puck_line and line_consistent); a game won in OT or a
shootout is a one-goal game, which the scores already reflect.

Candidates (direction fixed; the grid is what walk-forward chooses):
  xg_ml_follow / _fade       |model - no-vig market| >= t on the moneyline: back / fade the model
  xg_puckline_follow         same signal, bet on the puck line
  goalie_gsax_ml             starter GSAx (last 10 starts) gap >= t -> the better goalie's ML
  goalie_svpct_ml            starter save% (last 10) gap >= t -> the better goalie's ML
  xg_and_goalie_agree_ml     model edge >= t and the better goalie on the same side
  puck_dog_band              the +1.5 side, its price in band t
  puck_fav_band              the -1.5 side, its price in band t
  ml_dog_band                the moneyline underdog, its price in band t
  b2b_vs_rested_ml           team on a back-to-back (travel >= t), opponent not -> opponent ML
  total_finishing_under      both teams' last-10 finishing (goals - xG per game) summed
                             >= t -> under, <= -t -> over (shooting luck regresses)
  total_special_teams_over   combined PP xGF/60 + opposing PK xGA/60 (season to date) >= t -> over

goalie_* candidates are flagged uses_goalie: the starter is usually but not
always known when the line is set.

Usage
  uv run python scripts/nhl_edge_validation.py
  uv run python scripts/nhl_edge_validation.py --db /path/to/copy.duckdb

Writes data/betting/nhl_edges.csv and appends to data/betting/nhl_trials.jsonl.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from nba_nhl_edges import DB_PATH, Candidate, baselines, load, log_once, new_run_id, novig, report, walk_forward

MIN_TRAIN_BETS = 60
MIN_TRAIN_SEASONS = 2
MIN_OOS_BETS = 150      # the skill's bar for NHL

PUCK_DOG_BANDS = [(-400, -250), (-250, -200), (-200, -170), (-170, -140), (-140, 300)]
PUCK_FAV_BANDS = [(100, 140), (140, 170), (170, 200), (200, 400)]
ML_DOG_BANDS = [(100, 130), (130, 160), (160, 200), (200, 500)]


def side_where(df, home, away, a="home", b="away") -> pd.Series:
    out = pd.Series(None, index=df.index, dtype=object)
    out[home.fillna(False).astype(bool)] = a
    out[away.fillna(False).astype(bool) & out.isna()] = b
    return out


def in_band(price: pd.Series, band) -> pd.Series:
    lo, hi = band
    return (price >= lo) & (price < hi)


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # puck-line bets only on standard, sign-consistent lines
    df["spread_valid"] = df.is_standard_puck_line.fillna(False) & df.line_consistent.fillna(True)
    df.loc[~df.spread_valid, "home_ats_margin"] = np.nan
    # model edge vs the OPENING moneyline (no vig)
    df["home_prob_edge_open"] = df.model_home_win_prob - novig(df.open_home_ml, df.open_away_ml)
    df["home_is_pl_dog"] = df.home_spread == 1.5
    df["away_is_pl_dog"] = df.home_spread == -1.5
    df["fin_sum_l10"] = df.home_finishing_per_game_l10 + df.away_finishing_per_game_l10
    df["st_sum"] = (df.home_pp_xgf60_std + df.away_pk_xga60_std) + (df.away_pp_xgf60_std + df.home_pk_xga60_std)
    return df


def candidates() -> list[Candidate]:
    C = []
    e = "home_prob_edge"
    xg_grid = [0.02, 0.04, 0.06, 0.08, 0.10]
    C.append(Candidate("xg_ml_follow", "xg_vs_market", "ml", xg_grid,
                       lambda d, t: side_where(d, d[e] >= t, d[e] <= -t),
                       "xG win probability differs from the no-vig moneyline by >= t: bet the model's side ML"))
    C.append(Candidate("xg_ml_fade", "xg_vs_market", "ml", xg_grid,
                       lambda d, t: side_where(d, d[e] <= -t, d[e] >= t),
                       "xG win probability differs from the no-vig moneyline by >= t: bet against the model ML"))
    C.append(Candidate("xg_puckline_follow", "xg_vs_market", "spread", xg_grid,
                       lambda d, t: side_where(d, d[e] >= t, d[e] <= -t),
                       "xG model edge >= t: bet the model's side on the puck line"))
    g = "gap_starter_gsax_l10"
    C.append(Candidate("goalie_gsax_ml", "goalie", "ml", [2, 4, 6, 8],
                       lambda d, t: side_where(d, d[g] >= t, d[g] <= -t),
                       "starting goalies' GSAx over their last 10 starts differ by >= t: bet the better goalie's ML",
                       uses_goalie=True))
    sv = "gap_starter_sv_pct_l10"
    C.append(Candidate("goalie_svpct_ml", "goalie", "ml", [0.01, 0.02, 0.03],
                       lambda d, t: side_where(d, d[sv] >= t, d[sv] <= -t),
                       "starters' save% over their last 10 starts differ by >= t: bet the better goalie's ML",
                       uses_goalie=True))
    C.append(Candidate("xg_and_goalie_agree_ml", "goalie", "ml", [0.02, 0.04, 0.06],
                       lambda d, t: side_where(d, (d[e] >= t) & (d[g] > 0), (d[e] <= -t) & (d[g] < 0)),
                       "xG model edge >= t and the better recent goalie on the same side: bet that side ML",
                       uses_goalie=True))
    C.append(Candidate("puck_dog_band", "price_band", "spread", PUCK_DOG_BANDS,
                       lambda d, b: side_where(d, d.home_is_pl_dog & in_band(d.home_spread_price, b),
                                               d.away_is_pl_dog & in_band(d.away_spread_price, b)),
                       "bet the +1.5 side when its price is in band t"))
    C.append(Candidate("puck_fav_band", "price_band", "spread", PUCK_FAV_BANDS,
                       lambda d, b: side_where(d, d.away_is_pl_dog & in_band(d.home_spread_price, b),
                                               d.home_is_pl_dog & in_band(d.away_spread_price, b)),
                       "bet the -1.5 side when its price is in band t"))
    C.append(Candidate("ml_dog_band", "price_band", "ml", ML_DOG_BANDS,
                       lambda d, b: side_where(d, (d.home_ml > 0) & in_band(d.home_ml, b) & (d.away_ml < 0),
                                               (d.away_ml > 0) & in_band(d.away_ml, b) & (d.home_ml < 0)),
                       "bet the moneyline underdog when its price is in band t"))
    C.append(Candidate("b2b_vs_rested_ml", "back_to_back", "ml", [0, 500],
                       lambda d, t: side_where(
                           d, d.away_is_b2b & ~d.home_is_b2b & (d.away_travel_miles.fillna(0) >= t),
                           d.home_is_b2b & ~d.away_is_b2b & (d.home_travel_miles.fillna(0) >= t)),
                       "team on a back-to-back (after >= t miles) vs a rested opponent: bet the opponent ML"))
    C.append(Candidate("total_finishing_under", "totals", "total", [0.3, 0.5, 0.8],
                       lambda d, t: side_where(d, d.fin_sum_l10 <= -t, d.fin_sum_l10 >= t, "over", "under"),
                       "both teams' last-10 goals minus xG per game sum to >= t: under (<= -t: over)"))
    C.append(Candidate("total_special_teams_over", "totals", "total", [28, 29, 30, 31],
                       lambda d, t: side_where(d, d.st_sum >= t, pd.Series(False, index=d.index), "over", "under"),
                       "combined PP xGF/60 + opposing PK xGA/60 (season to date) >= t: over"))
    # placed at the OPEN (opening moneylines with prices: 2023-24 on, so one test season)
    C.append(Candidate("b2b_vs_rested_ml_open", "back_to_back", "ml", [0, 500],
                       lambda d, t: side_where(
                           d, d.away_is_b2b & ~d.home_is_b2b & (d.away_travel_miles.fillna(0) >= t),
                           d.home_is_b2b & ~d.away_is_b2b & (d.home_travel_miles.fillna(0) >= t)),
                       "as b2b_vs_rested_ml, bet at the opening moneyline", placement="open",
                       # proposed after the close version's 2025-26 line movement was seen:
                       # its 2026 bets are not a clean holdout; 2026-27 is the first real test
                       discovered_in_sample=True))
    eo = "home_prob_edge_open"
    C.append(Candidate("xg_ml_follow_open", "xg_vs_market", "ml", xg_grid,
                       lambda d, t: side_where(d, d[eo] >= t, d[eo] <= -t),
                       "xG win probability vs the OPENING no-vig moneyline >= t: bet the model's side at the open",
                       placement="open"))
    return C


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    p.add_argument("--db", default=str(DB_PATH))
    a = p.parse_args()
    df = prepare(load("nhl", a.db))
    run_id = new_run_id()
    lined = df[df.home_ml.notna()]
    print(f"NHL: {len(df):,} games, {len(lined):,} with a moneyline (seasons {lined.season.min()}-{lined.season.max()}); "
          f"home ML win rate {100 * (lined.home_margin > 0).mean():.1f}%")
    log_once("nhl", "invalid_20261109T211031", [{
        "type": "invalid_run", "run_id": "20261109T211031", "league": "nhl",
        "reason": "moneylines included 3-way regulation prices (fixed in dbt/macros/espn_odds.sql); "
                  "exclude this run from trial counts"}])
    baselines(df, ["ml", "spread", "total"])
    res, oos = walk_forward(df, candidates(), "nhl", MIN_TRAIN_BETS, MIN_TRAIN_SEASONS, MIN_OOS_BETS, run_id)
    report(res, oos, "nhl", MIN_OOS_BETS, len(df), run_id)


if __name__ == "__main__":
    main()
