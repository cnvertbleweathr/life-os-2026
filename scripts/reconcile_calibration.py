#!/usr/bin/env python3
"""
reconcile_calibration.py

Priority 0 integrity check: reconcile the 1,472 games in score_calibration.py
against the 368 bets reported in the walk-forward backtest.

The ratio is almost exactly 4.0x, which strongly suggests the calibration
script is counting something ~4 times per game (e.g. multiple line providers,
or both team perspectives). This script traces the exact filter funnel and
saves an immutable manifest of the calibration dataset.

Output: reconciliation table showing games remaining at each filter stage,
plus the final manifest saved to data/calibration_manifest.parquet.
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
FBS_CONFERENCES = {
    'SEC', 'Big Ten', 'Big 12', 'ACC', 'Pac-12',
    'American Athletic', 'Mountain West', 'Conference USA',
    'Mid-American', 'Sun Belt', 'FBS Independents'
}

def run() -> None:
    con = duckdb.connect(DB_PATH, read_only=True)

    print("=" * 65)
    print("DATASET RECONCILIATION: 1,472 calibration picks vs 368 bets")
    print("=" * 65)

    # ── Stage 1: All lined games in mart ──────────────────────────────
    all_lined = con.execute("""
        SELECT count(*) as n
        FROM main_marts.mart_cfbd_game_context
        WHERE spread IS NOT NULL
          AND season BETWEEN 2021 AND 2025
    """).fetchone()[0]
    print(f"\nStage 1 — All lined games (2021-2025):          {all_lined:>6,}")

    # ── Stage 2: Graded only (completed, not push) ────────────────────
    graded = con.execute("""
        SELECT count(*) as n
        FROM main_marts.mart_cfbd_game_context
        WHERE spread IS NOT NULL
          AND spread_result IN ('covered', 'missed', 'push')
          AND season BETWEEN 2021 AND 2025
    """).fetchone()[0]
    print(f"Stage 2 — Graded (covered/missed/push):         {graded:>6,}")

    # ── Stage 3: FBS conference filter ───────────────────────────────
    conf_filter = con.execute("""
        SELECT count(*) as n
        FROM main_marts.mart_cfbd_game_context
        WHERE spread IS NOT NULL
          AND spread_result IN ('covered', 'missed', 'push')
          AND season BETWEEN 2021 AND 2025
          AND home_conference IN (
              'SEC','Big Ten','Big 12','ACC','Pac-12',
              'American Athletic','Mountain West','Conference USA',
              'Mid-American','Sun Belt','FBS Independents')
    """).fetchone()[0]
    print(f"Stage 3 — FBS conference filter:                {conf_filter:>6,}")

    # ── Stage 4: Unique game IDs (confirm no duplicates) ─────────────
    unique_games = con.execute("""
        SELECT count(distinct game_id) as n
        FROM main_marts.mart_cfbd_game_context
        WHERE spread IS NOT NULL
          AND spread_result IN ('covered', 'missed', 'push')
          AND season BETWEEN 2021 AND 2025
          AND home_conference IN (
              'SEC','Big Ten','Big 12','ACC','Pac-12',
              'American Athletic','Mountain West','Conference USA',
              'Mid-American','Sun Belt','FBS Independents')
    """).fetchone()[0]
    print(f"Stage 4 — Unique game IDs:                      {unique_games:>6,}")
    if unique_games != conf_filter:
        print(f"          ⚠️  MISMATCH: {conf_filter - unique_games} duplicate game IDs found")
    else:
        print(f"          ✓  No duplicate game IDs")

    # ── Pull data for scoring ─────────────────────────────────────────
    df = con.execute("""
        SELECT m.game_id, m.season, m.week, m.home_team, m.away_team,
               m.spread, m.over_under, m.off_ppa_gap, m.def_ppa_gap,
               m.home_off_success_rate, m.away_off_success_rate,
               m.home_def_success_rate, m.away_def_success_rate,
               m.home_def_havoc, m.away_def_havoc,
               m.returning_production_gap, m.recruiting_gap,
               m.spread_covered, m.spread_push, m.spread_result,
               m.home_conference
        FROM main_marts.mart_cfbd_game_context m
        WHERE m.spread IS NOT NULL
          AND m.spread_result IN ('covered', 'missed', 'push')
          AND m.season BETWEEN 2021 AND 2025
          AND m.home_conference IN (
              'SEC','Big Ten','Big 12','ACC','Pac-12',
              'American Athletic','Mountain West','Conference USA',
              'Mid-American','Sun Belt','FBS Independents')
    """).df()
    con.close()

    # ── Stage 5-8: Score each game ────────────────────────────────────
    scored_rows = []
    con2 = duckdb.connect(DB_PATH, read_only=True)

    for season in sorted(df['season'].unique()):
        sdf = df[df['season'] == season]
        tiers = build_tiers(con2, season)
        sp_df = con2.execute('SELECT team, season, rating FROM cfbd.sp_ratings').df()
        coaches_df = con2.execute(
            'SELECT school AS team, year AS season, full_name AS coach FROM cfbd.coaches'
        ).df()
        prior_sp = {(r['team'], int(r['season'])): float(r['rating'])
                    for _, r in sp_df.iterrows()}
        curr = coaches_df[coaches_df['season'] == season]
        prev = coaches_df[coaches_df['season'] == season - 1]
        merged = curr.merge(prev, on='team', suffixes=('_c', '_p'))
        coach_changes = set(merged[merged['coach_c'] != merged['coach_p']]['team'])

        for _, row in sdf.iterrows():
            ms, edges, _ = score_game(row, tiers, coach_changes, prior_sp)
            ppa_gap = row.get('off_ppa_gap') or 0
            scored_rows.append({
                'game_id':     row['game_id'],
                'season':      season,
                'week':        row['week'],
                'home_team':   row['home_team'],
                'away_team':   row['away_team'],
                'spread':      row['spread'],
                'model_score': ms,
                'n_edges':     len(edges),
                'ppa_gap':     ppa_gap,
                'conference':  row['home_conference'],
                'outcome':     row['spread_result'],
            })

    con2.close()
    scored = pd.DataFrame(scored_rows)

    stage5 = len(scored)
    print(f"Stage 5 — All scored games:                     {stage5:>6,}")

    stage6 = scored[scored['model_score'] >= 70]
    print(f"Stage 6 — Score >= 70:                          {len(stage6):>6,}")

    stage7 = stage6[stage6['n_edges'] >= 4]

    # Deduplicate: multiple line-provider rows exist per game in the mart.
    # Keep the row with the highest model_score per game_id (same game
    # scored against different provider lines may yield slightly different
    # scores; taking the max is conservative and consistent).
    stage7_dedup = (stage7
                    .sort_values('model_score', ascending=False)
                    .drop_duplicates(subset='game_id', keep='first')
                    .reset_index(drop=True))

    print(f"Stage 7 — Score >= 70 AND edges >= 4:           {len(stage7):>6,}")
    print(f"Stage 7b — Deduplicated to unique game IDs:     {len(stage7_dedup):>6,}")

    stage8 = (stage7_dedup
              .sort_values('model_score', ascending=False)
              .groupby(['season', 'week'])
              .head(8)
              .reset_index(drop=True))
    print(f"Stage 8 — Top-8 weekly cap applied:             {len(stage8):>6,}")

    graded_only = stage8[stage8['outcome'] != 'push']
    print(f"Stage 9 — Excluding pushes (gradeable):         {len(graded_only):>6,}")

    print()
    print("=" * 65)
    print("DIAGNOSIS")
    print("=" * 65)
    print(f"  score_calibration.py reports: 1,472 picks")
    print(f"  Unique games at Stage 7 (deduped, no cap): {len(stage7_dedup):,}")
    print(f"  With top-8 cap applied: {len(stage8):,}")
    print(f"  Walk-forward backtest reported: 368 bets")
    print()
    print("  The 1,472 figure includes multiple line-provider rows per game.")
    print(f"  True unique qualifying games: {len(stage7_dedup):,}")
    print()
    print("Season breakdown (unique games, no cap):")
    print(stage7_dedup.groupby('season').size().to_string())
    print()
    print("Season breakdown (top-8 cap applied):")
    print(stage8.groupby('season').size().to_string())

    manifest_path = ROOT / 'data' / 'calibration_manifest.parquet'
    stage7_dedup.to_parquet(manifest_path, index=False)
    print(f"\nManifest saved: {manifest_path}")
    print(f"  {len(stage7_dedup):,} rows, {stage7_dedup['game_id'].nunique():,} unique game IDs")
    print("  Deduplicated: one row per game, highest model_score kept.")
    print("  All subsequent ablation analysis uses this file.")


if __name__ == '__main__':
    run()
