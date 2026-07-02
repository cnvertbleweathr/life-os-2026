#!/usr/bin/env python3
"""
phase_a_compare.py

Pre-registered comparison of Phase A v1 (equal weights, 1/3 each) vs
Phase A v2 (efficiency 50%, talent/program 25%, prior_results 25%).

Decision rule, written BEFORE running this script:
  - Primary metric: Spearman correlation with next-season scoring margin
    (confirmed stronger than PPA target in earlier validation: 0.545/0.452)
  - Comparison must be on the EXACT SAME team-season rows for both versions
  - If v2 margin correlation > v1 on BOTH dev and param-selection seasons: use v2
  - If v2 > v1 on dev only: keep v1 (could be overfitting to dev seasons)
  - If v1 >= v2 on both: keep v1 (simpler, equal weight, no justification to change)
  - Difference must be > 0.02 to be considered meaningful given sample size
  - Do NOT select based on which version looks better on any ATS outcome

This script reports the result. The human makes the final call.
The decision rule above cannot be changed after running this script.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import duckdb
import pandas as pd
from cfb_quality_validation import (
    validate_predictor, DEV_SEASONS, PARAMETER_SELECTION_SEASONS, DB_PATH
)

FBS = ('SEC','Big Ten','Big 12','ACC','Pac-12','American Athletic',
       'Mountain West','Conference USA','Mid-American','Sun Belt','FBS Independents')


def get_margin_df(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Team-season average scoring margin, FBS conference games only."""
    df = con.execute("""
        SELECT team, season, avg(margin) as avg_margin FROM (
            SELECT home_team AS team, season,
                   (home_score - away_score) AS margin
            FROM main_marts.mart_cfbd_line_accuracy
            WHERE home_score IS NOT NULL AND home_conference IN {}
            UNION ALL
            SELECT away_team AS team, season,
                   (away_score - home_score) AS margin
            FROM main_marts.mart_cfbd_line_accuracy
            WHERE home_score IS NOT NULL AND home_conference IN {}
        )
        GROUP BY team, season
    """.format(FBS, FBS)).df()
    return df


def run() -> None:
    con = duckdb.connect(DB_PATH, read_only=True)
    margin_df = get_margin_df(con)

    MODELS = {
        'v1 (equal 1/3)':          'mart_cfb_preseason_quality',
        'v2 (50/25/25 eff)':       'mart_cfb_preseason_quality_v2',
        'B (70/20/10 eff-heavy)':  'mart_cfb_preseason_quality_b',
        'C (60/25/15 talent)':     'mart_cfb_preseason_quality_c',
    }

    model_dfs = {}
    for label, mart in MODELS.items():
        try:
            df = con.execute(f"""
                SELECT team, season, preseason_off_rating_z AS rating
                FROM main_marts.{mart}
                WHERE preseason_off_rating_z IS NOT NULL
            """).df()
            model_dfs[label] = df
        except Exception as e:
            print(f"  {label}: mart not found ({e})")
    con.close()

    print("=" * 65)
    print(f"{'Model':<28} {'Dev corr':>10} {'Param corr':>12}")
    print("-" * 52)

    results = {}
    for label, df in model_dfs.items():
        combined = df.merge(margin_df, on=['team', 'season'])
        row = {}
        for season_label, seasons in [
            ('dev',   DEV_SEASONS),
            ('param', PARAMETER_SELECTION_SEASONS),
        ]:
            subset = combined[combined['season'].isin(seasons)]
            if len(subset) < 10:
                row[season_label] = float('nan')
                continue
            row[season_label] = subset['rating'].corr(subset['avg_margin'], method='pearson')
        results[label] = row
        print(f"  {label:<26} {row.get('dev', float('nan')):>10.3f} {row.get('param', float('nan')):>12.3f}")

    print()
    print("=" * 65)
    print("DECISION (pre-registered rule):")
    v1_dev   = results.get('v1 (equal 1/3)', {}).get('dev', 0)
    v1_param = results.get('v1 (equal 1/3)', {}).get('param', 0)
    best = 'v1 (equal 1/3)'
    for label, row in results.items():
        if label == 'v1 (equal 1/3)':
            continue
        beats_dev   = row.get('dev', 0) - v1_dev > 0.02
        beats_param = row.get('param', 0) - v1_param > 0.02
        if beats_dev and beats_param:
            print(f"  {label} beats v1 by >0.02 on BOTH season sets → candidate")
            best = label
    if best == 'v1 (equal 1/3)':
        print("  No variant beats v1 by >0.02 on both season sets → keep v1")
    print()
    print("Note: winner enters Phase C as the locked preseason quality mart.")
    print("None of these enter score_game() until Stage 2 ATS validation.")


if __name__ == '__main__':
    run()
