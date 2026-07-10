#!/usr/bin/env python3
"""Check whether the model's PPA-gap selection mechanism is structurally biased toward favorites."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import duckdb
from backtest_walk_forward import score_game, build_tiers

DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")
FBS = ('SEC','Big Ten','Big 12','ACC','Pac-12','American Athletic',
       'Mountain West','Conference USA','Mid-American','Sun Belt','FBS Independents')

con = duckdb.connect(DB_PATH, read_only=True)

# 1. Base rate: do favorites or dogs cover more often in this game population?
df = con.execute("""
    SELECT
        CASE WHEN cast(spread as double) < 0 THEN 'home_fav' ELSE 'home_dog' END as home_side,
        count(*) as n,
        sum(CASE WHEN spread_covered THEN 1 ELSE 0 END) as home_covers,
        round(avg(CASE WHEN spread_covered THEN 1.0 ELSE 0.0 END) * 100, 1) as home_cover_pct
    FROM main_marts.mart_cfbd_line_accuracy
    WHERE spread IS NOT NULL AND spread_covered IS NOT NULL AND spread_push = false
      AND season BETWEEN 2021 AND 2025
      AND home_conference IN {}
    GROUP BY home_side
""".format(FBS)).df()
print("=== Base rate: do favorites cover more? ===")
print(df.to_string(index=False))
print()

# 2. Model's published picks: fav vs dog breakdown
all_games = con.execute("""
    SELECT m.game_id, m.season, m.week, m.home_team, m.away_team,
           m.spread, m.off_ppa_gap, m.def_ppa_gap,
           m.home_off_success_rate, m.away_off_success_rate,
           m.home_def_success_rate, m.away_def_success_rate,
           m.home_def_havoc, m.away_def_havoc,
           m.returning_production_gap, m.recruiting_gap,
           m.spread_covered, m.spread_push, m.spread_result,
           m.home_conference, m.over_under
    FROM main_marts.mart_cfbd_game_context m
    WHERE m.spread IS NOT NULL
      AND m.spread_result IN ('covered', 'missed', 'push')
      AND m.season BETWEEN 2021 AND 2025
      AND m.home_conference IN {}
""".format(FBS)).df()

# Deduplicate
all_games = all_games.sort_values('off_ppa_gap', key=abs, ascending=False)
all_games = all_games.drop_duplicates(subset='game_id', keep='first').reset_index(drop=True)

fav_w = fav_l = dog_w = dog_l = 0
for season in sorted(all_games['season'].unique()):
    sdf = all_games[all_games['season'] == season]
    tiers = build_tiers(con, season)
    sp_df = con.execute('SELECT team, season, rating FROM cfbd.sp_ratings').df()
    coaches_df = con.execute('SELECT school AS team, year AS season, full_name AS coach FROM cfbd.coaches').df()
    prior_sp = {(r['team'], int(r['season'])): float(r['rating']) for _, r in sp_df.iterrows()}
    curr = coaches_df[coaches_df['season'] == season]
    prev = coaches_df[coaches_df['season'] == season - 1]
    merged = curr.merge(prev, on='team', suffixes=('_c','_p'))
    coach_changes = set(merged[merged['coach_c'] != merged['coach_p']]['team'])

    for _, row in sdf.iterrows():
        ms, edges, _ = score_game(row, tiers, coach_changes, prior_sp)
        if ms < 70 or len(edges) < 4 or bool(row['spread_push']): continue
        ppa_gap = float(row.get('off_ppa_gap') or 0)
        bet_home = ppa_gap > 0
        spread = float(row['spread'])
        betting_fav = (bet_home and spread < 0) or (not bet_home and spread > 0)
        win = bool(row['spread_covered']) if bet_home else not bool(row['spread_covered'])
        if betting_fav:
            if win: fav_w += 1
            else:   fav_l += 1
        else:
            if win: dog_w += 1
            else:   dog_l += 1

con.close()

print("=== Model published picks: fav vs dog ===")
fav_n = fav_w + fav_l
dog_n = dog_w + dog_l
print(f"Favorites: {fav_w}/{fav_n} = {fav_w/fav_n*100:.1f}%  ROI={(fav_w*0.909-fav_l)/fav_n*100:.1f}%" if fav_n else "No fav picks")
print(f"Underdogs: {dog_w}/{dog_n} = {dog_w/dog_n*100:.1f}%  ROI={(dog_w*0.909-dog_l)/dog_n*100:.1f}%" if dog_n else "No dog picks")
print(f"Total: {fav_n+dog_n} picks")
