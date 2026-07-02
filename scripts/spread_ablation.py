#!/usr/bin/env python3
"""
spread_ablation.py

Priority 2: Two controlled ablations of the spread-range scoring rule.

A) Fixed-cohort: same games as the calibration manifest, scores recalculated
   with spread points removed. Tests whether the rule distorts ordering of
   already-selected games without changing which games are selected.

B) Full-pipeline: re-run selection from scratch with spread rule disabled,
   allowing games to enter or leave. Tests what the actual published strategy
   would have done.

Must run reconcile_calibration.py first (needs calibration_manifest.parquet).
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import duckdb
import pandas as pd
from backtest_walk_forward import score_game, build_tiers

DB_PATH  = str(ROOT / "data" / "warehouse" / "ons.duckdb")
MANIFEST = ROOT / "data" / "calibration_manifest.parquet"


def score_game_no_spread_rule(row, tiers, coach_changes, prior_sp) -> tuple:
    """
    Wrapper: calls score_game() but zeroes out the spread-range contribution.
    We do this by post-processing: recompute the spread bonus that was added
    and subtract it. This avoids modifying score_game() itself.

    Spread rule logic from score_game() source:
      - abs_spread 3-7:   +10 ("prime")
      - abs_spread 7-10:  +8  ("solid")
      - abs_spread 14-17: -8
      - abs_spread 17-21: -12

    We identify the contribution and remove it.
    """
    ms, edges, warnings = score_game(row, tiers, coach_changes, prior_sp)

    spread = abs(float(row.get('spread') or 0))
    spread_contribution = 0
    if 3 <= spread <= 7:
        spread_contribution = 10
    elif 7 < spread <= 10:
        spread_contribution = 8
    elif 14 < spread <= 17:
        spread_contribution = -8
    elif 17 < spread <= 21:
        spread_contribution = -12

    ms_no_spread = ms - spread_contribution

    # Remove spread-related edge labels
    edges_no_spread = [e for e in edges if 'prime' not in str(e).lower()
                       and 'solid' not in str(e).lower()
                       and 'spread' not in str(e).lower()]

    return ms_no_spread, edges_no_spread, warnings


def cover_rate_table(df: pd.DataFrame) -> pd.DataFrame:
    bins = ['<70', '70-74', '75-79', '80-84', '85-89', '90-99']

    def bin_label(s):
        if s < 70:  return '<70'
        if s <= 74: return '70-74'
        if s <= 79: return '75-79'
        if s <= 84: return '80-84'
        if s <= 89: return '85-89'
        return '90-99'

    df = df.copy()
    df['bin'] = df['model_score'].apply(bin_label)
    rows = []
    for b in bins:
        g = df[(df['bin'] == b) & (df['outcome'].isin(['win', 'loss']))]
        if len(g) == 0:
            continue
        wins = (g['outcome'] == 'win').sum()
        rows.append({
            'bin': b, 'n': len(g), 'wins': wins,
            'cover_pct': round(wins / len(g) * 100, 1),
            'roi_pct': round((wins * 0.909 - (len(g) - wins)) / len(g) * 100, 1),
        })
    return pd.DataFrame(rows)


def run() -> None:
    if not MANIFEST.exists():
        print(f"ERROR: {MANIFEST} not found. Run reconcile_calibration.py first.")
        sys.exit(1)

    manifest = pd.read_parquet(MANIFEST)
    print(f"Manifest loaded: {len(manifest):,} games\n")

    # Pull full row data
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
        WHERE m.game_id IN ({})
    """.format(','.join(str(g) for g in manifest['game_id'].tolist()))).df()
    df = df.merge(manifest[['game_id', 'model_score']], on='game_id')

    # ── A: FIXED-COHORT ABLATION ──────────────────────────────────────
    print("=" * 65)
    print("A) FIXED-COHORT ABLATION: same games, spread rule removed")
    print("   Tests whether rule distorts ordering of already-selected games")
    print("=" * 65)

    orig_rows, ablated_rows = [], []
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
        merged = curr.merge(prev, on='team', suffixes=('_c', '_p'))
        coach_changes = set(merged[merged['coach_c'] != merged['coach_p']]['team'])

        for _, row in sdf.iterrows():
            ppa_gap = float(row.get('off_ppa_gap') or 0)
            bet_home = ppa_gap > 0

            def outcome_from(spread_covered, push, bet_home_):
                if bool(push): return 'push'
                if bet_home_: return 'win' if bool(spread_covered) else 'loss'
                return 'win' if not bool(spread_covered) else 'loss'

            out = outcome_from(row['spread_covered'], row['spread_push'], bet_home)

            ms_orig, _, _ = score_game(row, tiers, coach_changes, prior_sp)
            ms_abl, _, _  = score_game_no_spread_rule(row, tiers, coach_changes, prior_sp)

            orig_rows.append({'game_id': row['game_id'], 'season': season,
                               'model_score': ms_orig, 'outcome': out})
            ablated_rows.append({'game_id': row['game_id'], 'season': season,
                                 'model_score': ms_abl, 'outcome': out})

    orig_df    = pd.DataFrame(orig_rows)
    ablated_df = pd.DataFrame(ablated_rows)

    print("\nOriginal score calibration:")
    orig_table = cover_rate_table(orig_df)
    print(orig_table.to_string(index=False))

    print("\nWith spread rule removed (same games):")
    abl_table = cover_rate_table(ablated_df)
    print(abl_table.to_string(index=False))

    # Spearman correlation: does score rank correlate with future cover?
    # Use 1/0 for win/loss as continuous target
    # Spearman correlation using pandas rank (no scipy needed)
    gradeable = ablated_df[ablated_df['outcome'].isin(['win', 'loss'])].copy()
    gradeable['win'] = (gradeable['outcome'] == 'win').astype(float)
    score_ranks = gradeable['model_score'].rank()
    win_ranks   = gradeable['win'].rank()
    n = len(gradeable)
    spearman = score_ranks.corr(win_ranks) if n > 1 else float('nan')
    print(f"\nSpearman rank correlation (ablated score vs win): {spearman:.3f}")
    print("(Positive = higher score predicts win. Target > 0.0 for any useful signal.)")

    # ── B: FULL-PIPELINE ABLATION ─────────────────────────────────────
    print()
    print("=" * 65)
    print("B) FULL-PIPELINE ABLATION: re-run selection with spread rule disabled")
    print("   Tests what the published strategy would have looked like")
    print("=" * 65)

    # Load all lined games (not just the manifest)
    all_df = con.execute("""
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

    pipeline_rows = []
    for season in sorted(all_df['season'].unique()):
        sdf = all_df[all_df['season'] == season]
        tcon = duckdb.connect(DB_PATH, read_only=True)
        tiers = build_tiers(tcon, season)
        sp_df = tcon.execute('SELECT team, season, rating FROM cfbd.sp_ratings').df()
        coaches_df = tcon.execute(
            'SELECT school AS team, year AS season, full_name AS coach FROM cfbd.coaches'
        ).df()
        tcon.close()

        prior_sp = {(r['team'], int(r['season'])): float(r['rating'])
                    for _, r in sp_df.iterrows()}
        curr = coaches_df[coaches_df['season'] == season]
        prev = coaches_df[coaches_df['season'] == season - 1]
        merged = curr.merge(prev, on='team', suffixes=('_c', '_p'))
        coach_changes = set(merged[merged['coach_c'] != merged['coach_p']]['team'])

        week_picks = {}
        for _, row in sdf.iterrows():
            ms, edges, _ = score_game_no_spread_rule(row, tiers, coach_changes, prior_sp)
            if ms < 70 or len(edges) < 4:
                continue
            ppa_gap  = float(row.get('off_ppa_gap') or 0)
            bet_home = ppa_gap > 0
            if bool(row['spread_push']):
                out = 'push'
            elif bet_home:
                out = 'win' if bool(row['spread_covered']) else 'loss'
            else:
                out = 'win' if not bool(row['spread_covered']) else 'loss'

            week = int(row['week'])
            if week not in week_picks:
                week_picks[week] = []
            week_picks[week].append({'game_id': row['game_id'], 'season': season,
                                     'week': week, 'model_score': ms, 'outcome': out})

        # Apply top-8 cap per week
        for week, picks in week_picks.items():
            picks_sorted = sorted(picks, key=lambda x: x['model_score'], reverse=True)
            pipeline_rows.extend(picks_sorted[:8])

    pipeline_df = pd.DataFrame(pipeline_rows)

    print(f"\nFull-pipeline ablation: {len(pipeline_df):,} total picks (was 368 with spread rule)")
    print()
    print("Cover rate table (ablated full pipeline):")
    print(cover_rate_table(pipeline_df).to_string(index=False))

    print()
    print("Season breakdown:")
    for season in sorted(pipeline_df['season'].unique()):
        s = pipeline_df[(pipeline_df['season']==season) & (pipeline_df['outcome'].isin(['win','loss']))]
        wins = (s['outcome']=='win').sum()
        n = len(s)
        print(f"  {season}: {wins}/{n} = {wins/n*100:.1f}% cover, ROI {(wins*0.909-(n-wins))/n*100:.1f}%")


if __name__ == '__main__':
    run()
