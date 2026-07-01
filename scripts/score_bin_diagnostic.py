#!/usr/bin/env python3
"""
score_bin_diagnostic.py

Investigates WHY the 70-74 score bin outperforms 85-89 in cover rate --
specifically whether lower bins have systematically different spread sizes
or PPA gap magnitudes that would explain the pattern structurally.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import duckdb
import pandas as pd
from backtest_walk_forward import score_game, build_tiers

DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")
FBS_CONFERENCES = (
    'SEC', 'Big Ten', 'Big 12', 'ACC', 'Pac-12',
    'American Athletic', 'Mountain West', 'Conference USA',
    'Mid-American', 'Sun Belt', 'FBS Independents'
)

con = duckdb.connect(DB_PATH, read_only=True)

df = con.execute("""
    SELECT m.season, m.week, m.home_team, m.away_team,
           m.spread, m.off_ppa_gap, m.def_ppa_gap, m.over_under,
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
""".format(FBS_CONFERENCES)).df()

print(f"Loaded {len(df):,} historical games")

rows = []
for season in sorted(df['season'].unique()):
    sdf = df[df['season'] == season]
    tiers = build_tiers(con, season)
    sp_df = con.execute('SELECT team, season, rating FROM cfbd.sp_ratings').df()
    coaches_df = con.execute('SELECT school AS team, year AS season, full_name AS coach FROM cfbd.coaches').df()
    prior_sp = {(r['team'], int(r['season'])): float(r['rating']) for _, r in sp_df.iterrows()}
    curr = coaches_df[coaches_df['season'] == season]
    prev = coaches_df[coaches_df['season'] == season - 1]
    merged = curr.merge(prev, on='team', suffixes=('_c', '_p'))
    coach_changes = set(merged[merged['coach_c'] != merged['coach_p']]['team'])

    for _, row in sdf.iterrows():
        ms, edges, _ = score_game(row, tiers, coach_changes, prior_sp)
        if ms < 70 or len(edges) < 4:
            continue

        ppa_gap = row.get('off_ppa_gap', 0) or 0
        bet_home = ppa_gap > 0
        if bool(row['spread_push']):
            outcome = 'push'
        elif bet_home:
            outcome = 'win' if bool(row['spread_covered']) else 'loss'
        else:
            outcome = 'win' if not bool(row['spread_covered']) else 'loss'

        bin_label = ('70-74' if ms <= 74 else
                     '75-79' if ms <= 79 else
                     '80-84' if ms <= 84 else
                     '85-89' if ms <= 89 else '90-99')

        rows.append({
            'bin':          bin_label,
            'model_score':  ms,
            'abs_spread':   abs(float(row['spread'])),
            'off_ppa_gap':  abs(float(ppa_gap)),
            'n_edges':      len(edges),
            'outcome':      outcome,
        })

con.close()
scored = pd.DataFrame(rows)

print(f"\nQualifying picks: {len(scored):,}")
print()

print("=== Average characteristics by bin ===")
print(scored.groupby('bin')[['abs_spread', 'off_ppa_gap', 'model_score', 'n_edges']].mean().round(3))
print()

print("=== Cover rate by bin ===")
for bin_label in ['70-74', '75-79', '80-84', '85-89', '90-99']:
    b = scored[scored['bin'] == bin_label]
    gradeable = b[b['outcome'].isin(['win', 'loss'])]
    wins = (gradeable['outcome'] == 'win').sum()
    n = len(gradeable)
    print(f"  {bin_label}: {wins}/{n} = {wins/n*100:.1f}% cover" if n > 0 else f"  {bin_label}: no data")
print()

print("=== Key question: does abs_spread explain the pattern? ===")
print("Higher spreads are harder to cover -- if lower score bins have tighter")
print("spreads, that alone could explain their higher cover rate.")
spread_bins = pd.cut(scored['abs_spread'], bins=[0, 5, 10, 15, 20, 50], labels=['0-5', '5-10', '10-15', '15-20', '20+'])
scored['spread_bin'] = spread_bins
pivot = scored[scored['outcome'].isin(['win','loss'])].pivot_table(
    index='spread_bin', columns='bin',
    values='outcome', aggfunc=lambda x: (x == 'win').mean()
).round(3)
print(pivot)
