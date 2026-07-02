#!/usr/bin/env python3
"""Inspect every 2022 pick that scored 90+ to understand the 0% cover rate anomaly."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import duckdb
import pandas as pd
from backtest_walk_forward import score_game, build_tiers

DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")
FBS = ('SEC','Big Ten','Big 12','ACC','Pac-12','American Athletic',
       'Mountain West','Conference USA','Mid-American','Sun Belt','FBS Independents')

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
      AND m.season = 2022
      AND m.home_conference IN {}
""".format(FBS)).df()

tiers = build_tiers(con, 2022)
sp_df = con.execute('SELECT team, season, rating FROM cfbd.sp_ratings').df()
coaches_df = con.execute(
    'SELECT school AS team, year AS season, full_name AS coach FROM cfbd.coaches'
).df()
prior_sp = {(r['team'], int(r['season'])): float(r['rating']) for _, r in sp_df.iterrows()}
curr = coaches_df[coaches_df['season'] == 2022]
prev = coaches_df[coaches_df['season'] == 2021]
merged = curr.merge(prev, on='team', suffixes=('_c', '_p'))
coach_changes = set(merged[merged['coach_c'] != merged['coach_p']]['team'])
con.close()

rows = []
for _, row in df.iterrows():
    ms, edges, _ = score_game(row, tiers, coach_changes, prior_sp)
    if ms < 90 or len(edges) < 4:
        continue
    ppa_gap = float(row.get('off_ppa_gap') or 0)
    bet_home = ppa_gap > 0
    if bool(row['spread_push']):
        out = 'push'
    elif bet_home:
        out = 'win' if bool(row['spread_covered']) else 'loss'
    else:
        out = 'win' if not bool(row['spread_covered']) else 'loss'
    rows.append({
        'week': row['week'], 'home': row['home_team'], 'away': row['away_team'],
        'spread': row['spread'], 'score': ms, 'edges': len(edges),
        'outcome': out, 'ppa_gap': round(ppa_gap, 3),
    })

result = pd.DataFrame(rows).sort_values('week')
print(f'2022 picks scoring 90+: {len(result)}')
print(result.to_string(index=False))
wins = (result['outcome'] == 'win').sum()
losses = (result['outcome'] == 'loss').sum()
print(f'\nWins: {wins}, Losses: {losses}, Cover%: {wins/(wins+losses)*100:.1f}%' if wins+losses > 0 else '\nNo gradeable picks')
