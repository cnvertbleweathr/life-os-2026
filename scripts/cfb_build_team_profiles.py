#!/usr/bin/env python3
"""
cfb_build_team_profiles.py

Computes full ATS profiles for every FBS team across 2021-2025
and stores results in DuckDB under cfbd.team_profiles.

Run this once (or at start of each season) to populate the DB.
pregame_lookup.py then queries cfbd.team_profiles at runtime.

Usage:
  python scripts/cfb_build_team_profiles.py
  python scripts/cfb_build_team_profiles.py --min-games 15
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

ROOT    = Path(__file__).resolve().parents[1]
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")

WIN_PAYOUT  = 0.909
LOSS_AMOUNT = 1.00


def safe_bool(val) -> bool:
    if val is None:
        return False
    try:
        if pd.isna(val):
            return False
    except Exception:
        pass
    try:
        return bool(val)
    except Exception:
        return False


def bet_pnl(covered, push) -> float:
    if safe_bool(push):
        return 0.0
    covered_clean = None
    if covered is not None and str(covered) != "<NA>":
        try:
            covered_clean = bool(covered)
        except Exception:
            pass
    if covered_clean is True:
        return WIN_PAYOUT
    if covered_clean is False:
        return -LOSS_AMOUNT
    return 0.0


def load_games(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("""
        SELECT
            l.game_id, l.season, l.week,
            l.home_team, l.away_team,
            g.home_conference, g.away_conference,
            l.spread, l.spread_abs, l.actual_margin,
            l.total_points, l.over_under,
            l.spread_covered, l.spread_push,
            l.ou_result, l.ou_push,
            l.home_is_underdog, l.home_win,
            l.sp_agrees_with_line,
            ctx.off_ppa_gap,
            ctx.is_rivalry_game,
            ctx.temperature, ctx.wind_speed, ctx.game_indoors,
        FROM main_marts.mart_cfbd_line_accuracy l
        LEFT JOIN main_marts.mart_cfbd_game_context ctx
            ON l.game_id = ctx.game_id AND l.provider = ctx.provider
        LEFT JOIN cfbd.games g ON l.game_id = g.game_id
        WHERE l.spread_result IN ('covered', 'missed', 'push')
          AND l.provider = (
              SELECT coalesce(
                  max(case when provider = 'Bovada' then 'Bovada' end),
                  min(provider)
              )
              FROM cfbd.lines l2
              WHERE l2.game_id = l.game_id
          )
    """).df()


def ats_stats(subset: pd.DataFrame, flip: bool = False) -> dict:
    """Compute ATS win/loss/pnl for a subset. flip=True for away perspective."""
    if subset.empty:
        return {"bets": 0, "wins": 0, "losses": 0, "pushes": 0,
                "win_pct": None, "pnl": 0.0, "roi": None}

    pnl = wins = losses = pushes = 0
    for _, row in subset.iterrows():
        covered = row.get("spread_covered")
        push    = row.get("spread_push")

        if flip:
            if covered is not None and str(covered) != "<NA>":
                try:
                    covered = not bool(covered)
                except Exception:
                    covered = None

        p = bet_pnl(covered, safe_bool(push))
        pnl += p
        if p > 0:   wins += 1
        elif p < 0: losses += 1
        else:       pushes += 1

    bets = wins + losses + pushes
    wp   = wins / (wins + losses) * 100 if (wins + losses) else None
    roi  = pnl / bets * 100 if bets else None

    return {
        "bets":    bets,
        "wins":    wins,
        "losses":  losses,
        "pushes":  pushes,
        "win_pct": round(wp, 1) if wp is not None else None,
        "pnl":     round(pnl, 2),
        "roi":     round(roi, 2) if roi is not None else None,
    }


def ou_stats(subset: pd.DataFrame) -> dict:
    if subset.empty:
        return {"bets": 0, "overs": 0, "over_pct": None}
    overs = (subset["ou_result"] == "over").sum()
    bets  = subset["ou_result"].notna().sum()
    pct   = overs / bets * 100 if bets else None
    return {
        "bets":     int(bets),
        "overs":    int(overs),
        "over_pct": round(pct, 1) if pct is not None else None,
    }


def compute_team_profile(df: pd.DataFrame, team: str) -> dict | None:
    home = df[df["home_team"] == team].copy()
    away = df[df["away_team"] == team].copy()
    total = len(home) + len(away)
    if total == 0:
        return None

    # Conference
    conf = home["home_conference"].mode()[0] if not home.empty else \
           away["away_conference"].mode()[0] if not away.empty else "Unknown"

    # Overall
    h_stats = ats_stats(home, flip=False)
    a_stats = ats_stats(away, flip=True)
    total_bets   = h_stats["bets"] + a_stats["bets"]
    total_wins   = h_stats["wins"] + a_stats["wins"]
    total_losses = h_stats["losses"] + a_stats["losses"]
    total_pnl    = h_stats["pnl"]  + a_stats["pnl"]
    total_wp     = total_wins / (total_wins + total_losses) * 100 if (total_wins + total_losses) else None
    total_roi    = total_pnl / total_bets * 100 if total_bets else None

    # Situational splits
    home_fav = home[~home["home_is_underdog"].fillna(True).astype(bool)]
    home_dog = home[home["home_is_underdog"].fillna(False).astype(bool)]
    away_fav = away[away["home_is_underdog"].fillna(False).astype(bool)]   # home is dog = away is fav
    away_dog = away[~away["home_is_underdog"].fillna(True).astype(bool)]   # home is fav = away is dog

    # PPA edge
    home_ppa = home[home["off_ppa_gap"].notna() & (home["off_ppa_gap"].astype(float) > 0.15)]
    away_ppa = away[away["off_ppa_gap"].notna() & (away["off_ppa_gap"].astype(float) < -0.15)]

    # Season breakdown
    all_games = pd.concat([home, away])
    seasons   = sorted(all_games["season"].unique())
    season_rois = []
    for s in seasons:
        sh = home[home["season"] == s]
        sa = away[away["season"] == s]
        sh_s = ats_stats(sh, False)
        sa_s = ats_stats(sa, True)
        sb   = sh_s["bets"] + sa_s["bets"]
        sp   = sh_s["pnl"]  + sa_s["pnl"]
        sr   = sp / sb * 100 if sb else None
        season_rois.append({"season": int(s), "roi": round(sr, 1) if sr else None})

    profitable_seasons = sum(1 for s in season_rois if s["roi"] and s["roi"] > 0)

    # Tier assignment
    if total_roi is not None:
        if total_roi >= 20 and profitable_seasons >= 4:
            tier = "ELITE"
        elif total_roi >= 10 and profitable_seasons >= 3:
            tier = "STRONG"
        elif total_roi <= -20 and profitable_seasons <= 1:
            tier = "STRONG_FADE"
        elif total_roi <= -10:
            tier = "FADE"
        else:
            tier = "NEUTRAL"
    else:
        tier = "NEUTRAL"

    # Best and worst situations
    situations = {
        "home_fav":  ats_stats(home_fav, False),
        "home_dog":  ats_stats(home_dog, False),
        "away_fav":  ats_stats(away_fav, True),
        "away_dog":  ats_stats(away_dog, True),
        "home_ppa":  ats_stats(home_ppa, False),
        "away_ppa":  ats_stats(away_ppa, True),
        "home_ou":   ou_stats(home),
        "away_ou":   ou_stats(away),
    }

    # Find best/worst situation ROI
    sit_rois = {k: v["roi"] for k, v in situations.items()
                if v.get("roi") is not None and v.get("bets", 0) >= 5
                and k not in ("home_ou", "away_ou")}

    best_situation  = max(sit_rois, key=sit_rois.get) if sit_rois else None
    worst_situation = min(sit_rois, key=sit_rois.get) if sit_rois else None

    return {
        "team":               team,
        "conference":         conf,
        "seasons_in_data":    len(seasons),
        "total_games":        total_bets,
        "total_wins":         total_wins,
        "total_losses":       total_losses,
        "total_win_pct":      round(total_wp, 1) if total_wp is not None else None,
        "total_pnl":          round(total_pnl, 2),
        "total_roi":          round(total_roi, 2) if total_roi is not None else None,
        "profitable_seasons": profitable_seasons,
        "tier":               tier,

        # Home splits
        "home_bets":          h_stats["bets"],
        "home_wins":          h_stats["wins"],
        "home_roi":           h_stats["roi"],
        "home_fav_bets":      situations["home_fav"]["bets"],
        "home_fav_roi":       situations["home_fav"]["roi"],
        "home_dog_bets":      situations["home_dog"]["bets"],
        "home_dog_roi":       situations["home_dog"]["roi"],

        # Away splits
        "away_bets":          a_stats["bets"],
        "away_wins":          a_stats["wins"],
        "away_roi":           a_stats["roi"],
        "away_fav_bets":      situations["away_fav"]["bets"],
        "away_fav_roi":       situations["away_fav"]["roi"],
        "away_dog_bets":      situations["away_dog"]["bets"],
        "away_dog_roi":       situations["away_dog"]["roi"],

        # PPA edge
        "home_ppa_bets":      situations["home_ppa"]["bets"],
        "home_ppa_roi":       situations["home_ppa"]["roi"],
        "away_ppa_bets":      situations["away_ppa"]["bets"],
        "away_ppa_roi":       situations["away_ppa"]["roi"],

        # O/U
        "home_over_pct":      situations["home_ou"]["over_pct"],
        "away_over_pct":      situations["away_ou"]["over_pct"],

        # Best/worst
        "best_situation":     best_situation,
        "best_situation_roi": sit_rois.get(best_situation),
        "worst_situation":    worst_situation,
        "worst_situation_roi":sit_rois.get(worst_situation),

        # Season breakdown (JSON)
        "season_rois_json":   json.dumps(season_rois),

        "computed_at":        datetime.now().isoformat(),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--min-games", type=int, default=15)
    args = p.parse_args()

    con = duckdb.connect(DB_PATH)

    print("Loading game data...")
    df = load_games(con)
    print(f"Loaded {len(df):,} games\n")

    teams = sorted(set(df["home_team"].unique()) | set(df["away_team"].unique()))
    print(f"Computing profiles for {len(teams)} teams...")

    rows = []
    for i, team in enumerate(teams, 1):
        h = df[df["home_team"] == team]
        a = df[df["away_team"] == team]
        if len(h) + len(a) < args.min_games:
            continue
        profile = compute_team_profile(df, team)
        if profile:
            rows.append(profile)
        if i % 50 == 0:
            print(f"  {i}/{len(teams)} teams processed...")

    print(f"\nComputed {len(rows)} team profiles")

    # Write to DuckDB
    profiles_df = pd.DataFrame(rows)

    con.execute("CREATE SCHEMA IF NOT EXISTS cfbd")
    con.execute("DROP TABLE IF EXISTS cfbd.team_profiles")
    con.execute("""
        CREATE TABLE cfbd.team_profiles AS
        SELECT * FROM profiles_df
    """)

    print(f"Saved to cfbd.team_profiles")

    # Summary
    print(f"\n{'='*50}")
    print("TIER BREAKDOWN:")
    tier_counts = profiles_df.groupby("tier").size().sort_values(ascending=False)
    for tier, count in tier_counts.items():
        print(f"  {tier}: {count} teams")

    print(f"\nTOP 10 OVERALL ROI:")
    top = profiles_df.nlargest(10, "total_roi")[["team","conference","total_roi","profitable_seasons","tier"]]
    print(top.to_string(index=False))

    print(f"\nBOTTOM 10 OVERALL ROI:")
    bottom = profiles_df.nsmallest(10, "total_roi")[["team","conference","total_roi","profitable_seasons","tier"]]
    print(bottom.to_string(index=False))

    con.close()
    print(f"\n✓ Done — {len(rows)} team profiles stored in cfbd.team_profiles")


if __name__ == "__main__":
    main()
