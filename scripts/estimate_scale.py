#!/usr/bin/env python3
"""
estimate_scale.py

Estimates the 'scale' parameter for Phase B's tanh result score from
dev seasons (2021-2023) only. This value is locked into the mart SQL.

Design v5 requirement: estimate from dev seasons using robust dispersion
(not ordinary stdev), lock before seeing parameter-selection results.

scale = median absolute deviation of (actual_margin - expected_margin)
across all FBS-vs-FBS dev-season games with a real reference line.

Once this value is confirmed, it gets hardcoded into
mart_cfb_game_market_residual.sql and never re-estimated.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import duckdb
import numpy as np

DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")
FBS = ('SEC','Big Ten','Big 12','ACC','Pac-12','American Athletic',
       'Mountain West','Conference USA','Mid-American','Sun Belt','FBS Independents')
DEV_SEASONS = [2021, 2022, 2023]


def run() -> None:
    con = duckdb.connect(DB_PATH, read_only=True)

    df = con.execute("""
        SELECT
            l.game_id, l.season,
            l.home_score, l.away_score,
            cast(l.spread as double) as spread,
            cast(l.over_under as double) as total
        FROM main_marts.mart_cfbd_line_accuracy l
        WHERE l.home_score IS NOT NULL
          AND l.away_score IS NOT NULL
          AND l.spread IS NOT NULL
          AND l.season IN ({})
          AND l.home_conference IN {}
    """.format(','.join(str(s) for s in DEV_SEASONS), FBS)).df()
    con.close()

    # Deduplicate: multiple provider rows per game -- use first row per game
    df = df.drop_duplicates(subset='game_id', keep='first')

    # Compute spread residual: actual_margin - expected_margin
    # expected_home_margin = -spread (spread is home perspective, negative = home favored)
    df['actual_margin']   = df['home_score'] - df['away_score']
    df['expected_margin'] = -df['spread']
    df['residual']        = df['actual_margin'] - df['expected_margin']

    n = len(df)
    mean_res    = df['residual'].mean()
    std_res     = df['residual'].std()
    mad         = (df['residual'] - df['residual'].median()).abs().median()
    # Normalized MAD: consistent estimator of stdev for normal distributions
    # MAD * 1.4826 ≈ stdev for a normal distribution
    mad_normalized = mad * 1.4826

    print("Phase B scale parameter estimation")
    print("Dev seasons only: 2021-2023")
    print("=" * 55)
    print(f"Games (deduplicated): {n:,}")
    print(f"Mean spread residual: {mean_res:.2f} pts")
    print(f"Stdev spread residual (ordinary): {std_res:.2f} pts")
    print(f"MAD (robust): {mad:.2f} pts")
    print(f"Normalized MAD (stdev-equivalent): {mad_normalized:.2f} pts")
    print()
    print("Recommended scale value: MAD = {:.1f}".format(round(mad, 1)))
    print()
    print("Rationale: MAD is robust to outlier games (blowouts, triple-OT,")
    print("etc.) that inflate ordinary stdev. The scale sets the point at")
    print("which tanh produces a 0.76-score (5 + 5*tanh(1) ≈ 9.2), so a")
    print("residual equal to 'scale' points is treated as a strong outperformance.")
    print()
    print("tanh behavior at key residual values:")
    for r in [-20, -10, -5, 0, 5, 10, 20]:
        score = 5 + 5 * np.tanh(r / round(mad, 1))
        print(f"  residual={r:+3d} pts → result_score={score:.2f}")
    print()
    print("This value should be hardcoded into mart_cfb_game_market_residual.sql.")
    print("Do not re-estimate from parameter-selection or holdout seasons.")
    print(f"Lock: scale = {round(mad, 1)}")


if __name__ == '__main__':
    run()
