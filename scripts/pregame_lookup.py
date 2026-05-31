#!/usr/bin/env python3
"""
pregame_lookup.py

Given two teams and a spread, pulls all context from DuckDB and surfaces
which historical edges apply — including team-specific ATS profiles for
all 263 FBS teams (2021-2025).

Validated rules:
  PRIMARY:  Home PPA gap >0.15 + spread <=14 → +31.8% ROI, 5/5 seasons
  STRONG:   PPA gap >0.15 + SP+ agrees + spread <=17 → +28.3% ROI
  FADES:    STRONG_FADE tier teams as home favorites — avoid always

Usage:
  python scripts/pregame_lookup.py --home "Ohio State" --away "Michigan" --spread -7 --ou 45.5
"""

from __future__ import annotations

import argparse
import json
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

TIER_EMOJI = {
    "ELITE":       "🌟",
    "STRONG":      "✅",
    "NEUTRAL":     "➖",
    "FADE":        "⚠️ ",
    "STRONG_FADE": "❌",
}

SITUATION_LABELS = {
    "home_fav":  "Home favorite",
    "home_dog":  "Home underdog",
    "away_fav":  "Away favorite",
    "away_dog":  "Away underdog",
    "home_ppa":  "Home w/ PPA edge",
    "away_ppa":  "Away w/ PPA edge",
}


def sep(text: str) -> None:
    print(f"\n{'─'*60}")
    print(f"  {text}")
    print(f"{'─'*60}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--home",   required=True)
    p.add_argument("--away",   required=True)
    p.add_argument("--spread", type=float, default=None,
                   help="Negative = home favored")
    p.add_argument("--ou",     type=float, default=None)
    p.add_argument("--year",   type=int, default=2025)
    args = p.parse_args()

    home   = args.home
    away   = args.away
    spread = args.spread
    ou     = args.ou
    year   = args.year

    con = duckdb.connect(DB_PATH, read_only=True)

    # ── Header ────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  🏈 PRE-GAME EDGE REPORT")
    print(f"  {away} @ {home}")
    if spread is not None:
        fav = home if spread < 0 else away
        dog = away if spread < 0 else home
        print(f"  Spread: {fav} -{abs(spread):.1f} | {dog} +{abs(spread):.1f}")
    if ou is not None:
        print(f"  O/U: {ou}")
    print(f"{'='*60}")

    # ── SP+ Ratings ───────────────────────────────────────────────────────
    sep("📊 SP+ Ratings")
    sp = con.execute("""
        SELECT team, rating, offense, defense
        FROM cfbd.sp_ratings
        WHERE season = ? AND team IN (?, ?)
        ORDER BY rating DESC
    """, [year, home, away]).df()

    sp_gap = None
    if not sp.empty:
        for _, row in sp.iterrows():
            tag = "🏠" if row["team"] == home else "✈️ "
            print(f"  {tag} {row['team']}: {row['rating']:.1f} "
                  f"(Off: {row['offense']:.1f} / Def: {row['defense']:.1f})")
        if len(sp) == 2:
            h_sp = sp[sp["team"] == home]["rating"].values
            a_sp = sp[sp["team"] == away]["rating"].values
            if len(h_sp) and len(a_sp):
                sp_gap = float(h_sp[0]) - float(a_sp[0])
                print(f"\n  SP+ gap: {sp_gap:+.1f} "
                      f"({'home' if sp_gap > 0 else 'away'} advantage)")
    else:
        print(f"  No SP+ data for {year}")

    # ── Advanced stats ────────────────────────────────────────────────────
    sep("💪 Team Efficiency")
    adv = con.execute("""
        SELECT team,
               round(off_ppa, 3)         as off_ppa,
               round(off_success_rate, 3) as off_sr,
               round(off_rush_ppa, 3)     as rush_ppa,
               round(def_ppa, 3)          as def_ppa,
               round(def_success_rate, 3) as def_sr,
               round(def_havoc_total, 3)  as def_havoc
        FROM cfbd.advanced_stats
        WHERE season = ? AND team IN (?, ?)
    """, [year, home, away]).df()

    ppa_gap = None
    if not adv.empty:
        h_row = adv[adv["team"] == home]
        a_row = adv[adv["team"] == away]
        for _, row in adv.iterrows():
            tag = "🏠" if row["team"] == home else "✈️ "
            print(f"\n  {tag} {row['team']}")
            print(f"     Off: PPA={row['off_ppa']} | SR={row['off_sr']} | Rush={row['rush_ppa']}")
            print(f"     Def: PPA={row['def_ppa']} | SR={row['def_sr']} | Havoc={row['def_havoc']}")
        if not h_row.empty and not a_row.empty:
            ppa_gap = float(h_row["off_ppa"].values[0]) - float(a_row["off_ppa"].values[0])
            print(f"\n  PPA Gap: {ppa_gap:+.3f} ", end="")
            if ppa_gap > 0.30:   print("🔥 EXTREME home edge")
            elif ppa_gap > 0.15: print("✅ Home efficiency edge")
            elif ppa_gap < -0.15: print("✅ Away efficiency edge")
            else:                 print("(even)")
    else:
        print(f"  No advanced stats for {year}")

    # ── Returning production ──────────────────────────────────────────────
    sep("🔄 Returning Production")
    ret = con.execute("""
        SELECT team,
               round(percent_ppa * 100, 1)         as pct_ret,
               round(percent_rushing_ppa * 100, 1)  as pct_rush,
               round(percent_passing_ppa * 100, 1)  as pct_pass
        FROM cfbd.returning_production
        WHERE season = ? AND team IN (?, ?)
    """, [year, home, away]).df()

    if not ret.empty:
        for _, row in ret.iterrows():
            tag = "🏠" if row["team"] == home else "✈️ "
            print(f"  {tag} {row['team']}: {row['pct_ret']}% returning "
                  f"(Rush: {row['pct_rush']}% | Pass: {row['pct_pass']}%)")
    else:
        print(f"  No returning production data for {year}")

    # ── Coaches ───────────────────────────────────────────────────────────
    sep("🎓 Coaches")
    coaches = con.execute("""
        SELECT school, full_name, wins, losses
        FROM cfbd.coaches WHERE year = ? AND school IN (?, ?)
    """, [year, home, away]).df()

    if not coaches.empty:
        for _, row in coaches.iterrows():
            tag = "🏠" if row["school"] == home else "✈️ "
            print(f"  {tag} {row['school']}: {row['full_name']} "
                  f"({row['wins']}-{row['losses']} in {year})")

    # ── Rivalry ───────────────────────────────────────────────────────────
    sep("⚔️  Rivalry")
    rivalry = con.execute("""
        SELECT team1, team2, team1_wins, team2_wins, total_games,
               team1_last10_wins, team2_last10_wins, most_recent_winner
        FROM cfbd.matchup_history
        WHERE (team1 = ? AND team2 = ?) OR (team1 = ? AND team2 = ?)
    """, [home, away, away, home]).df()

    is_rivalry = not rivalry.empty
    if is_rivalry:
        r = rivalry.iloc[0]
        print(f"  ✅ RIVALRY — {r['team1']} {r['team1_wins']} vs "
              f"{r['team2']} {r['team2_wins']} all-time")
        print(f"     Last 10: {r['team1']} {r['team1_last10_wins']} — "
              f"{r['team2_last10_wins']} {r['team2']}")
        print(f"     ⚠️  Model rule: SKIP rivalry games (3/5 seasons profitable)")
    else:
        print("  Not a tracked rivalry")

    # ── Team profiles from DuckDB ─────────────────────────────────────────
    sep("🧠 Team ATS Profiles (2021-2025, all FBS)")

    profiles = con.execute("""
        SELECT * FROM cfbd.team_profiles
        WHERE team IN (?, ?)
    """, [home, away]).df()

    home_profile = profiles[profiles["team"] == home].iloc[0] if not profiles[profiles["team"] == home].empty else None
    away_profile = profiles[profiles["team"] == away].iloc[0] if not profiles[profiles["team"] == away].empty else None

    for team, profile, role in [(home, home_profile, "HOME"), (away, away_profile, "AWAY")]:
        if profile is None:
            print(f"\n  {role} {team}: No profile in DB (< 15 games)")
            continue

        tier    = profile["tier"]
        emoji   = TIER_EMOJI.get(tier, "")
        seasons = profile["profitable_seasons"]
        total_r = profile["total_roi"]

        print(f"\n  {emoji} {role} — {team} [{tier}]")
        print(f"     Overall: {profile['total_win_pct']}% cover | "
              f"{total_r:+.1f}% ROI | Profitable {seasons}/5 seasons")
        print(f"     Home: {profile['home_roi']:+.1f}% ROI | "
              f"Away: {profile['away_roi']:+.1f}% ROI")

        # Situational splits
        sits = [
            ("home_fav", profile["home_fav_roi"], profile["home_fav_bets"]),
            ("home_dog", profile["home_dog_roi"], profile["home_dog_bets"]),
            ("away_fav", profile["away_fav_roi"], profile["away_fav_bets"]),
            ("away_dog", profile["away_dog_roi"], profile["away_dog_bets"]),
        ]
        print(f"     Situations:")
        for sit, roi, bets in sits:
            if roi is not None and bets >= 5:
                flag = " ✅" if roi > 20 else " ⛔" if roi < -20 else ""
                print(f"       {SITUATION_LABELS[sit]:22s}: {roi:+.1f}% ROI "
                      f"({int(bets)}g){flag}")

        # PPA edge
        if profile["home_ppa_bets"] >= 5:
            print(f"     PPA edge (home): {profile['home_ppa_roi']:+.1f}% ROI "
                  f"({int(profile['home_ppa_bets'])}g)")
        if profile["away_ppa_bets"] >= 5:
            print(f"     PPA edge (away): {profile['away_ppa_roi']:+.1f}% ROI "
                  f"({int(profile['away_ppa_bets'])}g)")

        # O/U
        if profile["home_over_pct"]:
            ou_note = ""
            if profile["home_over_pct"] >= 65:   ou_note = " 📈 STRONG OVER lean"
            elif profile["home_over_pct"] <= 35:  ou_note = " 📉 STRONG UNDER lean"
            print(f"     O/U: {profile['home_over_pct']}% home overs | "
                  f"{profile['away_over_pct']}% away overs{ou_note}")

        # Season trend
        try:
            season_data = json.loads(profile["season_rois_json"])
            trend = " ".join(
                f"{s['season']}:{s['roi']:+.0f}%" for s in season_data
                if s["roi"] is not None
            )
            print(f"     Trend: {trend}")
        except Exception:
            pass

    # ── Edge signals ──────────────────────────────────────────────────────
    sep("🎯 Active Edge Signals")

    edges    = []
    warnings = []

    # PPA gap
    if ppa_gap is not None:
        if ppa_gap > 0.30:
            edges.append(("🔥 PPA gap >0.30", "EXTREME signal — +41.9% ROI historically"))
        elif ppa_gap > 0.15:
            edges.append(("📊 PPA gap >0.15", "Primary signal — +19.0% ROI, 5/5 seasons"))
        elif ppa_gap < -0.15:
            edges.append(("📊 PPA gap >0.15 (away)", "Away team efficiency edge"))

    # Spread + PPA combo
    if spread is not None and ppa_gap is not None and abs(ppa_gap) > 0.15:
        spread_abs = abs(spread)
        favored_team = home if ppa_gap > 0 else away
        if spread_abs <= 14:
            edges.append(("✅ PPA + spread ≤14", f"BEST COMBO — +31.8% ROI, 69% win rate → {favored_team}"))
        elif spread_abs <= 17:
            edges.append(("✅ PPA + spread ≤17", f"+28.3% ROI → {favored_team}"))
        else:
            warnings.append("⚠️  Spread >17 with PPA edge — blowout risk, skip")

    # SP+ alignment
    if sp_gap is not None and ppa_gap is not None and abs(ppa_gap) > 0.15:
        agrees = (sp_gap > 0 and ppa_gap > 0) or (sp_gap < 0 and ppa_gap < 0)
        if agrees:
            edges.append(("📈 SP+ confirms PPA", "Both metrics aligned — added confidence"))
        else:
            warnings.append("⚠️  SP+ disagrees with PPA signal — mixed picture")

    # Team-specific
    for team, profile, role, is_home in [
        (home, home_profile, "HOME", True),
        (away, away_profile, "AWAY", False),
    ]:
        if profile is None:
            continue
        tier = profile["tier"]

        if tier == "STRONG_FADE":
            # Determine their role in this game
            if is_home:
                if spread and spread < 0:  # home is favored
                    roi = profile["home_fav_roi"]
                    warnings.append(f"⛔ {team} home favorite: {roi:+.1f}% ROI — STRONG FADE")
                else:
                    roi = profile["home_dog_roi"]
                    warnings.append(f"⛔ {team} home dog: {roi:+.1f}% ROI — still a fade")
            else:
                if spread and spread < 0:  # away is dog
                    roi = profile["away_dog_roi"]
                    if roi and roi < -15:
                        warnings.append(f"⛔ {team} away underdog: {roi:+.1f}% ROI — fade")
                else:
                    roi = profile["away_fav_roi"]
                    if roi and roi < -15:
                        warnings.append(f"⛔ {team} away favorite: {roi:+.1f}% ROI — fade")

        elif tier in ("ELITE", "STRONG"):
            if is_home:
                sit = "home_dog" if (spread and spread > 0) else "home_fav"
                roi = profile[f"{sit}_roi"]
                bets = profile[f"{sit}_bets"]
                if roi and roi > 20 and bets >= 5:
                    edges.append((f"🌟 {team} {SITUATION_LABELS[sit]}",
                                  f"{roi:+.1f}% ROI over {int(bets)} games"))
            else:
                sit = "away_dog" if (spread and spread < 0) else "away_fav"
                roi = profile[f"{sit}_roi"]
                bets = profile[f"{sit}_bets"]
                if roi and roi > 20 and bets >= 5:
                    edges.append((f"🌟 {team} {SITUATION_LABELS[sit]}",
                                  f"{roi:+.1f}% ROI over {int(bets)} games"))

    # Rivalry
    if is_rivalry:
        warnings.append("⚔️  Rivalry — skip per model (3/5 seasons only)")

    if edges:
        print("\n  ACTIVE EDGES:")
        for label, detail in edges:
            print(f"    {label}")
            print(f"      → {detail}")

    if warnings:
        print("\n  WARNINGS:")
        for w in warnings:
            print(f"    {w}")

    if not edges and not warnings:
        print("  No strong signals — line appears fairly priced")

    # ── Bottom line ───────────────────────────────────────────────────────
    sep("📋 Bottom Line")

    strong_fades  = [w for w in warnings if "STRONG FADE" in w or "⛔" in w]
    strong_edges  = [e for e in edges if any(x in e[0] for x in ["🔥","✅","🌟"])]
    rivalry_skip  = is_rivalry

    if rivalry_skip:
        print(f"  ⏭  SKIP — Rivalry game, model says pass")
    elif strong_fades and not strong_edges:
        team_to_fade = home if home_profile is not None and home_profile["tier"] == "STRONG_FADE" else away
        print(f"  ⛔ FADE {team_to_fade} — historical fade, bet the other side")
    elif len(strong_edges) >= 3:
        direction = home if (ppa_gap and ppa_gap > 0) else away
        print(f"  🔥 STRONG BET — {direction} covers ({len(strong_edges)} edges stacked)")
    elif len(strong_edges) == 2:
        direction = home if (ppa_gap and ppa_gap > 0) else away
        print(f"  ✅ BET — {direction} covers ({len(strong_edges)} edges)")
    elif len(strong_edges) == 1:
        print(f"  💡 LEAN — {strong_edges[0][0]}: {strong_edges[0][1]}")
    elif warnings:
        print(f"  ⚠️  CAUTION — {warnings[0]}")
    else:
        print(f"  ➖ PASS — No edge, line is fair")

    print()
    con.close()


if __name__ == "__main__":
    main()
