#!/usr/bin/env python3
"""
cfb_team_analysis.py

Per-team ATS analysis across 2021-2025.
Identifies teams with consistent betting edges — as favorites, underdogs,
at home, on the road, and in PPA-gap situations.

Usage:
  python scripts/cfb_team_analysis.py
  python scripts/cfb_team_analysis.py --team "Ohio State"
  python scripts/cfb_team_analysis.py --conference SEC
  python scripts/cfb_team_analysis.py --min-games 30
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import pandas as pd
import numpy as np

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
    if covered is True:
        return WIN_PAYOUT
    if covered is False:
        return -LOSS_AMOUNT
    return 0.0


def load_data(con) -> pd.DataFrame:
    """Load all games with context, one row per game (not per provider)."""
    return con.execute("""
        SELECT
            l.game_id, l.season, l.week,
            l.home_team, l.away_team,
            g.home_conference, g.away_conference,
            l.home_score, l.away_score,
            l.spread, l.spread_abs, l.actual_margin,
            l.total_points, l.over_under,
            l.spread_covered, l.spread_push,
            l.ou_result, l.ou_push,
            l.home_is_underdog, l.home_win,
            l.sp_agrees_with_line, l.sp_upset_alert,
            l.sp_differential,
            ctx.off_ppa_gap, ctx.home_off_ppa, ctx.away_off_ppa,
            ctx.home_def_ppa, ctx.away_def_ppa,
            ctx.home_rush_ppa, ctx.away_rush_ppa,
            ctx.home_def_havoc, ctx.away_def_havoc,
            ctx.home_def_success_rate, ctx.away_def_success_rate,
            ctx.is_rivalry_game,
            ctx.temperature, ctx.wind_speed, ctx.game_indoors,
            ctx.returning_production_gap,
            ctx.home_recruiting_rank, ctx.away_recruiting_rank,
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
        ORDER BY l.season, l.week
    """).df()


def compute_team_stats(df: pd.DataFrame, team: str) -> dict:
    """Compute full ATS profile for a single team across all appearances."""

    # Home games
    home = df[df["home_team"] == team].copy()
    # Away games — flip perspective
    away = df[df["away_team"] == team].copy()

    def ats_stats(subset: pd.DataFrame, is_home: bool) -> dict:
        if subset.empty:
            return {"bets": 0, "wins": 0, "losses": 0, "pushes": 0,
                    "win_pct": 0.0, "pnl": 0.0, "roi": 0.0}
        pnl = wins = losses = pushes = 0
        for _, row in subset.iterrows():
            covered = row.get("spread_covered")
            push    = row.get("spread_push")
            if not is_home:
                # Away team covers when home team doesn't
                covered = not safe_bool(covered) if covered is not None and str(covered) != '<NA>' else None
            p = bet_pnl(covered, safe_bool(push))
            pnl += p
            if p > 0:   wins += 1
            elif p < 0: losses += 1
            else:       pushes += 1
        bets = wins + losses + pushes
        wp   = wins / (wins + losses) * 100 if (wins + losses) else 0
        roi  = pnl / bets * 100 if bets else 0
        return {"bets": bets, "wins": wins, "losses": losses, "pushes": pushes,
                "win_pct": round(wp, 1), "pnl": round(pnl, 2), "roi": round(roi, 2)}

    # Overall
    all_games = pd.concat([home, away])
    overall   = ats_stats(home, is_home=True)
    overall_away = ats_stats(away, is_home=False)
    total_bets = overall["bets"] + overall_away["bets"]
    total_wins = overall["wins"] + overall_away["wins"]
    total_losses = overall["losses"] + overall_away["losses"]
    total_pnl  = overall["pnl"] + overall_away["pnl"]
    total_wp   = total_wins / (total_wins + total_losses) * 100 if (total_wins + total_losses) else 0
    total_roi  = total_pnl / total_bets * 100 if total_bets else 0

    # As home favorite
    home_fav = home[~home["home_is_underdog"].fillna(True).astype(bool)]
    # As home underdog
    home_dog = home[home["home_is_underdog"].fillna(False).astype(bool)]
    # As away underdog (home team is favorite)
    away_dog = away[~away["home_is_underdog"].fillna(True).astype(bool)]
    # As away favorite
    away_fav = away[away["home_is_underdog"].fillna(False).astype(bool)]

    # PPA gap situations — when this team has the advantage
    home_ppa_edge = home[
        home["off_ppa_gap"].notna() &
        (home["off_ppa_gap"].astype(float) > 0.15)
    ]
    away_ppa_edge = away[
        away["off_ppa_gap"].notna() &
        (away["off_ppa_gap"].astype(float) < -0.15)  # away team has edge
    ]

    # Rivalry games
    rivalry_home = home[home["is_rivalry_game"].fillna(False).astype(bool)]
    rivalry_away = away[away["is_rivalry_game"].fillna(False).astype(bool)]

    # O/U trends
    def ou_stats(subset: pd.DataFrame, is_home: bool) -> dict:
        if subset.empty:
            return {"bets": 0, "overs": 0, "over_pct": 0.0}
        overs = (subset["ou_result"] == "over").sum()
        bets  = subset["ou_result"].notna().sum()
        pct   = overs / bets * 100 if bets else 0
        return {"bets": int(bets), "overs": int(overs), "over_pct": round(pct, 1)}

    home_ou = ou_stats(home, True)
    away_ou = ou_stats(away, False)

    # Season by season
    season_rows = []
    for season in sorted(all_games["season"].unique()):
        h = home[home["season"] == season]
        a = away[away["season"] == season]
        hs = ats_stats(h, True)
        as_ = ats_stats(a, False)
        sb  = hs["bets"] + as_["bets"]
        sw  = hs["wins"] + as_["wins"]
        sl  = hs["losses"] + as_["losses"]
        sp  = hs["pnl"] + as_["pnl"]
        sr  = sp / sb * 100 if sb else 0
        swp = sw / (sw + sl) * 100 if (sw + sl) else 0
        season_rows.append({
            "season": int(season), "bets": sb, "wins": sw, "losses": sl,
            "win_pct": round(swp, 1), "pnl": round(sp, 2), "roi": round(sr, 2)
        })

    conference = home["home_conference"].mode()[0] if not home.empty else \
                 away["away_conference"].mode()[0] if not away.empty else "Unknown"

    return {
        "team":        team,
        "conference":  conference,
        "seasons":     len(all_games["season"].unique()),
        "total_games": total_bets,
        "total_wins":  total_wins,
        "total_losses":total_losses,
        "total_win_pct": round(total_wp, 1),
        "total_pnl":   round(total_pnl, 2),
        "total_roi":   round(total_roi, 2),

        # Home/away splits
        "home_ats":    overall,
        "away_ats":    overall_away,
        "home_fav_ats": ats_stats(home_fav, True),
        "home_dog_ats": ats_stats(home_dog, True),
        "away_fav_ats": ats_stats(away_fav, False),
        "away_dog_ats": ats_stats(away_dog, False),

        # PPA edge situations
        "ppa_edge_home": ats_stats(home_ppa_edge, True),
        "ppa_edge_away": ats_stats(away_ppa_edge, False),

        # Rivalry
        "rivalry_home": ats_stats(rivalry_home, True),
        "rivalry_away": ats_stats(rivalry_away, False),

        # O/U
        "home_ou":     home_ou,
        "away_ou":     away_ou,

        # Season breakdown
        "by_season":   season_rows,
    }


def print_team_report(stats: dict) -> None:
    t = stats
    print(f"\n{'='*60}")
    print(f"  🏈 {t['team']} — {t['conference']}")
    print(f"  {t['seasons']} seasons | {t['total_games']} games")
    print(f"{'='*60}")

    print(f"\n  OVERALL ATS: {t['total_win_pct']}% | "
          f"${t['total_pnl']:+.2f} | {t['total_roi']:+.1f}% ROI")

    print(f"\n  ┌─ HOME ({t['home_ats']['bets']} games): "
          f"{t['home_ats']['win_pct']}% | ${t['home_ats']['pnl']:+.2f} | "
          f"{t['home_ats']['roi']:+.1f}% ROI")
    print(f"  │   ├─ As favorite: {t['home_fav_ats']['bets']}g | "
          f"{t['home_fav_ats']['win_pct']}% | {t['home_fav_ats']['roi']:+.1f}% ROI")
    print(f"  │   └─ As underdog: {t['home_dog_ats']['bets']}g | "
          f"{t['home_dog_ats']['win_pct']}% | {t['home_dog_ats']['roi']:+.1f}% ROI")
    print(f"  └─ AWAY ({t['away_ats']['bets']} games): "
          f"{t['away_ats']['win_pct']}% | ${t['away_ats']['pnl']:+.2f} | "
          f"{t['away_ats']['roi']:+.1f}% ROI")
    print(f"      ├─ As favorite: {t['away_fav_ats']['bets']}g | "
          f"{t['away_fav_ats']['win_pct']}% | {t['away_fav_ats']['roi']:+.1f}% ROI")
    print(f"      └─ As underdog: {t['away_dog_ats']['bets']}g | "
          f"{t['away_dog_ats']['win_pct']}% | {t['away_dog_ats']['roi']:+.1f}% ROI")

    ppa_h = t["ppa_edge_home"]
    ppa_a = t["ppa_edge_away"]
    if ppa_h["bets"] + ppa_a["bets"] > 0:
        print(f"\n  PPA EDGE SITUATIONS:")
        if ppa_h["bets"] > 0:
            print(f"    Home with PPA >0.15 edge: {ppa_h['bets']}g | "
                  f"{ppa_h['win_pct']}% | {ppa_h['roi']:+.1f}% ROI")
        if ppa_a["bets"] > 0:
            print(f"    Away with PPA >0.15 edge: {ppa_a['bets']}g | "
                  f"{ppa_a['win_pct']}% | {ppa_a['roi']:+.1f}% ROI")

    rou_h = t["home_ou"]
    rou_a = t["away_ou"]
    print(f"\n  O/U TRENDS:")
    print(f"    Home games: {rou_h['over_pct']}% overs ({rou_h['overs']}/{rou_h['bets']})")
    print(f"    Away games: {rou_a['over_pct']}% overs ({rou_a['overs']}/{rou_a['bets']})")

    print(f"\n  BY SEASON:")
    for row in t["by_season"]:
        bar = "█" * min(int(row["roi"] / 5) + 5, 15) if row["roi"] > -25 else ""
        print(f"    {row['season']}: {row['bets']}g | {row['win_pct']}% | "
              f"{row['roi']:+.1f}% ROI  {bar}")


def build_league_table(df: pd.DataFrame, min_games: int,
                       conference: str = None) -> pd.DataFrame:
    """Build sortable summary table for all teams."""
    teams = set(df["home_team"].unique()) | set(df["away_team"].unique())
    rows  = []

    for team in sorted(teams):
        home = df[df["home_team"] == team]
        away = df[df["away_team"] == team]

        if len(home) + len(away) < min_games:
            continue

        conf = home["home_conference"].mode()[0] if not home.empty else \
               away["away_conference"].mode()[0] if not away.empty else "?"

        if conference and conf.lower() != conference.lower():
            continue

        stats = compute_team_stats(df, team)

        # Key situational stats
        ppa_h = stats["ppa_edge_home"]
        ppa_a = stats["ppa_edge_away"]
        ppa_bets = ppa_h["bets"] + ppa_a["bets"]
        ppa_wins  = ppa_h["wins"] + ppa_a["wins"]
        ppa_pnl   = ppa_h["pnl"]  + ppa_a["pnl"]
        ppa_roi   = ppa_pnl / ppa_bets * 100 if ppa_bets else None

        rows.append({
            "team":           team,
            "conf":           conf,
            "games":          stats["total_games"],
            "overall_wp":     stats["total_win_pct"],
            "overall_roi":    stats["total_roi"],
            "home_roi":       stats["home_ats"]["roi"],
            "away_roi":       stats["away_ats"]["roi"],
            "home_dog_roi":   stats["home_dog_ats"]["roi"],
            "away_dog_roi":   stats["away_dog_ats"]["roi"],
            "ppa_edge_bets":  ppa_bets,
            "ppa_edge_roi":   round(ppa_roi, 1) if ppa_roi is not None else None,
            "home_over_pct":  stats["home_ou"]["over_pct"],
            "away_over_pct":  stats["away_ou"]["over_pct"],
            "profitable_seasons": sum(1 for s in stats["by_season"] if s["roi"] > 0),
        })

    return pd.DataFrame(rows)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--team",        type=str, default=None)
    p.add_argument("--conference",  type=str, default=None)
    p.add_argument("--min-games",   type=int, default=20)
    p.add_argument("--all-conferences", action="store_true")
    p.add_argument("--sort-by",     type=str, default="overall_roi",
                   choices=["overall_roi", "home_roi", "away_roi",
                             "home_dog_roi", "ppa_edge_roi", "overall_wp"])
    p.add_argument("--top",         type=int, default=20)
    args = p.parse_args()

    con = duckdb.connect(DB_PATH, read_only=True)
    print("Loading game data...")
    df = load_data(con)
    con.close()
    print(f"Loaded {len(df):,} games\n")

    if args.team:
        # Single team deep dive
        stats = compute_team_stats(df, args.team)
        print_team_report(stats)
        return

    # League-wide table
    print(f"Building team ATS table (min {args.min_games} games)...")
    table = build_league_table(df, args.min_games, args.conference)

    if table.empty:
        print("No teams found.")
        return

    table = table.sort_values(args.sort_by, ascending=False)

    # ── Top overall ATS ──────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  🏆 TOP {args.top} TEAMS — OVERALL ATS ROI (2021-2025)")
    print(f"{'='*65}")
    cols = ["team", "conf", "games", "overall_wp", "overall_roi",
            "profitable_seasons"]
    top = table.nlargest(args.top, "overall_roi")[cols]
    print(top.to_string(index=False))

    # ── Best home dogs ───────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  🏠🐶 TOP HOME UNDERDOG COVERS")
    print(f"{'='*65}")
    home_dogs = table[table["home_dog_roi"].notna()].nlargest(15, "home_dog_roi")
    print(home_dogs[["team","conf","home_dog_roi","overall_roi"]].to_string(index=False))

    # ── Best away dogs ───────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  ✈️🐶 TOP AWAY UNDERDOG COVERS")
    print(f"{'='*65}")
    away_dogs = table[table["away_dog_roi"].notna()].nlargest(15, "away_dog_roi")
    print(away_dogs[["team","conf","away_dog_roi","overall_roi"]].to_string(index=False))

    # ── Best PPA edge situations ─────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  📊 TOP TEAMS IN PPA EDGE SITUATIONS (>0.15 gap)")
    print(f"{'='*65}")
    ppa = table[table["ppa_edge_bets"] >= 5].nlargest(15, "ppa_edge_roi")
    print(ppa[["team","conf","ppa_edge_bets","ppa_edge_roi","overall_roi"]].to_string(index=False))

    # ── O/U leans ───────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  📈 BIGGEST OVER TEAMS (home games)")
    print(f"{'='*65}")
    overs = table.nlargest(10, "home_over_pct")[["team","conf","home_over_pct","away_over_pct"]]
    print(overs.to_string(index=False))

    print(f"\n{'='*65}")
    print(f"  📉 BIGGEST UNDER TEAMS (home games)")
    print(f"{'='*65}")
    unders = table.nsmallest(10, "home_over_pct")[["team","conf","home_over_pct","away_over_pct"]]
    print(unders.to_string(index=False))

    # ── Consistent winners ───────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  ✅ MOST CONSISTENTLY PROFITABLE (4-5 profitable seasons)")
    print(f"{'='*65}")
    consistent = table[table["profitable_seasons"] >= 4].sort_values(
        "overall_roi", ascending=False
    )[["team","conf","games","overall_roi","profitable_seasons"]]
    print(consistent.head(20).to_string(index=False))

    # ── Teams to FADE ────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  ❌ TEAMS TO FADE (worst overall ATS ROI)")
    print(f"{'='*65}")
    fades = table.nsmallest(15, "overall_roi")[["team","conf","games","overall_roi","profitable_seasons"]]
    print(fades.to_string(index=False))

    print(f"\n\nTotal teams analyzed: {len(table)}")
    print("Run with --team 'Team Name' for deep dive on any team.")
    print("Run with --conference SEC to filter by conference.")


if __name__ == "__main__":
    main()
