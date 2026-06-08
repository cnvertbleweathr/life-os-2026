#!/usr/bin/env python3
"""
backtest_ablation.py

Signal ablation test: disables each signal group completely inside score_game,
removing both the score contribution AND the edge/warning label.

This is the correct ablation — it answers:
  "What happens to model ROI if this signal is entirely removed?"

A signal is VALUABLE if removing it drops ROI.
A signal is REDUNDANT/HARMFUL if removing it improves ROI.

Usage:
  python scripts/backtest_ablation.py
  python scripts/backtest_ablation.py --min-score 70
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT    = Path(__file__).resolve().parents[1]
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")

sys.path.insert(0, str(ROOT / "scripts"))
from backtest_walk_forward import build_tiers, score_game, safe_float


def run_once(df, sp_lookup, coaches_df, min_score, disabled=None):
    """Full walk-forward with optional signal group disabled. Returns summary dict."""
    disabled = disabled or set()
    results  = []

    for season in sorted(df["season"].unique()):
        try:
            con2  = duckdb.connect(DB_PATH, read_only=True)
            tiers = build_tiers(con2, season)
            con2.close()
        except Exception:
            tiers = {}

        curr = coaches_df[coaches_df["season"] == season]
        prev = coaches_df[coaches_df["season"] == season - 1]
        merged = curr.merge(prev, on="team", suffixes=("_c","_p"))
        coach_changes = set(merged[merged["coach_c"] != merged["coach_p"]]["team"])

        for _, row in df[df["season"] == season].iterrows():
            ms, edges, _ = score_game(
                row, tiers, coach_changes, sp_lookup, disabled=disabled
            )
            if ms < min_score: continue
            if len(edges) < 4: continue

            ppa_gap  = safe_float(row.get("off_ppa_gap"), 0)
            bet_home = ppa_gap > 0
            result   = str(row.get("spread_result", ""))

            if result == "push":
                pnl, outcome = 0.0, "push"
            elif bet_home:
                pnl     = 0.909 if result == "covered" else -1.0
                outcome = "win"  if result == "covered" else "loss"
            else:
                pnl     = 0.909 if result == "missed"  else -1.0
                outcome = "win"  if result == "missed"  else "loss"
            results.append({"outcome": outcome, "pnl": pnl})

    if not results:
        return {"bets": 0, "wins": 0, "losses": 0, "pnl": 0.0, "roi": 0.0, "wp": 0.0}

    rdf    = pd.DataFrame(results)
    total  = len(rdf)
    wins   = int((rdf["outcome"] == "win").sum())
    losses = int((rdf["outcome"] == "loss").sum())
    pnl    = float(rdf["pnl"].sum())
    roi    = pnl / total * 100
    wp     = wins / (wins + losses) * 100 if (wins + losses) else 0
    return {"bets": total, "wins": wins, "losses": losses, "pnl": pnl, "roi": roi, "wp": wp}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--min-score", type=int, default=70)
    args = p.parse_args()

    print("Loading data...")
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
    except Exception as e:
        print(f"Cannot open DuckDB: {e}"); sys.exit(1)

    df = con.execute("""
        WITH ranked AS (
            SELECT
                gc.game_id, gc.season, gc.week,
                gc.home_team, gc.away_team, gc.home_conference,
                gc.spread, gc.spread_result, gc.spread_covered,
                gc.off_ppa_gap,
                gc.returning_production_gap,
                gc.recruiting_gap,
                gc.home_off_success_rate,
                gc.away_off_success_rate,
                gc.home_def_success_rate,
                gc.away_def_success_rate,
                gc.home_def_havoc,
                gc.away_def_havoc,
                gc.home_coach, gc.away_coach,
                td.travel_miles,
                ROW_NUMBER() OVER (
                    PARTITION BY gc.game_id
                    ORDER BY CASE gc.provider
                        WHEN 'consensus' THEN 1
                        WHEN 'DraftKings' THEN 2
                        WHEN 'ESPN Bet'   THEN 3
                        ELSE 4 END
                ) AS rn
            FROM main_marts.mart_cfbd_game_context gc
            LEFT JOIN main_marts.mart_cfbd_travel_distance td
                ON td.game_id = gc.game_id
            WHERE gc.spread_result IN ('covered','missed','push')
              AND gc.season BETWEEN 2022 AND 2025
              AND gc.spread IS NOT NULL
        )
        SELECT * FROM ranked WHERE rn = 1
    """).df()

    sp_df = con.execute("SELECT team, season, rating FROM cfbd.sp_ratings").df()
    sp_lookup = {(r["team"], int(r["season"])): float(r["rating"])
                 for _, r in sp_df.iterrows()}
    coaches_df = con.execute(
        "SELECT school AS team, year AS season, full_name AS coach FROM cfbd.coaches"
    ).df()
    con.close()

    print(f"Loaded {len(df):,} games\n")

    # Baseline
    print("Running baseline...")
    base = run_once(df, sp_lookup, coaches_df, args.min_score)
    print(f"Baseline: {base['bets']} bets  {base['wins']}-{base['losses']}  "
          f"{base['wp']:.1f}%  ROI {base['roi']:+.1f}%\n")

    # Signal groups to ablate — key must match disabled key in score_game
    SIGNALS = [
        ("SP+ alignment",         {"sp_plus"}),
        ("Team tier",             {"tier"}),
        ("Conference filter",     {"conference"}),
        ("Returning production",  {"returning"}),
        ("Travel distance",       {"travel"}),
        ("Recruiting talent",     {"recruiting"}),
        ("Success rate",          {"success_rate"}),
        ("Defensive havoc",       {"havoc"}),
        ("Spread range",          {"spread"}),
        ("Coach change filter",   {"coach_change"}),
    ]

    rows = []
    for name, disabled in SIGNALS:
        print(f"  Ablating: {name}...")
        r = run_once(df, sp_lookup, coaches_df, args.min_score, disabled=disabled)
        delta_roi  = r["roi"]  - base["roi"]
        delta_bets = r["bets"] - base["bets"]
        rows.append((name, r, delta_roi, delta_bets))

    rows.sort(key=lambda x: x[2])  # most valuable first (biggest negative delta)

    print()
    print("=" * 75)
    print("SIGNAL ABLATION RESULTS")
    print("Each signal disabled completely — score + edge + warning removed")
    print("=" * 75)
    print(f"{'Signal':<25} {'Bets':>5}  {'W-L':<10}  {'Win%':>6}  "
          f"{'ROI':>8}  {'ΔROI':>8}  {'ΔBets':>6}  Verdict")
    print(f"{'-'*25} {'-'*5}  {'-'*10}  {'-'*6}  "
          f"{'-'*8}  {'-'*8}  {'-'*6}  {'-'*15}")

    # Baseline row first
    print(f"{'BASELINE (all signals)':<25} {base['bets']:>5}  "
          f"{base['wins']}-{base['losses']:<7}  {base['wp']:>5.1f}%  "
          f"{base['roi']:>+7.1f}%  {'—':>8}  {'—':>6}")
    print()

    for name, r, d_roi, d_bets in rows:
        if d_roi < -5:      verdict = "✅ HIGHLY VALUABLE"
        elif d_roi < -2:    verdict = "✅ VALUABLE"
        elif d_roi < 0:     verdict = "✅ slight+"
        elif d_roi < 2:     verdict = "⚠️  neutral"
        elif d_roi < 5:     verdict = "⚠️  review"
        else:               verdict = "❌ REMOVE/REDUCE"
        wl = f"{r['wins']}-{r['losses']}"
        print(f"  {name:<23} {r['bets']:>5}  {wl:<10}  {r['wp']:>5.1f}%  "
              f"{r['roi']:>+7.1f}%  {d_roi:>+7.1f}%  {d_bets:>+6}  {verdict}")

    print()
    print("ΔROI = ROI without signal − baseline ROI")
    print("  Negative ΔROI → signal was adding value (removing it hurts)")
    print("  Positive ΔROI → signal was redundant or harmful (removing it helps)")
    print("=" * 75)


if __name__ == "__main__":
    raise SystemExit(main())
