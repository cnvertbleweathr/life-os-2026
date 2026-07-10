#!/usr/bin/env python3
"""
returning_ablation.py

Targeted ablation for two findings from edge_cooccurrence.py:

1. Returning production family: -8.7 delta (fires=66.0%, no-fire=74.7%)
   The returning production rules appear to be net negative.
   Test: disable all returning rules, does overall cover rate improve?

2. away_eff_beats_talent edge: -14.0 delta (56.2% cover, n=64)
   When the away team has a PPA edge despite lower recruiting,
   the pick covers at only 56.2% -- nearly coin-flip.
   The HOME version (home_eff_beats_talent) covers at 77.0% (+11.2).
   Test: disable the away version specifically.

Both use fixed-cohort ablation: same qualifying games, scores
recalculated with the target rule removed.
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
       'Mountain West','Conference USA','Mid-American','Sun Belt','FBS Independents')


def load_games(con):
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
    return (df.sort_values('off_ppa_gap', key=abs, ascending=False)
              .drop_duplicates(subset='game_id', keep='first')
              .reset_index(drop=True))


def score_all(con, df, disabled: set = None) -> pd.DataFrame:
    disabled = disabled or set()
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
            ms, edges, _ = score_game(row, tiers, coach_changes, prior_sp,
                                      disabled=disabled)
            if ms < 70 or len(edges) < 4 or bool(row['spread_push']):
                continue
            ppa_gap  = float(row.get('off_ppa_gap') or 0)
            bet_home = ppa_gap > 0
            win = bool(row['spread_covered']) if bet_home else not bool(row['spread_covered'])
            rows.append({'game_id': row['game_id'], 'season': season,
                         'model_score': ms, 'win': int(win),
                         'edges': edges})
    return pd.DataFrame(rows).drop_duplicates(subset='game_id', keep='first')


def stats(df):
    n = len(df)
    w = df['win'].sum()
    cover = w / n * 100 if n > 0 else 0
    roi   = (w * 0.909 - (n - w)) / n * 100 if n > 0 else 0
    return n, w, cover, roi


def run():
    con = duckdb.connect(DB_PATH, read_only=True)
    print("Loading games...")
    df = load_games(con)
    print(f"Loaded {len(df):,} games")

    print("\nScoring baseline (all rules active)...")
    baseline = score_all(con, df)
    bn, bw, bc, br = stats(baseline)
    print(f"Baseline: {bn} picks, {bc:.1f}% cover, {br:.1f}% ROI")

    # ── Ablation 1: Disable all returning production rules ────────────
    print("\nAblation 1: Disable returning production rules...")
    no_ret = score_all(con, df, disabled={'returning'})
    rn, rw, rc, rr = stats(no_ret)
    print(f"No returning: {rn} picks, {rc:.1f}% cover, {rr:.1f}% ROI")
    print(f"Delta vs baseline: cover {rc-bc:+.1f}pts, ROI {rr-br:+.1f}pts, picks {rn-bn:+d}")

    # Per-season breakdown
    print("\nPer-season (no returning vs baseline):")
    for season in sorted(baseline['season'].unique()):
        b = baseline[baseline['season'] == season]
        r = no_ret[no_ret['season'] == season]
        _, _, bc_s, br_s = stats(b)
        _, _, rc_s, rr_s = stats(r)
        print(f"  {season}: baseline {bc_s:.1f}%/{br_s:.1f}% → no-ret {rc_s:.1f}%/{rr_s:.1f}% "
              f"(cover {rc_s-bc_s:+.1f}pts)")

    # ── Ablation 2: Disable away_eff_beats_talent specifically ────────
    # This requires modifying score_game to accept a fine-grained disabled set.
    # Approximation: check cover rate for picks WITH vs WITHOUT this edge
    print("\n\nAblation 2: away_eff_beats_talent edge analysis")
    print("(Fixed-cohort: same qualifying games, split by edge presence)")
    with_edge    = baseline[baseline['edges'].apply(lambda e: 'away_eff_beats_talent' in e)]
    without_edge = baseline[baseline['edges'].apply(lambda e: 'away_eff_beats_talent' not in e)]

    we_n, we_w, we_c, we_r = stats(with_edge)
    wo_n, wo_w, wo_c, wo_r = stats(without_edge)

    print(f"  With away_eff_beats_talent:    {we_n:>4} picks, {we_c:.1f}% cover, {we_r:.1f}% ROI")
    print(f"  Without away_eff_beats_talent: {wo_n:>4} picks, {wo_c:.1f}% cover, {wo_r:.1f}% ROI")
    print(f"  Delta: {we_c-wo_c:+.1f}pts cover")

    # Compare with home_eff_beats_talent for contrast
    with_home = baseline[baseline['edges'].apply(lambda e: 'home_eff_beats_talent' in e)]
    wh_n, wh_w, wh_c, wh_r = stats(with_home)
    print(f"\n  For contrast — home_eff_beats_talent:")
    print(f"  With home_eff_beats_talent:    {wh_n:>4} picks, {wh_c:.1f}% cover, {wh_r:.1f}% ROI")

    # Per-season for away_eff_beats_talent
    print("\nPer-season for away_eff_beats_talent:")
    for season in sorted(baseline['season'].unique()):
        b_s = baseline[baseline['season'] == season]
        we_s = b_s[b_s['edges'].apply(lambda e: 'away_eff_beats_talent' in e)]
        wo_s = b_s[b_s['edges'].apply(lambda e: 'away_eff_beats_talent' not in e)]
        if len(we_s) > 0:
            _, _, c, r = stats(we_s)
            print(f"  {season}: WITH edge: {c:.1f}% cover (n={len(we_s)})")

    con.close()

    print("\n" + "=" * 65)
    print("VERDICT")
    print("=" * 65)
    print(f"""
Returning production rules:
  Baseline cover:       {bc:.1f}%
  Without returning:    {rc:.1f}%
  Delta:                {rc-bc:+.1f}pts
  Pick count change:    {rn-bn:+d}

  → {'DISABLE returning rules' if rc > bc + 1 else 'KEEP returning rules' if bc > rc + 1 else 'INCONCLUSIVE -- marginal difference'}

away_eff_beats_talent edge:
  With edge:            {we_c:.1f}% (n={we_n})
  Without edge:         {wo_c:.1f}% (n={wo_n})
  Delta:                {we_c-wo_c:+.1f}pts
  vs home version:      {wh_c:.1f}% (n={wh_n})

  → {'DISABLE away_eff_beats_talent' if we_c < wo_c - 3 else 'KEEP -- not clearly harmful'}
""")


if __name__ == '__main__':
    run()
