#!/usr/bin/env python3
"""Break down every underdog pick the model has made 2021-2025."""
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

all_games = con.execute("""
    SELECT m.game_id, m.season, m.week, m.home_team, m.away_team,
           m.spread, m.off_ppa_gap, m.def_ppa_gap, m.home_conference,
           m.over_under, m.home_off_success_rate, m.away_off_success_rate,
           m.home_def_success_rate, m.away_def_success_rate,
           m.home_def_havoc, m.away_def_havoc,
           m.returning_production_gap, m.recruiting_gap,
           m.spread_covered, m.spread_push, m.spread_result
    FROM main_marts.mart_cfbd_game_context m
    WHERE m.spread IS NOT NULL
      AND m.spread_result IN ('covered', 'missed')
      AND m.season BETWEEN 2021 AND 2025
      AND m.home_conference IN {}
""".format(FBS)).df()

all_games = all_games.drop_duplicates(subset='game_id', keep='first').reset_index(drop=True)
print(f"Total games loaded: {len(all_games):,}")

rows = []
for season in sorted(all_games['season'].unique()):
    sdf = all_games[all_games['season'] == season]
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
        if ms < 70 or len(edges) < 4:
            continue

        ppa_gap = float(row.get('off_ppa_gap') or 0)
        bet_home = ppa_gap > 0
        spread   = float(row['spread'])

        # betting_fav: True if the bet is on the favored side
        betting_fav = (bet_home and spread < 0) or (not bet_home and spread > 0)
        if betting_fav:
            continue  # favorites only excluded here

        win = bool(row['spread_covered']) if bet_home else not bool(row['spread_covered'])
        bet_team = row['home_team'] if bet_home else row['away_team']
        rows.append({
            'season':     season,
            'week':       int(row['week']),
            'home':       row['home_team'],
            'away':       row['away_team'],
            'bet_team':   bet_team,
            'spread':     spread,
            'abs_spread': abs(spread),
            'score':      ms,
            'outcome':    'W' if win else 'L',
            'conference': row['home_conference'],
        })

con.close()

if not rows:
    print("No underdog picks found -- check the filter logic")
    sys.exit(1)

df = pd.DataFrame(rows)
print(f"\nTotal underdog picks: {len(df)}")
print(f"Record: {(df['outcome']=='W').sum()}-{(df['outcome']=='L').sum()} "
      f"= {(df['outcome']=='W').mean()*100:.1f}%")
print()

print("=== All underdog picks ===")
print(df[['season','week','home','away','bet_team','spread','score','outcome']]
      .sort_values(['season','week'])
      .to_string(index=False))
print()

print("=== By conference ===")
for conf, grp in df.groupby('conference'):
    w = (grp['outcome']=='W').sum()
    print(f"  {conf:<28} {w}/{len(grp)} = {w/len(grp)*100:.0f}%")
print()

print("=== By spread bucket ===")
df['bucket'] = pd.cut(df['abs_spread'], [0, 7, 14, 21, 50],
                      labels=['0-7 (close)', '7-14 (solid)', '14-21 (big)', '21+ (blowout)'])
for bucket, grp in df.groupby('bucket', observed=True):
    w = (grp['outcome']=='W').sum()
    print(f"  {str(bucket):<20} {w}/{len(grp)} = {w/len(grp)*100:.0f}%")
print()

print("=== By season ===")
for season, grp in df.groupby('season'):
    w = (grp['outcome']=='W').sum()
    print(f"  {season}: {w}/{len(grp)} = {w/len(grp)*100:.0f}%")
