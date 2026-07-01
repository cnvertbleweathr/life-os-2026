#!/usr/bin/env python3
"""
score_calibration.py

Answers the question: does model_score actually discriminate?
If picks scored 85+ cover at the same rate as picks scored 70-74,
the scoring scale is cosmetic. If higher bins cover materially more,
the model is doing something real.

Uses mart_cfbd_line_accuracy (historical ground truth, 2021-2025) joined
against a replay of score_game() on the same games. This is the same
population the walk-forward backtest used -- NOT the 2026 holdout.

Output: per-bin table of n, wins, cover_rate, roi at -110.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import duckdb
import pandas as pd
from backtest_walk_forward import score_game, build_tiers

DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")

SCORE_BINS = [
    (70, 74, "70-74"),
    (75, 79, "75-79"),
    (80, 84, "80-84"),
    (85, 89, "85-89"),
    (90, 99, "90-99"),
]


def run() -> None:
    con = duckdb.connect(DB_PATH, read_only=True)

    # Pull all qualifying historical games with real outcomes
    # Qualifying = would have passed the model's hard filters and publish bar
    # We re-score them here to get model_score, then bin them
    df = con.execute("""
        SELECT
            m.season, m.week, m.home_team, m.away_team,
            m.spread, m.over_under,
            m.off_ppa_gap, m.def_ppa_gap,
            m.home_off_success_rate, m.away_off_success_rate,
            m.home_def_success_rate, m.away_def_success_rate,
            m.home_def_havoc, m.away_def_havoc,
            m.returning_production_gap,
            m.recruiting_gap,
            m.spread_covered, m.spread_push, m.spread_result,
            m.home_conference
        FROM main_marts.mart_cfbd_game_context m
        WHERE m.spread IS NOT NULL
          AND m.spread_result IN ('covered', 'missed', 'push')
          AND m.season BETWEEN 2021 AND 2025
          AND m.home_conference IN (
              'SEC', 'Big Ten', 'Big 12', 'ACC', 'Pac-12',
              'American Athletic', 'Mountain West', 'Conference USA',
              'Mid-American', 'Sun Belt', 'FBS Independents'
          )
    """).df()
    con.close()

    print(f"Loaded {len(df):,} historical games to score")

    scored_rows = []
    for season in sorted(df["season"].unique()):
        season_df = df[df["season"] == season]
        # Build tiers using only prior seasons (same walk-forward discipline)
        tcon = duckdb.connect(DB_PATH, read_only=True)
        tiers = build_tiers(tcon, season)
        sp_df = tcon.execute("SELECT team, season, rating FROM cfbd.sp_ratings").df()
        coaches_df = tcon.execute("SELECT school AS team, year AS season, full_name AS coach FROM cfbd.coaches").df()
        tcon.close()

        prior_sp = {(r["team"], int(r["season"])): float(r["rating"]) for _, r in sp_df.iterrows()}
        curr = coaches_df[coaches_df["season"] == season]
        prev = coaches_df[coaches_df["season"] == season - 1]
        merged = curr.merge(prev, on="team", suffixes=("_c", "_p"))
        coach_changes = set(merged[merged["coach_c"] != merged["coach_p"]]["team"])

        for _, row in season_df.iterrows():
            model_score, edges, warnings = score_game(row, tiers, coach_changes, prior_sp)
            n_edges = len(edges)
            if model_score < 70 or n_edges < 4:
                continue
            # Determine which side the model bet
            ppa_gap = row.get("off_ppa_gap")
            if ppa_gap is None:
                continue
            bet_home = ppa_gap > 0
            if bool(row["spread_push"]):
                outcome = "push"
            elif bet_home:
                outcome = "win" if bool(row["spread_covered"]) else "loss"
            else:
                outcome = "win" if not bool(row["spread_covered"]) else "loss"

            scored_rows.append({
                "season": season,
                "model_score": model_score,
                "outcome": outcome,
            })

    if not scored_rows:
        print("No qualifying scored games found -- check mart population")
        return

    scored = pd.DataFrame(scored_rows)
    print(f"Qualifying picks scored: {len(scored):,}")
    print()

    print(f"{'Bin':<10} {'N':>6} {'Wins':>6} {'Losses':>6} {'Pushes':>6} {'Cover%':>8} {'ROI%':>8}")
    print("-" * 58)

    total_n = total_wins = total_losses = 0
    for lo, hi, label in SCORE_BINS:
        bin_df = scored[(scored["model_score"] >= lo) & (scored["model_score"] <= hi)]
        n = len(bin_df)
        if n == 0:
            continue
        wins    = (bin_df["outcome"] == "win").sum()
        losses  = (bin_df["outcome"] == "loss").sum()
        pushes  = (bin_df["outcome"] == "push").sum()
        gradeable = wins + losses
        cover_pct = wins / gradeable * 100 if gradeable > 0 else 0
        roi = (wins * 0.909 - losses) / gradeable * 100 if gradeable > 0 else 0
        total_n += n; total_wins += wins; total_losses += losses
        print(f"{label:<10} {n:>6} {wins:>6} {losses:>6} {pushes:>6} {cover_pct:>7.1f}% {roi:>7.1f}%")

    print("-" * 58)
    gradeable = total_wins + total_losses
    cover_pct = total_wins / gradeable * 100 if gradeable > 0 else 0
    roi = (total_wins * 0.909 - total_losses) / gradeable * 100 if gradeable > 0 else 0
    print(f"{'TOTAL':<10} {total_n:>6} {total_wins:>6} {total_losses:>6} {'':>6} {cover_pct:>7.1f}% {roi:>7.1f}%")
    print()
    print("Note: model_score is an ordinal ranking signal, NOT a probability.")
    print("A meaningful model should show rising cover% as score increases.")
    print("If all bins cluster near 50-55%, the scoring scale is not discriminating.")


if __name__ == "__main__":
    run()
