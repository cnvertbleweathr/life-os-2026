#!/usr/bin/env python3
"""
quality_signal_ablation.py

Tests whether off_vs_preseason adds value within the existing model's
actual published picks (after the spread-rule fix).

This is distinct from Phase D validation:
  Phase D: all model-qualifying game-team pairs
  This script: only the specific picks the model actually published

If outperforming-team picks cover at materially higher rates than
underperforming-team picks, off_vs_preseason earns consideration as
a filter or score modifier in score_game().

Thresholds used:
  Strong: off_vs_preseason > 0.15 (team clearly outperforming preseason)
  Weak:   off_vs_preseason < -0.15 (team clearly underperforming preseason)
  Neutral: between -0.15 and 0.15
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
FBS = ('SEC','Big Ten','Big 12','ACC','Pac-12','American Athletic',
       'Mountain West','Conference USA','Mid-American','Sun Belt',
       'FBS Independents')
DEV_SEASONS        = [2021, 2022, 2023]
PARAMETER_SELECTION = [2024, 2025]


def get_quality_signal(con, team: str, season: int, week: int) -> float | None:
    """Get the pregame off_vs_preseason for a team entering a given week."""
    result = con.execute("""
        SELECT off_vs_preseason
        FROM main_marts.mart_cfb_live_strength
        WHERE team = ? AND season = ? AND week < ?
        ORDER BY week DESC
        LIMIT 1
    """, [team, season, week]).fetchone()
    return float(result[0]) if result and result[0] is not None else None


def run() -> None:
    con = duckdb.connect(DB_PATH, read_only=True)

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
          AND m.home_conference IN {}
    """.format(FBS)).df()

    # Deduplicate -- one row per game_id, highest ppa_gap magnitude
    df = df.sort_values('off_ppa_gap', key=abs, ascending=False)
    df = df.drop_duplicates(subset='game_id', keep='first').reset_index(drop=True)

    rows = []
    for season in sorted(df['season'].unique()):
        sdf = df[df['season'] == season]
        tiers = build_tiers(con, season)
        sp_df = con.execute('SELECT team, season, rating FROM cfbd.sp_ratings').df()
        coaches_df = con.execute(
            'SELECT school AS team, year AS season, full_name AS coach FROM cfbd.coaches'
        ).df()
        prior_sp = {(r['team'], int(r['season'])): float(r['rating'])
                    for _, r in sp_df.iterrows()}
        curr = coaches_df[coaches_df['season'] == season]
        prev = coaches_df[coaches_df['season'] == season - 1]
        merged = curr.merge(prev, on='team', suffixes=('_c','_p'))
        coach_changes = set(merged[merged['coach_c'] != merged['coach_p']]['team'])

        for _, row in sdf.iterrows():
            ms, edges, _ = score_game(row, tiers, coach_changes, prior_sp)
            if ms < 70 or len(edges) < 4:
                continue

            ppa_gap  = float(row.get('off_ppa_gap') or 0)
            bet_home = ppa_gap > 0
            bet_team = row['home_team'] if bet_home else row['away_team']

            if bool(row['spread_push']):
                continue  # skip pushes
            if bet_home:
                outcome = 'win' if bool(row['spread_covered']) else 'loss'
            else:
                outcome = 'win' if not bool(row['spread_covered']) else 'loss'

            # Get pregame quality signal for the bet team
            signal = get_quality_signal(con, bet_team, int(row['season']), int(row['week']))

            rows.append({
                'game_id':    row['game_id'],
                'season':     season,
                'week':       row['week'],
                'bet_team':   bet_team,
                'model_score': ms,
                'outcome':    outcome,
                'signal':     signal,
            })

    con.close()

    picks = pd.DataFrame(rows)
    picks = picks.drop_duplicates(subset='game_id', keep='first')
    print(f"Published picks (after spread-rule fix): {len(picks):,}")
    print(f"With quality signal available: {picks['signal'].notna().sum():,}")
    picks = picks[picks['signal'].notna()]

    def stats(subset):
        wins = (subset['outcome'] == 'win').sum()
        n = len(subset)
        cover = wins / n * 100 if n > 0 else 0
        roi   = (wins * 0.909 - (n - wins)) / n * 100 if n > 0 else 0
        return n, wins, cover, roi

    print()
    print("=" * 65)
    print("OFF_VS_PRESEASON SIGNAL WITHIN PUBLISHED PICKS")
    print("=" * 65)

    for season_label, seasons in [
        ('Dev (2021-2023)',         DEV_SEASONS),
        ('Param (2024-2025)',       PARAMETER_SELECTION),
        ('All seasons (2021-2025)', DEV_SEASONS + PARAMETER_SELECTION),
    ]:
        subset = picks[picks['season'].isin(seasons)]
        strong  = subset[subset['signal'] >  0.15]
        neutral = subset[(subset['signal'] >= -0.15) & (subset['signal'] <= 0.15)]
        weak    = subset[subset['signal'] < -0.15]

        print(f"\n{season_label}:")
        print(f"  {'Category':<30} {'N':>5} {'Wins':>5} {'Cover%':>8} {'ROI%':>8}")
        print(f"  {'-'*54}")
        for label, grp in [
            ('Strong (signal > +0.15)',  strong),
            ('Neutral (-0.15 to +0.15)', neutral),
            ('Weak (signal < -0.15)',     weak),
            ('All published picks',       subset),
        ]:
            n, w, cov, roi = stats(grp)
            print(f"  {label:<30} {n:>5} {w:>5} {cov:>7.1f}% {roi:>7.1f}%")

    print()
    print("=" * 65)
    print("INTERPRETATION")
    print("=" * 65)
    print("If Strong > All > Weak by a meaningful margin (>5 pts) across")
    print("both dev and param-selection seasons: off_vs_preseason earns")
    print("consideration as a filter or score modifier in score_game().")
    print()
    print("If the pattern is noisy or reversed: the Phase D signal does")
    print("not translate to the published-pick population and should not")
    print("be added to the model without further investigation.")


if __name__ == '__main__':
    run()
