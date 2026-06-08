#!/usr/bin/env python3
"""
backtest_full_model.py

Runs the complete 14-signal ONS model against 2021-2025 historical data.
Simulates $1 bets at standard -110 vig.

Payout:
  WIN:  +$0.909 (bet $1, win $0.909)
  LOSS: -$1.000
  PUSH:  $0.000

Usage:
  python scripts/backtest_full_model.py
  python scripts/backtest_full_model.py --season 2024
  python scripts/backtest_full_model.py --min-confidence 80
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

ROOT    = Path(__file__).resolve().parents[1]
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")


def safe_float(val, default=None):
    if val is None: return default
    try:
        f = float(val)
        return None if f != f else f  # NaN check
    except (TypeError, ValueError):
        return default


def score_game(row: pd.Series) -> tuple[int, list[str], list[str]]:
    """
    Apply the full 14-signal model to a historical game row.
    Returns (confidence, edges, warnings).
    """
    confidence = 50
    edges: list[str] = []
    warnings: list[str] = []

    home      = str(row.get("home_team", ""))
    away      = str(row.get("away_team", ""))
    spread    = safe_float(row.get("spread"))
    if spread is None:
        return 0, [], []

    abs_spread  = abs(spread)
    home_is_fav = spread < 0

    # ── Hard spread filters ───────────────────────────────────────────────
    if abs_spread > 28:
        return 0, [], []

    ppa_gap = safe_float(row.get("off_ppa_gap"))

    if abs_spread > 21 and (ppa_gap is None or abs(ppa_gap) < 0.25):
        return 0, [], []

    # ── Rule 4: PPA gap ───────────────────────────────────────────────────
    has_ppa_edge = ppa_gap is not None and abs(ppa_gap) > 0.15
    if not has_ppa_edge:
        return 0, [], []  # PPA is required — no edge, no pick

    if abs(ppa_gap) > 0.30:
        edges.append(f"PPA gap {ppa_gap:+.3f} — EXTREME")
        confidence += 25
    else:
        edges.append(f"PPA gap {ppa_gap:+.3f} — primary signal")
        confidence += 15

    # ── Rule 5: Spread range ──────────────────────────────────────────────
    if 3 <= abs_spread <= 7:
        edges.append(f"Spread {spread:+.1f} prime range (3-7)")
        confidence += 10
    elif 10 <= abs_spread <= 14:
        edges.append(f"Spread {spread:+.1f} solid range (10-14)")
        confidence += 8
    elif 14 < abs_spread <= 17:
        confidence -= 8
    elif 17 < abs_spread <= 21:
        confidence -= 12
    elif abs_spread > 21:
        confidence -= 15

    # ── Rule 6: SP+ alignment ────────────────────────────────────────────
    sp_agrees = row.get("sp_agrees_with_line")
    if sp_agrees is not None:
        if bool(sp_agrees):
            edges.append("SP+ confirms PPA")
            confidence += 7
        else:
            warnings.append("SP+ disagrees")
            confidence -= 4

    # ── Rule 7: Team tier ─────────────────────────────────────────────────
    bet_team = home if ppa_gap > 0 else away
    home_tier = str(row.get("home_tier", "NEUTRAL"))
    away_tier = str(row.get("away_tier", "NEUTRAL"))
    bet_tier  = home_tier if bet_team == home else away_tier

    if bet_tier == "ELITE":
        edges.append(f"{bet_team} ELITE tier")
        confidence += 12
    elif bet_tier == "STRONG":
        edges.append(f"{bet_team} STRONG tier")
        confidence += 7
    elif bet_tier == "FADE":
        warnings.append(f"{bet_team} FADE tier")
        confidence -= 12
    elif bet_tier == "STRONG_FADE":
        warnings.append(f"{bet_team} STRONG_FADE tier")
        confidence -= 18

    # ── Rule 8: Conference filter ─────────────────────────────────────────
    home_conf = str(row.get("home_conference", ""))
    if home_is_fav and ppa_gap > 0:
        if home_conf in ("Big Ten", "ACC", "Mountain West", "American Athletic"):
            warnings.append(f"{home_conf} home ATS headwind")
            confidence -= 6
        elif home_conf == "Sun Belt":
            confidence -= 3
        elif home_conf in ("Big 12", "Pac-12"):
            edges.append(f"{home_conf} home ATS tailwind")
            confidence += 3

    # ── Rule 9a: Returning production ────────────────────────────────────
    ret_gap = safe_float(row.get("returning_production_gap"))
    if ret_gap is not None:
        if ret_gap > 0.05:
            edges.append(f"Home returning edge {ret_gap:+.2f}")
            confidence += 6
        elif ret_gap < -0.05:
            if ppa_gap < 0:
                edges.append(f"Away returning edge {ret_gap:+.2f}")
                confidence += 6
            else:
                warnings.append(f"Away returning edge {ret_gap:+.2f}")
                confidence -= 2

    # ── Rule 10: Coach H2H ────────────────────────────────────────────────
    # Not available in game_context mart — skip in backtest
    # (would require joining game-by-game coach H2H which is expensive)

    # ── Rule 11: Travel distance ──────────────────────────────────────────
    travel = safe_float(row.get("travel_miles"))
    betting_away = ppa_gap < 0
    if travel is not None:
        if travel >= 1500:
            if not betting_away:
                edges.append(f"Away travels {travel:.0f}mi")
                confidence += 2
            else:
                warnings.append(f"Betting away team traveling {travel:.0f}mi")
                confidence -= 2
        elif travel >= 1000:
            if not betting_away:
                edges.append(f"Away travels {travel:.0f}mi")
                confidence += 1
            else:
                confidence -= 1

    # ── Rule 12: Recruiting talent gap ───────────────────────────────────
    rec_gap = safe_float(row.get("recruiting_gap"))
    if rec_gap is not None:
        if abs(rec_gap) <= 10:
            edges.append(f"Talent parity ({rec_gap:+.0f}pts) + PPA — 71.2% hist")
            confidence += 10
        elif rec_gap < -10 and ppa_gap > 0:
            edges.append(f"Home efficiency beats talent gap")
            confidence += 6
        elif rec_gap > 10 and ppa_gap < 0:
            edges.append(f"Away efficiency beats talent gap")
            confidence += 6
        elif rec_gap > 10 and ppa_gap > 0:
            edges.append(f"Home talent confirms PPA")
            confidence += 3
        elif rec_gap < -10 and ppa_gap < 0:
            edges.append(f"Away talent confirms PPA")
            confidence += 3

    # ── Rule 13: Success rate differential ───────────────────────────────
    sr_diff = safe_float(row.get("home_off_success_rate"))
    away_def_sr = safe_float(row.get("away_def_success_rate"))
    if sr_diff is not None and away_def_sr is not None:
        net_sr = sr_diff - away_def_sr
        if abs(net_sr) <= 0.05:
            edges.append(f"Success rate parity + PPA — 65.3% hist")
            confidence += 8
        elif net_sr < -0.05 and ppa_gap > 0:
            edges.append(f"Home efficiency overcomes SR gap")
            confidence += 5
        elif net_sr > 0.05 and ppa_gap < 0:
            edges.append(f"Away efficiency overcomes SR gap")
            confidence += 5
        elif net_sr > 0.05 and ppa_gap > 0:
            edges.append(f"Home SR confirms PPA")
            confidence += 3

    # ── Rule 14: Defensive havoc ──────────────────────────────────────────
    home_havoc = safe_float(row.get("home_def_havoc"))
    away_havoc = safe_float(row.get("away_def_havoc"))
    if home_havoc is not None and away_havoc is not None:
        hd = home_havoc - away_havoc
        if hd > 0.02:
            if ppa_gap > 0:
                edges.append(f"Home havoc edge {hd:+.3f}")
                confidence += 7
            else:
                warnings.append(f"Home havoc works against away bet")
                confidence -= 5
        elif hd < -0.02:
            if ppa_gap < 0:
                edges.append(f"Away havoc edge {hd:+.3f}")
                confidence += 7
            else:
                warnings.append(f"Away havoc works against home bet")
                confidence -= 5

    return min(confidence, 95), edges, warnings


def run_backtest(seasons: list[int], min_confidence: int) -> None:
    print(f"Loading historical data from DuckDB...")
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
    except Exception as e:
        print(f"Cannot open DuckDB: {e}")
        sys.exit(1)

    # Pull all required fields from game_context + line_accuracy + travel + profiles
    df = con.execute("""
        SELECT
            gc.game_id,
            gc.season,
            gc.week,
            gc.home_team,
            gc.away_team,
            gc.home_conference,
            gc.spread,
            gc.spread_covered,
            gc.spread_result,
            gc.ou_result,
            gc.home_score,
            gc.away_score,
            gc.off_ppa_gap,
            gc.sp_agrees_with_line,
            gc.returning_production_gap,
            gc.recruiting_gap,
            gc.home_off_success_rate,
            gc.away_def_success_rate,
            gc.home_def_havoc,
            gc.away_def_havoc,
            ht.tier AS home_tier,
            at2.tier AS away_tier,
            td.travel_miles
        FROM main_marts.mart_cfbd_game_context gc
        LEFT JOIN cfbd.team_profiles ht ON ht.team = gc.home_team
        LEFT JOIN cfbd.team_profiles at2 ON at2.team = gc.away_team
        LEFT JOIN main_marts.mart_cfbd_travel_distance td ON td.game_id = gc.game_id
        WHERE gc.spread_result IN ('covered', 'missed', 'push')
          AND gc.season IN ({})
          AND gc.spread IS NOT NULL
    """.format(",".join(str(s) for s in seasons))).df()

    con.close()

    print(f"Loaded {len(df):,} games across seasons {seasons}\n")

    # Score every game
    results = []
    for _, row in df.iterrows():
        confidence, edges, warnings = score_game(row)
        if confidence < min_confidence:
            continue

        spread     = float(row["spread"])
        ppa_gap    = safe_float(row.get("off_ppa_gap"), 0)
        bet_home   = ppa_gap > 0
        covered    = str(row.get("spread_result", "")) == "covered"
        pushed     = str(row.get("spread_result", "")) == "push"

        # Home cover means spread_covered=True from home perspective
        # If we're betting home: win when covered, lose when not
        # If we're betting away: win when NOT covered, lose when covered
        if pushed:
            pnl = 0.0
            outcome = "push"
        elif bet_home:
            pnl     = 0.909 if covered else -1.0
            outcome = "win" if covered else "loss"
        else:
            pnl     = 0.909 if not covered else -1.0
            outcome = "win" if not covered else "loss"

        results.append({
            "season":     int(row["season"]),
            "week":       int(row["week"]),
            "home_team":  row["home_team"],
            "away_team":  row["away_team"],
            "bet_team":   row["home_team"] if bet_home else row["away_team"],
            "spread":     spread,
            "confidence": confidence,
            "edges":      len(edges),
            "ppa_gap":    ppa_gap,
            "outcome":    outcome,
            "pnl":        pnl,
        })

    if not results:
        print("No qualifying picks found.")
        return

    rdf = pd.DataFrame(results)

    # ── Overall results ───────────────────────────────────────────────────
    total_bets  = len(rdf)
    wins        = (rdf["outcome"] == "win").sum()
    losses      = (rdf["outcome"] == "loss").sum()
    pushes      = (rdf["outcome"] == "push").sum()
    total_pnl   = rdf["pnl"].sum()
    roi         = total_pnl / total_bets * 100
    win_pct     = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0

    print("=" * 60)
    print("FULL MODEL BACKTEST — 2021-2025")
    print("=" * 60)
    print(f"Seasons:         {', '.join(str(s) for s in sorted(rdf['season'].unique()))}")
    print(f"Min confidence:  {min_confidence}%")
    print(f"Total bets:      {total_bets:,}")
    print(f"Record:          {wins}-{losses}-{pushes}")
    print(f"Win rate:        {win_pct:.1f}%")
    print(f"Total P&L:       ${total_pnl:+.2f}")
    print(f"ROI:             {roi:+.1f}%")
    print(f"Avg bet:         $1.00")
    print(f"Breakeven rate:  52.4% (at -110 vig)")
    print()

    # ── By season ────────────────────────────────────────────────────────
    print("─" * 60)
    print("BY SEASON")
    print("─" * 60)
    for season, grp in rdf.groupby("season"):
        g_wins   = (grp["outcome"] == "win").sum()
        g_losses = (grp["outcome"] == "loss").sum()
        g_pushes = (grp["outcome"] == "push").sum()
        g_pnl    = grp["pnl"].sum()
        g_roi    = g_pnl / len(grp) * 100
        g_wp     = g_wins / (g_wins + g_losses) * 100 if (g_wins + g_losses) > 0 else 0
        marker   = " ✅" if g_pnl > 0 else " ❌"
        print(f"  {season}: {len(grp):3d} bets  {g_wins}-{g_losses}-{g_pushes}  "
              f"{g_wp:.1f}% cover  ${g_pnl:+.2f}  ROI {g_roi:+.1f}%{marker}")
    print()

    # ── By confidence tier ────────────────────────────────────────────────
    print("─" * 60)
    print("BY CONFIDENCE TIER")
    print("─" * 60)
    bins   = [(60, 70), (70, 80), (80, 90), (90, 96)]
    labels = ["60-69%", "70-79%", "80-89%", "90-95%"]
    for (lo, hi), label in zip(bins, labels):
        grp = rdf[(rdf["confidence"] >= lo) & (rdf["confidence"] < hi)]
        if grp.empty:
            continue
        g_wins   = (grp["outcome"] == "win").sum()
        g_losses = (grp["outcome"] == "loss").sum()
        g_pnl    = grp["pnl"].sum()
        g_roi    = g_pnl / len(grp) * 100
        g_wp     = g_wins / (g_wins + g_losses) * 100 if (g_wins + g_losses) > 0 else 0
        print(f"  {label}: {len(grp):3d} bets  {g_wins}-{g_losses}  "
              f"{g_wp:.1f}% cover  ${g_pnl:+.2f}  ROI {g_roi:+.1f}%")
    print()

    # ── By number of signals ─────────────────────────────────────────────
    print("─" * 60)
    print("BY SIGNAL COUNT (edges stacked)")
    print("─" * 60)
    for n_edges, grp in rdf.groupby("edges"):
        if len(grp) < 10:
            continue
        g_wins   = (grp["outcome"] == "win").sum()
        g_losses = (grp["outcome"] == "loss").sum()
        g_pnl    = grp["pnl"].sum()
        g_roi    = g_pnl / len(grp) * 100
        g_wp     = g_wins / (g_wins + g_losses) * 100 if (g_wins + g_losses) > 0 else 0
        print(f"  {n_edges} signals: {len(grp):3d} bets  {g_wins}-{g_losses}  "
              f"{g_wp:.1f}% cover  ROI {g_roi:+.1f}%")
    print()

    # ── By PPA gap threshold ──────────────────────────────────────────────
    print("─" * 60)
    print("BY PPA GAP SIZE")
    print("─" * 60)
    ppa_bins = [(0.15, 0.20, "0.15-0.20"), (0.20, 0.25, "0.20-0.25"),
                (0.25, 0.30, "0.25-0.30"), (0.30, 1.00, "0.30+")]
    for lo, hi, label in ppa_bins:
        grp = rdf[(rdf["ppa_gap"].abs() >= lo) & (rdf["ppa_gap"].abs() < hi)]
        if len(grp) < 5:
            continue
        g_wins   = (grp["outcome"] == "win").sum()
        g_losses = (grp["outcome"] == "loss").sum()
        g_pnl    = grp["pnl"].sum()
        g_roi    = g_pnl / len(grp) * 100
        g_wp     = g_wins / (g_wins + g_losses) * 100 if (g_wins + g_losses) > 0 else 0
        print(f"  PPA {label}: {len(grp):3d} bets  {g_wins}-{g_losses}  "
              f"{g_wp:.1f}% cover  ROI {g_roi:+.1f}%")
    print()

    # ── Profitable seasons check ──────────────────────────────────────────
    seasons_data = rdf.groupby("season")["pnl"].sum()
    profitable   = (seasons_data > 0).sum()
    print("─" * 60)
    print(f"Profitable seasons: {profitable}/{len(seasons_data)}")
    print(f"Breakeven at 52.4% win rate — model at {win_pct:.1f}%")
    if total_pnl > 0:
        print(f"✅ Model is PROFITABLE: ${total_pnl:+.2f} on {total_bets} $1 bets")
    else:
        print(f"❌ Model LOSES MONEY: ${total_pnl:+.2f} on {total_bets} $1 bets")
    print("=" * 60)


def main() -> int:
    p = argparse.ArgumentParser(description="Backtest the full ONS CFB model 2021-2025")
    p.add_argument("--season",         type=int, default=None,
                   help="Single season to test (default: all 2021-2025)")
    p.add_argument("--min-confidence", type=int, default=60,
                   help="Minimum confidence to include a pick (default: 60)")
    args = p.parse_args()

    seasons = [args.season] if args.season else [2021, 2022, 2023, 2024, 2025]
    run_backtest(seasons, args.min_confidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
