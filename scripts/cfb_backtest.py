#!/usr/bin/env python3
"""
cfb_backtest.py

Simulate betting $1 on spread and/or O/U for every major conference game
in 2025 using the edge signals from the model.

Strategies tested:
  1. Blind — bet every game (baseline)
  2. Rivalry underdogs — bet underdog whenever rivalry flag is set
  3. Freeze/cold — bet home team + under when temp < 45°F
  4. High wind under — bet under when wind >= 20mph
  5. Elite rushing home — bet home when rush PPA >= 0.20
  6. Home efficiency edge — bet home when off_ppa_gap > 0.15
  7. SP+ upset alert — bet favorite when SP+ strongly disagrees with line direction
  8. Combined — bet when 2+ edges stack

Standard -110 vig assumed (bet $1.10 to win $1.00, or normalized to $1 = win $0.909).

Usage:
  python scripts/cfb_backtest.py
  python scripts/cfb_backtest.py --conferences "SEC,Big Ten,Big 12,ACC"
  python scripts/cfb_backtest.py --min-edges 2   # only bet when 2+ edges agree
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import pandas as pd

def safe_bool(val) -> bool:
    """Safely convert pandas NA/None to False."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return False
    try:
        return bool(val)
    except (TypeError, ValueError):
        return False

ROOT    = Path(__file__).resolve().parents[1]
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")

# Standard -110 vig: risk $1.10 to win $1.00
# Normalized: $1 bet wins $0.909 on win, loses $1.00 on loss
WIN_PAYOUT  = 0.909
LOSS_AMOUNT = 1.00
PUSH_AMOUNT = 0.00

MAJOR_CONFERENCES = {"SEC", "Big Ten", "Big 12", "ACC", "Pac-12"}
ALL_MAJOR = {"SEC", "Big Ten", "Big 12", "ACC", "Pac-12",
             "American Athletic", "Mountain West", "Sun Belt",
             "Mid-American", "Conference USA"}


def bet_result(covered: bool | None, push: bool | None) -> float:
    """Return P&L for a $1 bet."""
    if push:
        return PUSH_AMOUNT
    if covered is True:
        return WIN_PAYOUT
    if covered is False:
        return -LOSS_AMOUNT
    return 0.0  # unknown


def load_games(con: duckdb.DuckDBPyConnection, conferences: set[str]) -> pd.DataFrame:
    """Load 2025 completed games with all context factors."""
    conf_list = "', '".join(conferences)
    return con.execute(f"""
        SELECT
            l.game_id,
            l.season,
            l.week,
            g.home_conference,
            l.home_team,
            l.away_team,
            l.home_score,
            l.away_score,
            l.spread,
            l.over_under,
            l.actual_margin,
            l.total_points,
            l.spread_covered,
            l.spread_push,
            l.ou_result,
            l.ou_push,
            l.spread_abs,
            l.home_is_underdog,
            l.is_big_spread,
            l.sp_agrees_with_line,
            l.sp_upset_alert,
            l.home_sp_rating,
            l.away_sp_rating,
            l.sp_differential,
            -- Extended context
            ctx.is_rivalry_game,
            ctx.temperature,
            ctx.wind_speed,
            ctx.game_indoors,
            ctx.high_wind,
            ctx.rain_game,
            ctx.snow_game,
            ctx.temp_bucket,
            ctx.home_rush_ppa,
            ctx.away_rush_ppa,
            ctx.off_ppa_gap,
            ctx.home_def_havoc,
            ctx.returning_production_gap,
            ctx.home_pct_returning,
            ctx.away_pct_returning,
            ctx.recruiting_gap,
        FROM main_marts.mart_cfbd_line_accuracy l
        LEFT JOIN main_marts.mart_cfbd_game_context ctx
            ON l.game_id = ctx.game_id AND l.provider = ctx.provider
        LEFT JOIN cfbd.games g ON l.game_id = g.game_id
        WHERE l.season = 2025
          AND l.spread_result IN ('covered', 'missed', 'push')
          AND g.home_conference IN ('{conf_list}')
          -- Use consensus: pick one provider per game (Bovada preferred, else first)
          AND l.provider = (
              SELECT coalesce(
                  max(case when provider = 'Bovada' then 'Bovada' end),
                  min(provider)
              )
              FROM cfbd.lines l2
              WHERE l2.game_id = l.game_id AND l2.season = 2025
          )
        ORDER BY l.season, l.week, l.game_id
    """).df()


def apply_edges(row: pd.Series) -> list[str]:
    edges = []

    if safe_bool(row.get("is_rivalry_game")):
        edges.append("rivalry")

    temp = row.get("temperature")
    if not safe_bool(row.get("game_indoors")) and temp is not None and not pd.isna(temp):
        if float(temp) < 32:
            edges.append("freezing")
        elif float(temp) < 45:
            edges.append("cold")

    if safe_bool(row.get("high_wind")) and not safe_bool(row.get("game_indoors")):
        edges.append("high_wind")

    rush_ppa = row.get("home_rush_ppa")
    if rush_ppa is not None and not pd.isna(rush_ppa) and float(rush_ppa) >= 0.20:
        edges.append("elite_rush_home")

    ppa_gap = row.get("off_ppa_gap")
    if ppa_gap is not None and not pd.isna(ppa_gap):
        if float(ppa_gap) > 0.15:
            edges.append("home_off_edge")
        elif float(ppa_gap) < -0.15:
            edges.append("away_off_edge")

    if safe_bool(row.get("sp_upset_alert")):
        edges.append("sp_upset_alert")

    ret_gap = row.get("returning_production_gap")
    if ret_gap is not None and not pd.isna(ret_gap):
        if float(ret_gap) > 0.15:
            edges.append("returning_home_edge")

    return edges


# ---------------------------------------------------------------------------
# Betting strategies
# ---------------------------------------------------------------------------

def strategy_blind_spread(row: pd.Series) -> tuple[str, bool] | None:
    """Bet home team spread every game."""
    return ("spread_home", True)


def strategy_blind_ou(row: pd.Series) -> tuple[str, bool] | None:
    """Bet under every game (slight historical lean)."""
    return ("ou_under", False)  # False = bet under (not over)


def strategy_rivalry_dog(row: pd.Series) -> tuple[str, bool] | None:
    """Bet underdog ATS in rivalry games."""
    if not safe_bool(row.get("is_rivalry_game")):
        return None
    bet_home_covers = safe_bool(row.get("home_is_underdog"))  # if home is dog, bet home covers
    return ("spread", bet_home_covers)


def strategy_freeze_home_under(row):
    temp = row.get("temperature")
    if safe_bool(row.get("game_indoors")) or temp is None or pd.isna(temp):
        return None
    if float(temp) < 45:
        return ("both", "home_under")
    return None


def strategy_high_wind_under(row):
    if safe_bool(row.get("high_wind")) and not safe_bool(row.get("game_indoors")):
        return ("ou_under", False)
    return None


def strategy_home_efficiency(row: pd.Series) -> tuple[str, bool] | None:
    """Bet home team when they have a big offensive efficiency edge."""
    ppa_gap = row.get("off_ppa_gap")
    if ppa_gap is not None and not pd.isna(ppa_gap) and float(ppa_gap) > 0.15:
        return ("spread", True)  # True = bet home covers
    return None


def strategy_sp_upset_alert(row: pd.Series) -> tuple[str, bool] | None:
    """Bet favorite when SP+ strongly disagrees with line (market usually right)."""
    if safe_bool(row.get("sp_upset_alert")):
        # Bet home covers (home is usually the favorite in this scenario)
        return ("spread", not safe_bool(row.get("home_is_underdog")))
    return None


def strategy_multi_edge(row: pd.Series, min_edges: int = 2) -> list[tuple] | None:
    """Bet when multiple edges stack in the same direction."""
    edges = apply_edges(row)
    if len(edges) < min_edges:
        return None

    bets = []

    # If rivalry — lean underdog spread
    if "rivalry" in edges:
        bet_home = safe_bool(row.get("home_is_underdog"))
        bets.append(("spread", bet_home))

    # If cold/freezing + wind — lean under
    if ("freezing" in edges or "cold" in edges or "high_wind" in edges):
        bets.append(("ou", False))  # under

    # If home efficiency edge — lean home
    if "home_off_edge" in edges:
        bets.append(("spread", True))

    return bets if bets else None


# ---------------------------------------------------------------------------
# Simulate
# ---------------------------------------------------------------------------

def simulate_strategy(df: pd.DataFrame, strategy_fn, name: str,
                      min_edges: int = 1) -> dict:
    bets = 0
    wins = 0
    losses = 0
    pushes = 0
    pnl = 0.0

    for _, row in df.iterrows():
        result = strategy_fn(row)
        if result is None:
            continue

        # Handle multi-bet strategies
        if isinstance(result, list):
            bet_list = result
        else:
            bet_list = [result]

        for bet_type, bet_direction in bet_list:
            bets += 1

            if bet_type in ("spread", "spread_home"):
                if bet_direction is True:  # betting home covers
                    covered = row.get("spread_covered")
                    push = row.get("spread_push")
                else:  # betting away covers
                    covered = not row.get("spread_covered") if row.get("spread_covered") is not None else None
                    push = row.get("spread_push")
                p = bet_result(covered, push)

            elif bet_type in ("ou", "ou_under"):
                ou = row.get("ou_result")
                push = row.get("ou_push")
                if bet_direction is False:  # betting under
                    covered = ou == "under" if ou else None
                else:  # betting over
                    covered = ou == "over" if ou else None
                p = bet_result(covered, push)

            elif bet_type == "both":
                # Spread: home covers
                covered_s = row.get("spread_covered")
                push_s = row.get("spread_push")
                pnl += bet_result(covered_s, push_s)
                bets += 1  # extra bet
                if bet_result(covered_s, push_s) > 0:
                    wins += 1
                elif bet_result(covered_s, push_s) < 0:
                    losses += 1
                else:
                    pushes += 1

                # O/U: under
                ou = row.get("ou_result")
                push_o = row.get("ou_push")
                covered_o = ou == "under" if ou else None
                p = bet_result(covered_o, push_o)
            else:
                continue

            pnl += p
            if p > 0:
                wins += 1
            elif p < 0:
                losses += 1
            else:
                pushes += 1

    roi = (pnl / bets * 100) if bets else 0
    win_pct = (wins / (wins + losses) * 100) if (wins + losses) else 0

    return {
        "strategy": name,
        "bets":     bets,
        "wins":     wins,
        "losses":   losses,
        "pushes":   pushes,
        "win_pct":  round(win_pct, 1),
        "pnl":      round(pnl, 2),
        "roi_pct":  round(roi, 2),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--conferences", default="SEC,Big Ten,Big 12,ACC,Pac-12",
                   help="Comma-separated conferences to include")
    p.add_argument("--all-conferences", action="store_true",
                   help="Include all major conferences")
    p.add_argument("--min-edges", type=int, default=2,
                   help="Min edges required for multi-edge strategy")
    args = p.parse_args()

    if args.all_conferences:
        conferences = ALL_MAJOR
    else:
        conferences = {c.strip() for c in args.conferences.split(",")}

    con = duckdb.connect(DB_PATH, read_only=True)
    print(f"Loading 2025 games for: {', '.join(sorted(conferences))}...")
    df = load_games(con, conferences)
    con.close()

    print(f"Loaded {len(df)} games\n")

    if df.empty:
        print("No games found. Check conferences and make sure mart_cfbd_game_context is built.")
        return

    strategies = [
        (strategy_blind_spread,     "Blind — home spread every game"),
        (strategy_blind_ou,         "Blind — under every game"),
        (strategy_rivalry_dog,      "Rivalry underdog ATS"),
        (strategy_freeze_home_under,"Cold/freeze — home + under"),
        (strategy_high_wind_under,  "High wind — under"),
        (strategy_home_efficiency,  "Home efficiency edge (PPA gap >0.15)"),
        (strategy_sp_upset_alert,   "SP+ upset alert — bet favorite"),
        (lambda r: strategy_multi_edge(r, args.min_edges),
                                    f"Multi-edge ({args.min_edges}+ signals)"),
    ]

    results = []
    for fn, name in strategies:
        res = simulate_strategy(df, fn, name)
        results.append(res)

    results_df = pd.DataFrame(results).sort_values("pnl", ascending=False)

    print(f"{'='*70}")
    print(f"  2025 CFB BACKTEST — $1/bet, -110 vig")
    print(f"  Conferences: {', '.join(sorted(conferences))}")
    print(f"{'='*70}")
    print(results_df.to_string(index=False))
    print(f"\n{'='*70}")

    # Best strategy detail
    best = results_df.iloc[0]
    print(f"\n  Best strategy: {best['strategy']}")
    print(f"  {int(best['bets'])} bets | {best['win_pct']}% win rate | "
          f"${best['pnl']:+.2f} P&L | {best['roi_pct']:+.1f}% ROI")

    # Highlight any strategy with positive ROI
    profitable = results_df[results_df["roi_pct"] > 0]
    if not profitable.empty:
        print(f"\n  ✅ Profitable strategies: {len(profitable)}")
        for _, row in profitable.iterrows():
            print(f"     {row['strategy']}: ${row['pnl']:+.2f} ({row['roi_pct']:+.1f}% ROI)")
    else:
        print("\n  ❌ No profitable strategies — model needs refinement")


if __name__ == "__main__":
    main()
