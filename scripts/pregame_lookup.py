#!/usr/bin/env python3
"""
pregame_lookup.py

Given two teams and a spread, pull all relevant context factors and
surface which historical edges apply to this matchup.

Usage:
  python scripts/pregame_lookup.py --home "Ohio State" --away "Michigan" --spread -7 --ou 48.5
  python scripts/pregame_lookup.py --home "Alabama" --away "Auburn" --spread -14 --ou 52
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import duckdb
import requests
from dotenv import load_dotenv

ROOT    = Path(__file__).resolve().parents[1]
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")
load_dotenv(ROOT / ".env")

API_BASE   = "https://api.collegefootballdata.com"
CFBD_TOKEN = os.getenv("CFBD_API_TOKEN", "")


def cfbd_get(endpoint: str, params: dict = None) -> list | dict:
    headers = {"Authorization": f"Bearer {CFBD_TOKEN}"}
    r = requests.get(f"{API_BASE}{endpoint}", headers=headers,
                     params=params or {}, timeout=15)
    r.raise_for_status()
    return r.json()


def get_current_lines(home: str, away: str) -> list[dict]:
    """Fetch current betting lines for this matchup."""
    try:
        data = cfbd_get("/lines", {"team": home, "year": 2025})
        return [g for g in data if
                g.get("homeTeam") == home and g.get("awayTeam") == away
                or g.get("homeTeam") == away and g.get("awayTeam") == home]
    except Exception:
        return []


def print_header(text: str) -> None:
    print(f"\n{'─'*55}")
    print(f"  {text}")
    print(f"{'─'*55}")


def main() -> None:
    p = argparse.ArgumentParser(description="Pre-game betting edge lookup.")
    p.add_argument("--home",   required=True, help="Home team name")
    p.add_argument("--away",   required=True, help="Away team name")
    p.add_argument("--spread", type=float, default=None,
                   help="Current spread (negative = home favored)")
    p.add_argument("--ou",     type=float, default=None,
                   help="Current over/under")
    p.add_argument("--year",   type=int, default=2025)
    args = p.parse_args()

    home  = args.home
    away  = args.away
    spread = args.spread
    ou    = args.ou

    con = duckdb.connect(DB_PATH, read_only=True)

    print(f"\n{'='*55}")
    print(f"  🏈 PRE-GAME EDGE REPORT")
    print(f"  {away} @ {home}")
    if spread is not None:
        fav = home if spread < 0 else away
        line_str = f"{fav} -{abs(spread):.1f}"
        print(f"  Spread: {line_str}")
    if ou is not None:
        print(f"  O/U: {ou}")
    print(f"{'='*55}")

    # ------------------------------------------------------------------
    # SP+ ratings
    # ------------------------------------------------------------------
    print_header("📊 SP+ Ratings")
    sp = con.execute("""
        SELECT team, rating, offense, defense
        FROM cfbd.sp_ratings
        WHERE season = ? AND team IN (?, ?)
        ORDER BY rating DESC
    """, [args.year, home, away]).df()

    if not sp.empty:
        for _, row in sp.iterrows():
            tag = "🏠" if row["team"] == home else "✈️ "
            print(f"  {tag} {row['team']}: {row['rating']:.1f} "
                  f"(Off: {row['offense']:.1f} / Def: {row['defense']:.1f})")
        if len(sp) == 2:
            home_sp = sp[sp["team"] == home]["rating"].values
            away_sp = sp[sp["team"] == away]["rating"].values
            if len(home_sp) and len(away_sp):
                gap = home_sp[0] - away_sp[0]
                print(f"\n  SP+ gap: {gap:+.1f} ({'home' if gap > 0 else 'away'} advantage)")
    else:
        print(f"  No SP+ data for {args.year}")

    # ------------------------------------------------------------------
    # Advanced stats — defense & rushing strength
    # ------------------------------------------------------------------
    print_header("💪 Team Efficiency")
    adv = con.execute("""
        SELECT team,
               round(off_ppa, 3) as off_ppa,
               round(off_success_rate, 3) as off_sr,
               round(off_rush_ppa, 3) as rush_ppa,
               round(def_ppa, 3) as def_ppa,
               round(def_success_rate, 3) as def_sr,
               round(def_havoc_total, 3) as def_havoc
        FROM cfbd.advanced_stats
        WHERE season = ? AND team IN (?, ?)
    """, [args.year, home, away]).df()

    if not adv.empty:
        for _, row in adv.iterrows():
            tag = "🏠" if row["team"] == home else "✈️ "
            print(f"\n  {tag} {row['team']}")
            print(f"     Offense: PPA={row['off_ppa']} | SR={row['off_sr']} | Rush PPA={row['rush_ppa']}")
            print(f"     Defense: PPA={row['def_ppa']} | SR={row['def_sr']} | Havoc={row['def_havoc']}")
    else:
        print(f"  No advanced stats for {args.year}")

    # ------------------------------------------------------------------
    # Returning production
    # ------------------------------------------------------------------
    print_header("🔄 Returning Production (NIL/Portal effect)")
    ret = con.execute("""
        SELECT team,
               round(percent_ppa * 100, 1) as pct_returning,
               round(percent_rushing_ppa * 100, 1) as pct_rush_returning,
               round(percent_passing_ppa * 100, 1) as pct_pass_returning
        FROM cfbd.returning_production
        WHERE season = ? AND team IN (?, ?)
    """, [args.year, home, away]).df()

    if not ret.empty:
        for _, row in ret.iterrows():
            tag = "🏠" if row["team"] == home else "✈️ "
            print(f"  {tag} {row['team']}: {row['pct_returning']}% returning "
                  f"(Rush: {row['pct_rush_returning']}% | Pass: {row['pct_pass_returning']}%)")
    else:
        print(f"  No returning production data for {args.year}")

    # ------------------------------------------------------------------
    # Coaches
    # ------------------------------------------------------------------
    print_header("🎓 Head Coaches")
    coaches = con.execute("""
        SELECT school, full_name, wins, losses
        FROM cfbd.coaches
        WHERE year = ? AND school IN (?, ?)
    """, [args.year, home, away]).df()

    if not coaches.empty:
        for _, row in coaches.iterrows():
            tag = "🏠" if row["school"] == home else "✈️ "
            print(f"  {tag} {row['school']}: {row['full_name']} "
                  f"({row['wins']}-{row['losses']} in {args.year})")
    else:
        print(f"  No coach data for {args.year}")

    # ------------------------------------------------------------------
    # Rivalry check
    # ------------------------------------------------------------------
    print_header("⚔️  Rivalry Check")
    rivalry = con.execute("""
        SELECT team1, team2, team1_wins, team2_wins, total_games,
               team1_last10_wins, team2_last10_wins, most_recent_winner
        FROM cfbd.matchup_history
        WHERE (team1 = ? AND team2 = ?) OR (team1 = ? AND team2 = ?)
    """, [home, away, away, home]).df()

    if not rivalry.empty:
        row = rivalry.iloc[0]
        t1, t2 = row["team1"], row["team2"]
        print(f"  ✅ RIVALRY GAME — historical record:")
        print(f"     All-time: {t1} {row['team1_wins']} — {row['team2_wins']} {t2} "
              f"({row['total_games']} games)")
        print(f"     Last 10:  {t1} {row['team1_last10_wins']} — "
              f"{row['team2_last10_wins']} {t2}")
        print(f"     Last winner: {row['most_recent_winner']}")
        print(f"\n  ⚠️  RIVALRY EDGE: Underdogs cover at 63.7% in rivalry games")
        if spread is not None:
            dog = away if spread < 0 else home
            print(f"  → Lean: {dog} ({'+' if spread < 0 else '-'}{abs(spread):.1f}) to cover")
    else:
        print("  Not a tracked rivalry")

    # ------------------------------------------------------------------
    # Recruiting talent gap
    # ------------------------------------------------------------------
    print_header("⭐ Recruiting Talent")
    rec = con.execute("""
        SELECT team, rank, round(points, 1) as points
        FROM cfbd.recruiting_rankings
        WHERE year = ? AND team IN (?, ?)
        ORDER BY rank
    """, [args.year, home, away]).df()

    if not rec.empty:
        for _, row in rec.iterrows():
            tag = "🏠" if row["team"] == home else "✈️ "
            print(f"  {tag} {row['team']}: Rank #{int(row['rank'])} "
                  f"({row['points']} pts)")
    else:
        print(f"  No recruiting data for {args.year}")

    # ------------------------------------------------------------------
    # Historical edges summary
    # ------------------------------------------------------------------
    print_header("🎯 Applicable Historical Edges")

    edges = []

    # Rivalry
    if not rivalry.empty:
        edges.append(("⚔️  Rivalry game", "Underdogs cover 63.7% — fade the favorite"))

    # Check spread size
    if spread is not None:
        spread_abs = abs(spread)
        if spread_abs >= 7 and spread_abs <= 9.5:
            edges.append(("📐 TD-range spread (7-9.5)", "53.2% ATS cover rate — slight lean to favorite"))
        if spread_abs >= 14:
            edges.append(("📐 Big spread (14+)", "Large favorites underperform vs spread"))

    # Weather (if available for this game)
    weather = con.execute("""
        SELECT temperature, wind_speed, precipitation, game_indoors
        FROM cfbd.weather w
        JOIN cfbd.games g ON w.game_id = g.game_id
        WHERE g.season = ? AND (g.home_team = ? OR g.away_team = ?)
        ORDER BY g.week DESC LIMIT 1
    """, [args.year, home, home]).df()

    if not weather.empty:
        w = weather.iloc[0]
        if w["temperature"] and float(w["temperature"]) < 32:
            edges.append(("🌡️  Freezing game (<32°F)", "62.7% ATS home cover, 43.5% over — bet home + UNDER"))
        elif w["temperature"] and float(w["temperature"]) < 45:
            edges.append(("🌡️  Cold game (32-44°F)", "55.3% ATS cover, slight lean to under"))
        if w["wind_speed"] and float(w["wind_speed"]) >= 20:
            edges.append(("💨 High wind (20+ mph)", "42.7% over — strong UNDER lean"))

    if edges:
        for label, detail in edges:
            print(f"\n  {label}")
            print(f"     → {detail}")
    else:
        print("  No strong historical edges identified for this matchup")

    # ------------------------------------------------------------------
    # Bottom line
    # ------------------------------------------------------------------
    print_header("📋 Summary")
    if not rivalry.empty and spread is not None:
        dog = away if spread < 0 else home
        print(f"  STRONGEST SIGNAL: Rivalry game — lean {dog} ATS")
    if not edges:
        print("  No strong edges — line appears fairly priced")

    print()
    con.close()


if __name__ == "__main__":
    main()
