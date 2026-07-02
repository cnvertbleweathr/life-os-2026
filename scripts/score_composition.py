#!/usr/bin/env python3
"""
score_composition.py

Priority 1: Before declaring any rule responsible for the non-monotonic
calibration, produce a full rule-trigger and contribution table by score bin.

Also breaks out favorite vs underdog, home vs away, and season to test
whether the pattern is stable or concentrated in a specific subset.

Reads from data/calibration_manifest.parquet (written by reconcile_calibration.py).
Must run reconcile_calibration.py first.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import duckdb
import pandas as pd
import numpy as np
from backtest_walk_forward import score_game, build_tiers

DB_PATH  = str(ROOT / "data" / "warehouse" / "ons.duckdb")
MANIFEST = ROOT / "data" / "calibration_manifest.parquet"


def get_rule_contributions(row: dict, tiers: dict, coach_changes: set, prior_sp: dict) -> dict:
    """
    Re-run score_game() but capture each rule's contribution individually.
    Returns a dict of {rule_name: points_added}.
    """
    import importlib
    import backtest_walk_forward as bwf

    # We need to trace which rules fire. Since score_game() is opaque,
    # we reconstruct by calling it with individual rules zeroed out via
    # the model's own ablation mechanism, then taking differences.
    # This requires reading score_game()'s source to enumerate rule names.

    # Full score
    full, full_edges, _ = score_game(row, tiers, coach_changes, prior_sp)

    # Extract which edges fired (these are the rule labels)
    return {'model_score': full, 'n_edges': len(full_edges), 'edges': full_edges}


def run() -> None:
    if not MANIFEST.exists():
        print(f"ERROR: {MANIFEST} not found. Run reconcile_calibration.py first.")
        sys.exit(1)

    manifest = pd.read_parquet(MANIFEST)
    print(f"Loaded manifest: {len(manifest):,} games")

    # Add score bin
    def bin_label(s: float) -> str:
        if s < 70:  return '<70'
        if s <= 74: return '70-74'
        if s <= 79: return '75-79'
        if s <= 84: return '80-84'
        if s <= 89: return '85-89'
        return '90-99'

    manifest['bin'] = manifest['model_score'].apply(bin_label)

    # Reload full row data from mart for rule decomposition
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
    df = df.merge(manifest[['game_id', 'model_score', 'n_edges', 'bin']], on='game_id')

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
        merged = curr.merge(prev, on='team', suffixes=('_c', '_p'))
        coach_changes = set(merged[merged['coach_c'] != merged['coach_p']]['team'])

        for _, row in sdf.iterrows():
            ms, edges, _ = score_game(row, tiers, coach_changes, prior_sp)
            ppa_gap = float(row.get('off_ppa_gap') or 0)
            spread  = float(row['spread'])
            bet_home = ppa_gap > 0
            is_fav   = (bet_home and spread < 0) or (not bet_home and spread > 0)

            if bool(row['spread_push']):
                outcome = 'push'
            elif bet_home:
                outcome = 'win' if bool(row['spread_covered']) else 'loss'
            else:
                outcome = 'win' if not bool(row['spread_covered']) else 'loss'

            edge_set = set(edges)
            rows.append({
                'game_id':    row['game_id'],
                'season':     season,
                'week':       row['week'],
                'bin':        row['bin'],
                'model_score': ms,
                'abs_spread': abs(spread),
                'ppa_gap':    abs(ppa_gap),
                'bet_home':   bet_home,
                'is_fav':     is_fav,
                'outcome':    outcome,
                # Rule triggers (1 if edge fired, 0 if not)
                'e_ppa_extreme':      int('PPA extreme' in str(edge_set)),
                'e_spread_prime':     int('Spread prime' in str(edge_set) or
                                         any('prime' in str(e).lower() for e in edges)),
                'e_spread_solid':     int(any('solid' in str(e).lower() for e in edges)),
                'e_talent_parity':    int(any('talent' in str(e).lower() for e in edges)),
                'e_sr_parity':        int(any('success' in str(e).lower() or
                                              'SR' in str(e) for e in edges)),
                'e_returning':        int(any('return' in str(e).lower() for e in edges)),
                'e_recruiting':       int(any('recruit' in str(e).lower() for e in edges)),
                'e_havoc':            int(any('havoc' in str(e).lower() for e in edges)),
                'n_edges':            len(edges),
            })

    con.close()
    scored = pd.DataFrame(rows)

    BINS = ['70-74', '75-79', '80-84', '85-89', '90-99']
    scored = scored[scored['bin'].isin(BINS)]

    def cover_rate(df: pd.DataFrame) -> float:
        g = df[df['outcome'].isin(['win', 'loss'])]
        return round(g['outcome'].eq('win').mean() * 100, 1) if len(g) > 0 else float('nan')

    print()
    print("=" * 65)
    print("RULE TRIGGER RATES BY BIN (% of games where rule fired)")
    print("=" * 65)
    rule_cols = [c for c in scored.columns if c.startswith('e_')]
    rule_names = {
        'e_ppa_extreme':  'PPA extreme',
        'e_spread_prime': 'Spread prime (3-7)',
        'e_spread_solid': 'Spread solid (7-10)',
        'e_talent_parity':'Talent parity',
        'e_sr_parity':    'SR parity',
        'e_returning':    'Returning prod',
        'e_recruiting':   'Recruiting',
        'e_havoc':        'Havoc',
    }
    header = f"{'Rule':<22}" + "".join(f"{b:>8}" for b in BINS)
    print(header)
    print("-" * (22 + 8 * len(BINS)))
    for col, name in rule_names.items():
        row_str = f"{name:<22}"
        for b in BINS:
            bdf = scored[scored['bin'] == b]
            rate = bdf[col].mean() * 100 if len(bdf) > 0 else float('nan')
            row_str += f"{rate:>7.0f}%"
        print(row_str)

    # Cover rate row
    print("-" * (22 + 8 * len(BINS)))
    cr_row = f"{'Cover rate':<22}"
    for b in BINS:
        cr_row += f"{cover_rate(scored[scored['bin']==b]):>7.1f}%"
    print(cr_row)

    print()
    print("=" * 65)
    print("COVER RATE BY BIN — FAVORITE vs UNDERDOG")
    print("=" * 65)
    print(f"{'':22}" + "".join(f"{b:>8}" for b in BINS))
    for label, mask in [("Favorite", scored['is_fav']==True),
                        ("Underdog", scored['is_fav']==False)]:
        row_str = f"{label:<22}"
        for b in BINS:
            subset = scored[mask & (scored['bin']==b)]
            row_str += f"{cover_rate(subset):>7.1f}%"
        print(row_str)
    print(f"{'N (fav)':<22}" + "".join(
        f"{(scored[(scored['is_fav']==True)&(scored['bin']==b)]['outcome'].isin(['win','loss']).sum()):>8}"
        for b in BINS))
    print(f"{'N (dog)':<22}" + "".join(
        f"{(scored[(scored['is_fav']==False)&(scored['bin']==b)]['outcome'].isin(['win','loss']).sum()):>8}"
        for b in BINS))

    print()
    print("=" * 65)
    print("COVER RATE BY BIN — SEASON")
    print("=" * 65)
    print(f"{'Season':<22}" + "".join(f"{b:>8}" for b in BINS))
    for season in sorted(scored['season'].unique()):
        row_str = f"{season:<22}"
        for b in BINS:
            subset = scored[(scored['season']==season) & (scored['bin']==b)]
            row_str += f"{cover_rate(subset):>7.1f}%"
        print(row_str)

    print()
    print("=" * 65)
    print("AVERAGE ABS_SPREAD AND PPA_GAP BY BIN + SIDE")
    print("=" * 65)
    print(scored.groupby(['bin', 'is_fav'])[['abs_spread', 'ppa_gap', 'model_score']].mean().round(3))


if __name__ == '__main__':
    run()
