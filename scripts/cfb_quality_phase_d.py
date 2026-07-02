#!/usr/bin/env python3
"""
cfb_quality_phase_d.py

Phase D — Repeatable validation harness for the Quality-of-Win system.

Per design v5 (docs/cfb_quality/QUALITY_OF_WIN_DESIGN.md):
  - Stage 1: Does live_football_strength / preseason_quality predict
    FOOTBALL outcomes (future scoring margin)? No ATS data here.
  - Stage 2: Does off_vs_preseason or market_outperformance_ema predict
    future ATS outcomes (spread cover rate, ROI)?
  - Both stages are pre-registered and run together in one pass.
  - The locked holdout (2026) is never touched by this script.
  - All parameters below are the pre-registered configuration.
    Do not change them and re-run as if the result is a fresh test.

SEASON CLASSIFICATION (from CFB_QUALITY_DATA_CONTRACT.md §8):
  2021-2023: dev / previously_examined
  2024-2025: parameter_selection
  2026: future_live_holdout -- never queried by this script

PRE-REGISTERED PRIMARY METRICS:
  Stage 1: Pearson correlation of signal with next-week scoring margin
  Stage 2: Spearman correlation of signal with next-week spread cover (0/1)
           ROI at -110 juice for picks where signal exceeds threshold
           Cover rate by signal quintile

Run: python3 scripts/cfb_quality_phase_d.py
     python3 scripts/cfb_quality_phase_d.py --season-set dev
     python3 scripts/cfb_quality_phase_d.py --season-set param
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import duckdb
import pandas as pd
import numpy as np

DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")

# ── Season classification (never touch holdout) ───────────────────────
DEV_SEASONS              = [2021, 2022, 2023]
PARAMETER_SELECTION      = [2024, 2025]
HOLDOUT                  = [2026]  # NEVER QUERIED

FBS = ('SEC','Big Ten','Big 12','ACC','Pac-12','American Athletic',
       'Mountain West','Conference USA','Mid-American','Sun Belt',
       'FBS Independents')

# ── Pre-registered config ─────────────────────────────────────────────
# These are locked. Running with different values produces a different
# experiment, not a re-run of this one.
LOOKBACK_WEEKS   = 4    # how many prior weeks of signal to average
MIN_GAMES_PLAYED = 4    # minimum games before signal is considered reliable
SIGNAL_THRESHOLD = 0.15 # minimum abs(off_vs_preseason) to be considered
                         # a meaningful divergence from preseason quality


def connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(DB_PATH, read_only=True)


def load_live_strength(con, seasons: list[int]) -> pd.DataFrame:
    """Pull live strength ratings for the given seasons."""
    season_list = ','.join(str(s) for s in seasons)
    return con.execute(f"""
        SELECT
            team, season, week,
            live_off_strength,
            live_def_strength,
            market_outperformance_ema,
            off_vs_preseason,
            def_vs_preseason
        FROM main_marts.mart_cfb_live_strength
        WHERE season IN ({season_list})
        ORDER BY team, season, week
    """).df()


def load_qualifying_game_ids(con, seasons: list[int]) -> set:
    """
    Pull game_ids that the existing betting model would score (ppa_gap exists,
    conference eligible). This restricts Stage 2 to games the model actually
    considers, testing incremental value rather than signal over all FBS games.
    """
    season_list = ','.join(str(s) for s in seasons)
    df = con.execute(f"""
        SELECT DISTINCT game_id
        FROM main_marts.mart_cfbd_game_context
        WHERE season IN ({season_list})
          AND off_ppa_gap IS NOT NULL
          AND abs(cast(off_ppa_gap as double)) >= 0.15
          AND home_conference IN {FBS}
    """).df()
    return set(df['game_id'].tolist())


def load_game_outcomes(con, seasons: list[int],
                       qualifying_ids: set | None = None) -> pd.DataFrame:
    """Pull game outcomes for correlation targets."""
    season_list = ','.join(str(s) for s in seasons)
    df = con.execute(f"""
        SELECT
            home_team, away_team, season, week,
            game_id,
            home_score, away_score,
            cast(spread as double) as spread,
            spread_covered, spread_push,
            home_conference
        FROM main_marts.mart_cfbd_line_accuracy
        WHERE season IN ({season_list})
          AND home_score IS NOT NULL
          AND spread IS NOT NULL
          AND home_conference IN {FBS}
        ORDER BY season, week
    """).df()
    if qualifying_ids is not None:
        df = df[df['game_id'].isin(qualifying_ids)]
        print(f"  Filtered to {len(df):,} model-qualifying games "
              f"(from {con.execute(f'SELECT count(distinct game_id) FROM main_marts.mart_cfbd_line_accuracy WHERE season IN ({season_list}) AND home_conference IN {FBS} AND spread IS NOT NULL').fetchone()[0]:,} total)")
    return df


def build_signal_outcome_pairs(
    strength_df: pd.DataFrame,
    outcomes_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    For each game, pair the pregame live strength signal (entering that week)
    with the actual game outcome.

    Signal: the live_off_strength and market_outperformance_ema from the
    week BEFORE the game (pregame, so no leakage).

    Target 1 (Stage 1): actual_margin vs expected_margin (spread residual)
    Target 2 (Stage 2): spread_covered (0/1)
    """
    rows = []
    for _, game in outcomes_df.iterrows():
        season = int(game['season'])
        week   = int(game['week'])
        spread = float(game['spread'])

        for team, is_home in [(game['home_team'], True), (game['away_team'], False)]:
            # Get pregame signal: most recent live strength row BEFORE this week
            team_ratings = strength_df[
                (strength_df['team']   == team) &
                (strength_df['season'] == season) &
                (strength_df['week']   < week)
            ].sort_values('week')

            if len(team_ratings) < MIN_GAMES_PLAYED:
                continue  # not enough games to have a reliable signal

            latest = team_ratings.iloc[-1]

            # Actual margin from this team's perspective
            if is_home:
                actual_margin   = float(game['home_score']) - float(game['away_score'])
                expected_margin = -spread  # spread is home-perspective
                covered = bool(game['spread_covered']) if not bool(game['spread_push']) else None
            else:
                actual_margin   = float(game['away_score']) - float(game['home_score'])
                expected_margin = spread
                covered = (not bool(game['spread_covered'])) if not bool(game['spread_push']) else None

            if covered is None:
                continue  # push

            spread_residual = actual_margin - expected_margin

            rows.append({
                'team':                     team,
                'season':                   season,
                'week':                     week,
                'is_home':                  is_home,
                'abs_spread':               abs(spread),
                'live_off_strength':        float(latest['live_off_strength']),
                'live_def_strength':        float(latest['live_def_strength']),
                'market_outperformance_ema': float(latest['market_outperformance_ema']),
                'off_vs_preseason':         float(latest['off_vs_preseason']),
                'def_vs_preseason':         float(latest['def_vs_preseason']),
                'actual_margin':            actual_margin,
                'expected_margin':          expected_margin,
                'spread_residual':          spread_residual,
                'covered':                  int(covered),
            })

    return pd.DataFrame(rows)


def run_stage_1(pairs: pd.DataFrame, label: str) -> None:
    """
    Stage 1: Does live_football_strength predict football outcomes?
    Uses continuous spread_residual (actual - expected margin) as target.
    No ATS win/loss binary outcome here -- continuous target preserves info.
    """
    print(f"\n{'='*65}")
    print(f"STAGE 1 — Football quality predicts future margin")
    print(f"Season set: {label}  |  n={len(pairs):,} game-team pairs")
    print(f"{'='*65}")

    signals = {
        'live_off_strength':         'Live offensive strength (Phase C)',
        'off_vs_preseason':          'Off drift from preseason (Phase C)',
        'market_outperformance_ema': 'Market outperformance EMA (Phase C)',
    }

    for col, name in signals.items():
        r = pairs[col].corr(pairs['spread_residual'])
        print(f"  {name:<42} r={r:+.3f}")

    print()
    print("  Baseline (abs_spread as noise control):")
    r_spread = pairs['abs_spread'].corr(pairs['spread_residual'])
    print(f"  {'abs_spread (should be ~0)':<42} r={r_spread:+.3f}")


def run_stage_2(pairs: pd.DataFrame, label: str) -> None:
    """
    Stage 2: Does the signal predict ATS outcomes?
    Primary: Spearman correlation with cover (0/1)
    Secondary: cover rate and ROI by signal quintile
    """
    print(f"\n{'='*65}")
    print(f"STAGE 2 — Signal predicts ATS outcomes")
    print(f"Season set: {label}  |  n={len(pairs):,} game-team pairs")
    print(f"{'='*65}")

    signals = {
        'live_off_strength':         'Live offensive strength',
        'off_vs_preseason':          'Off drift from preseason',
        'market_outperformance_ema': 'Market outperformance EMA',
    }

    for col, name in signals.items():
        # Spearman correlation with binary cover
        score_ranks  = pairs[col].rank()
        cover_ranks  = pairs['covered'].rank()
        spearman = score_ranks.corr(cover_ranks)
        cover_rate = pairs['covered'].mean() * 100
        print(f"  {name:<42} spearman={spearman:+.3f}  overall cover={cover_rate:.1f}%")

    print()
    print("  Cover rate by off_vs_preseason quintile:")
    print("  (Q1=most negative drift, Q5=most positive drift)")
    pairs['quintile'] = pd.qcut(pairs['off_vs_preseason'], q=5,
                                 labels=['Q1','Q2','Q3','Q4','Q5'])
    quintile_stats = pairs.groupby('quintile', observed=True).agg(
        n=('covered','count'),
        wins=('covered','sum'),
    ).reset_index()
    quintile_stats['cover_pct'] = (quintile_stats['wins'] / quintile_stats['n'] * 100).round(1)
    quintile_stats['roi'] = (
        (quintile_stats['wins'] * 0.909 - (quintile_stats['n'] - quintile_stats['wins']))
        / quintile_stats['n'] * 100
    ).round(1)
    print(quintile_stats.to_string(index=False))

    print()
    print("  Cover rate by market_outperformance_ema quintile:")
    pairs['mkt_quintile'] = pd.qcut(pairs['market_outperformance_ema'], q=5,
                                     labels=['Q1','Q2','Q3','Q4','Q5'])
    mkt_stats = pairs.groupby('mkt_quintile', observed=True).agg(
        n=('covered','count'),
        wins=('covered','sum'),
    ).reset_index()
    mkt_stats['cover_pct'] = (mkt_stats['wins'] / mkt_stats['n'] * 100).round(1)
    mkt_stats['roi'] = (
        (mkt_stats['wins'] * 0.909 - (mkt_stats['n'] - mkt_stats['wins']))
        / mkt_stats['n'] * 100
    ).round(1)
    print(mkt_stats.to_string(index=False))


def run(season_set: str = 'dev', model_qualifying: bool = False) -> None:
    if season_set == 'dev':
        seasons = DEV_SEASONS
        label   = 'Dev (2021-2023)'
    elif season_set == 'param':
        seasons = PARAMETER_SELECTION
        label   = 'Parameter-selection (2024-2025)'
    elif season_set == 'holdout':
        print("ERROR: holdout seasons (2026) are locked.")
        print("Run this on dev or param seasons only until Stage 2 is")
        print("fully pre-registered and both stages are ready to run once.")
        sys.exit(1)
    else:
        print(f"Unknown season set: {season_set}. Use 'dev' or 'param'.")
        sys.exit(1)

    con = connect()
    print(f"Loading live strength for seasons {seasons}...")
    strength_df = load_live_strength(con, seasons)
    print(f"Loading game outcomes for seasons {seasons}...")

    qualifying_ids = None
    if model_qualifying:
        print("  Restricting to model-qualifying games (PPA gap >= 0.15, conference eligible)...")
        qualifying_ids = load_qualifying_game_ids(con, seasons)

    outcomes_df = load_game_outcomes(con, seasons, qualifying_ids)
    con.close()

    filter_label = " [model-qualifying games only]" if model_qualifying else " [all FBS games]"
    print(f"Building signal-outcome pairs (min {MIN_GAMES_PLAYED} games played)...")
    pairs = build_signal_outcome_pairs(strength_df, outcomes_df)
    print(f"Pairs built: {len(pairs):,}")

    run_stage_1(pairs, label + filter_label)
    run_stage_2(pairs, label + filter_label)

    print(f"\n{'='*65}")
    print("INTERPRETATION NOTES")
    print(f"{'='*65}")
    print("Stage 1 target: Pearson r with spread_residual (continuous margin)")
    print("  r > 0.10: meaningful football quality signal")
    print("  r > 0.20: strong signal worth carrying into Stage 2")
    print()
    print("Stage 2 target: Spearman r with cover (0/1 binary)")
    print("  Meaningful threshold: Q5 cover rate > Q1 by >10 percentage points")
    print("  AND sustained across both dev and param-selection seasons")
    print("  before this signal is considered for score_game() integration")
    print()
    print("HOLDOUT STATUS: 2026 seasons NOT touched by this script.")
    print("Holdout will be run ONCE after all parameters are frozen,")
    print("with both Stage 1 and Stage 2 pre-registered and run together.")


def main() -> int:
    p = argparse.ArgumentParser(description="Phase D quality system validation")
    p.add_argument('--season-set', default='dev',
                   choices=['dev','param','holdout'],
                   help='Which season set to validate against')
    p.add_argument('--model-qualifying', action='store_true',
                   help='Restrict to games the existing model would consider '
                        '(PPA gap >= 0.15, conference eligible). Tests incremental '
                        'value within the model\'s natural scope rather than over '
                        'all FBS games.')
    args = p.parse_args()
    run(args.season_set, args.model_qualifying)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
