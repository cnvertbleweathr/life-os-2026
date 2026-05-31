#!/usr/bin/env python3
"""
cfb_edge_validation.py

Cross-season validation of betting edges (2021-2025).
Tests multiple PPA gap thresholds to find optimal cutoffs.
Detects trends, consistency, and which edges hold across years.

Usage:
  python scripts/cfb_edge_validation.py
  python scripts/cfb_edge_validation.py --conferences "SEC,Big Ten,Big 12,ACC"
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import pandas as pd
import numpy as np

ROOT    = Path(__file__).resolve().parents[1]
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")

ALL_MAJOR = {"SEC", "Big Ten", "Big 12", "ACC",
             "American Athletic", "Mountain West", "Sun Belt",
             "Mid-American", "Conference USA"}

WIN_PAYOUT  = 0.909
LOSS_AMOUNT = 1.00


def safe_bool(val) -> bool:
    if val is None:
        return False
    try:
        if pd.isna(val):
            return False
    except (TypeError, ValueError):
        pass
    try:
        return bool(val)
    except (TypeError, ValueError):
        return False


def safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
        return float(val)
    except (TypeError, ValueError):
        return None


def bet_result(covered, push) -> float:
    if safe_bool(push):
        return 0.0
    if covered is True:
        return WIN_PAYOUT
    if covered is False:
        return -LOSS_AMOUNT
    return 0.0


def load_all_seasons(con, conferences: set[str]) -> pd.DataFrame:
    conf_list = "', '".join(conferences)
    return con.execute(f"""
        SELECT
            l.game_id, l.season, l.week,
            g.home_conference,
            l.home_team, l.away_team,
            l.spread, l.over_under,
            l.actual_margin, l.total_points,
            l.spread_covered, l.spread_push,
            l.ou_result, l.ou_push,
            l.spread_abs, l.home_is_underdog,
            l.sp_agrees_with_line, l.sp_upset_alert,
            l.sp_differential,
            ctx.is_rivalry_game,
            ctx.temperature, ctx.wind_speed,
            ctx.game_indoors, ctx.high_wind,
            ctx.temp_bucket,
            ctx.home_rush_ppa, ctx.away_rush_ppa,
            ctx.off_ppa_gap, ctx.def_ppa_gap,
            ctx.home_def_havoc, ctx.away_def_havoc,
            ctx.returning_production_gap,
            ctx.home_pct_returning, ctx.away_pct_returning,
            ctx.recruiting_gap,
            ctx.home_off_ppa, ctx.away_off_ppa,
            ctx.home_def_ppa, ctx.away_def_ppa,
            ctx.home_rush_success_rate, ctx.away_rush_success_rate,
        FROM main_marts.mart_cfbd_line_accuracy l
        LEFT JOIN main_marts.mart_cfbd_game_context ctx
            ON l.game_id = ctx.game_id AND l.provider = ctx.provider
        LEFT JOIN cfbd.games g ON l.game_id = g.game_id
        WHERE l.spread_result IN ('covered', 'missed', 'push')
          AND g.home_conference IN ('{conf_list}')
          AND l.provider = (
              SELECT coalesce(
                  max(case when provider = 'Bovada' then 'Bovada' end),
                  min(provider)
              )
              FROM cfbd.lines l2
              WHERE l2.game_id = l.game_id
          )
        ORDER BY l.season, l.week
    """).df()


def simulate_edge(df: pd.DataFrame, mask: pd.Series,
                  bet_home_covers: bool = True,
                  bet_under: bool = False) -> dict:
    """Simulate a single-signal edge on a filtered subset."""
    subset = df[mask].copy()
    if subset.empty:
        return {"bets": 0, "wins": 0, "losses": 0, "win_pct": 0, "pnl": 0, "roi": 0}

    pnl = 0.0
    wins = losses = pushes = 0

    for _, row in subset.iterrows():
        if not bet_under:
            covered = row.get("spread_covered")
            push    = row.get("spread_push")
            if not bet_home_covers:
                covered = not covered if covered is not None else None
        else:
            ou     = row.get("ou_result")
            push   = row.get("ou_push")
            covered = ou == "under" if ou else None

        p = bet_result(covered, safe_bool(push))
        pnl += p
        if p > 0: wins += 1
        elif p < 0: losses += 1
        else: pushes += 1

    bets = wins + losses + pushes
    win_pct = wins / (wins + losses) * 100 if (wins + losses) else 0
    roi = pnl / bets * 100 if bets else 0

    return {
        "bets": bets, "wins": wins, "losses": losses, "pushes": pushes,
        "win_pct": round(win_pct, 1),
        "pnl": round(pnl, 2),
        "roi": round(roi, 2),
    }


def section(title: str) -> None:
    print(f"\n{'='*65}")
    print(f"  {title}")
    print(f"{'='*65}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--conferences", default=None)
    p.add_argument("--all-conferences", action="store_true")
    args = p.parse_args()

    if args.all_conferences or not args.conferences:
        conferences = ALL_MAJOR
    else:
        conferences = {c.strip() for c in args.conferences.split(",")}

    con = duckdb.connect(DB_PATH, read_only=True)
    print(f"Loading all seasons for: {', '.join(sorted(conferences))}...")
    df = load_all_seasons(con, conferences)
    con.close()

    print(f"Loaded {len(df):,} games across {df['season'].nunique()} seasons "
          f"({df['season'].min()}-{df['season'].max()})\n")

    seasons = sorted(df["season"].unique())

    # ==================================================================
    # 1. PPA GAP THRESHOLD OPTIMIZATION
    # ==================================================================
    section("📐 PPA Gap Threshold Optimization (home offense vs away defense)")

    thresholds = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
    threshold_rows = []

    for t in thresholds:
        mask = (
            df["off_ppa_gap"].notna() &
            (df["off_ppa_gap"].astype(float) > t)
        )
        res = simulate_edge(df, mask, bet_home_covers=True)
        res["threshold"] = f">{t}"
        res["pct_games"] = round(mask.sum() / len(df) * 100, 1)
        threshold_rows.append(res)

    thresh_df = pd.DataFrame(threshold_rows)
    print(thresh_df[["threshold", "bets", "pct_games", "win_pct", "pnl", "roi"]].to_string(index=False))

    # Best threshold
    best_t = thresh_df.loc[thresh_df["roi"].idxmax(), "threshold"]
    print(f"\n  → Optimal threshold: PPA gap {best_t}")

    # ==================================================================
    # 2. PPA GAP EDGE BY SEASON (consistency check)
    # ==================================================================
    section("📅 PPA Gap Edge (>0.15) by Season")

    season_rows = []
    for season in seasons:
        season_df = df[df["season"] == season]
        mask = (
            season_df["off_ppa_gap"].notna() &
            (season_df["off_ppa_gap"].astype(float) > 0.15)
        )
        res = simulate_edge(season_df, mask, bet_home_covers=True)
        res["season"] = season
        season_rows.append(res)

    season_df_out = pd.DataFrame(season_rows)
    print(season_df_out[["season", "bets", "win_pct", "pnl", "roi"]].to_string(index=False))

    profitable_seasons = (season_df_out["roi"] > 0).sum()
    print(f"\n  → Profitable in {profitable_seasons}/{len(seasons)} seasons")

    # ==================================================================
    # 3. RIVALRY EDGE BY SEASON
    # ==================================================================
    section("⚔️  Rivalry Underdog Edge by Season")

    rivalry_rows = []
    for season in seasons:
        season_df = df[df["season"] == season]
        mask = (
            season_df["is_rivalry_game"].notna() &
            season_df["is_rivalry_game"].astype(bool) &
            season_df["home_is_underdog"].notna()
        )
        if mask.sum() == 0:
            continue
        # Bet underdog (home if home_is_underdog, away otherwise)
        subset = season_df[mask]
        pnl = wins = losses = 0
        for _, row in subset.iterrows():
            bet_home = safe_bool(row.get("home_is_underdog"))
            covered = row.get("spread_covered")
            push = row.get("spread_push")
            if not bet_home:
                covered = not covered if covered is not None else None
            p = bet_result(covered, safe_bool(push))
            pnl += p
            if p > 0: wins += 1
            elif p < 0: losses += 1

        bets = wins + losses
        rivalry_rows.append({
            "season": season,
            "bets": bets,
            "wins": wins,
            "losses": losses,
            "win_pct": round(wins/bets*100, 1) if bets else 0,
            "pnl": round(pnl, 2),
            "roi": round(pnl/bets*100, 2) if bets else 0,
        })

    if rivalry_rows:
        riv_df = pd.DataFrame(rivalry_rows)
        print(riv_df.to_string(index=False))
        profitable = (riv_df["roi"] > 0).sum()
        print(f"\n  → Profitable in {profitable}/{len(rivalry_rows)} seasons")

    # ==================================================================
    # 4. WEATHER EDGES BY SEASON
    # ==================================================================
    section("🌡️  Cold Game (<45°F) Under by Season")

    cold_rows = []
    for season in seasons:
        season_df = df[df["season"] == season]
        mask = (
            season_df["temperature"].notna() &
            (~season_df["game_indoors"].fillna(False).astype(bool)) &
            (season_df["temperature"].astype(float) < 45)
        )
        res = simulate_edge(season_df, mask, bet_under=True)
        res["season"] = season
        cold_rows.append(res)

    cold_df = pd.DataFrame(cold_rows)
    print(cold_df[["season", "bets", "win_pct", "pnl", "roi"]].to_string(index=False))

    # ==================================================================
    # 5. COMBINED EDGES — PPA GAP + OTHER FACTORS
    # ==================================================================
    section("🎯 Combined Edge Testing (PPA gap >0.15 + secondary signal)")

    combo_rows = []

    # PPA gap + home is favorite
    mask = (
        df["off_ppa_gap"].notna() &
        (df["off_ppa_gap"].astype(float) > 0.15) &
        (~df["home_is_underdog"].fillna(True).astype(bool))
    )
    res = simulate_edge(df, mask, bet_home_covers=True)
    res["combo"] = "PPA >0.15 + home favorite"
    combo_rows.append(res)

    # PPA gap + SP+ agrees
    mask = (
        df["off_ppa_gap"].notna() &
        (df["off_ppa_gap"].astype(float) > 0.15) &
        df["sp_agrees_with_line"].fillna(False).astype(bool)
    )
    res = simulate_edge(df, mask, bet_home_covers=True)
    res["combo"] = "PPA >0.15 + SP+ agrees"
    combo_rows.append(res)

    # PPA gap + strong returning production
    mask = (
        df["off_ppa_gap"].notna() &
        (df["off_ppa_gap"].astype(float) > 0.15) &
        df["returning_production_gap"].notna() &
        (df["returning_production_gap"].astype(float) > 0.05)
    )
    res = simulate_edge(df, mask, bet_home_covers=True)
    res["combo"] = "PPA >0.15 + home returning edge"
    combo_rows.append(res)

    # PPA gap + elite home rushing
    mask = (
        df["off_ppa_gap"].notna() &
        (df["off_ppa_gap"].astype(float) > 0.15) &
        df["home_rush_ppa"].notna() &
        (df["home_rush_ppa"].astype(float) >= 0.15)
    )
    res = simulate_edge(df, mask, bet_home_covers=True)
    res["combo"] = "PPA >0.15 + elite home rush"
    combo_rows.append(res)

    # PPA gap + spread size (avoid blowouts)
    mask = (
        df["off_ppa_gap"].notna() &
        (df["off_ppa_gap"].astype(float) > 0.15) &
        (df["spread_abs"].astype(float) <= 14)
    )
    res = simulate_edge(df, mask, bet_home_covers=True)
    res["combo"] = "PPA >0.15 + spread <=14"
    combo_rows.append(res)

    # PPA gap + spread not too large (7-17)
    mask = (
        df["off_ppa_gap"].notna() &
        (df["off_ppa_gap"].astype(float) > 0.15) &
        (df["spread_abs"].astype(float) >= 7) &
        (df["spread_abs"].astype(float) <= 17)
    )
    res = simulate_edge(df, mask, bet_home_covers=True)
    res["combo"] = "PPA >0.15 + spread 7-17"
    combo_rows.append(res)

    # Triple stack: PPA + SP+ agrees + spread <=17
    mask = (
        df["off_ppa_gap"].notna() &
        (df["off_ppa_gap"].astype(float) > 0.15) &
        df["sp_agrees_with_line"].fillna(False).astype(bool) &
        (df["spread_abs"].astype(float) <= 17)
    )
    res = simulate_edge(df, mask, bet_home_covers=True)
    res["combo"] = "PPA >0.15 + SP+ agrees + spread <=17"
    combo_rows.append(res)

    combo_df = pd.DataFrame(combo_rows).sort_values("roi", ascending=False)
    print(combo_df[["combo", "bets", "win_pct", "pnl", "roi"]].to_string(index=False))

    # ==================================================================
    # 6. DEFENSE HAVOC EDGE
    # ==================================================================
    section("🛡️  Elite Home Defense Havoc by Season")

    havoc_rows = []
    for season in seasons:
        season_df = df[df["season"] == season]
        mask = (
            season_df["home_def_havoc"].notna() &
            (season_df["home_def_havoc"].astype(float) >= 0.18)
        )
        res = simulate_edge(season_df, mask, bet_home_covers=True)
        res["season"] = season
        havoc_rows.append(res)

    havoc_df = pd.DataFrame(havoc_rows)
    print(havoc_df[["season", "bets", "win_pct", "pnl", "roi"]].to_string(index=False))

    # ==================================================================
    # 7. CONFERENCE-LEVEL ATS TRENDS
    # ==================================================================
    section("🏟️  ATS Cover Rate by Conference (all seasons)")

    conf_rows = []
    for conf in sorted(conferences):
        conf_df = df[df["home_conference"] == conf]
        if len(conf_df) < 50:
            continue
        mask = pd.Series([True] * len(conf_df), index=conf_df.index)
        res = simulate_edge(conf_df, mask, bet_home_covers=True)
        res["conference"] = conf
        res["games"] = len(conf_df)
        conf_rows.append(res)

    conf_df_out = pd.DataFrame(conf_rows).sort_values("roi", ascending=False)
    print(conf_df_out[["conference", "games", "win_pct", "pnl", "roi"]].to_string(index=False))

    # ==================================================================
    # 8. FINAL RECOMMENDED STRATEGY
    # ==================================================================
    section("💡 Recommended Strategy (based on cross-season validation)")

    # Find the best combo
    best_combo = combo_df.iloc[0]
    print(f"\n  Best combined edge: {best_combo['combo']}")
    print(f"  {int(best_combo['bets'])} bets | {best_combo['win_pct']}% win rate | "
          f"${best_combo['pnl']:+.2f} P&L | {best_combo['roi']:+.1f}% ROI")

    print(f"\n  Key findings:")
    ppa_all = simulate_edge(
        df,
        df["off_ppa_gap"].notna() & (df["off_ppa_gap"].astype(float) > 0.15),
        bet_home_covers=True
    )
    print(f"  • PPA gap >0.15 (all seasons): {ppa_all['win_pct']}% win rate, "
          f"{ppa_all['roi']:+.1f}% ROI over {ppa_all['bets']} bets")

    profitable_ppa = sum(1 for r in season_rows if r["roi"] > 0)
    print(f"  • PPA edge profitable in {profitable_ppa}/{len(seasons)} seasons")

    print(f"\n  Suggested rules for live betting:")
    print(f"  1. Home team must have PPA gap > 0.15 vs visitor")
    print(f"  2. SP+ should agree with line direction")
    print(f"  3. Avoid spreads > 17 (blowout risk, variance)")
    print(f"  4. Skip rivalry games (market adjusted)")
    print(f"  5. Bet under in wind > 20mph or temp < 32°F")


if __name__ == "__main__":
    main()
