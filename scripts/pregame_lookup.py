#!/usr/bin/env python3
"""
pregame_lookup.py

Given two teams and a spread, pull all relevant context factors and
surface which historical edges apply — including team-specific ATS tendencies.

Validated rules (2021-2025, cross-season):
  PRIMARY:  Home PPA gap >0.15 + spread <=14 → +31.8% ROI, 5/5 seasons
  STRONG:   Home PPA gap >0.15 + SP+ agrees + spread <=17 → +28.3% ROI
  TEAMS:    Notre Dame away dog (+75% ROI), Wazzu home dog (+33.6%)
            Ohio State home + PPA edge (+22.7%), Kentucky home/away covers
  FADES:    North Carolina home favorite (-39.5%), Stanford home fav (-76.1%)
            Purdue home (-47.9%), Florida home (-24.1%)

Usage:
  python scripts/pregame_lookup.py --home "Ohio State" --away "Michigan" --spread -7 --ou 45.5
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

# ─────────────────────────────────────────────────────────────────────────────
# Team intelligence — validated across 2021-2025
# ─────────────────────────────────────────────────────────────────────────────

TEAM_INTEL = {
    # ── STRONG BET teams ──────────────────────────────────────────────────
    "Notre Dame": {
        "tier": "ELITE",
        "overall_roi": 29.91,
        "profitable_seasons": "4/5",
        "edges": [
            ("away_dog", 75.0, "Away underdog: 91.7% cover, +75% ROI — AUTO BET"),
            ("away_any",  43.2, "Road games generally: +43.2% ROI"),
            ("home_fav",  33.2, "Home favorite: +33.2% ROI"),
        ],
        "ou_note": "Away games 69.4% overs — lean OVER on road",
        "fade_situation": "home_dog",  # -58.4% ROI
    },
    "Washington State": {
        "tier": "ELITE",
        "overall_roi": 14.17,
        "profitable_seasons": "5/5 — only team profitable every season",
        "edges": [
            ("home_dog", 33.6, "Home underdog: 70% cover, +33.6% ROI"),
            ("home_any", 22.5, "Home games generally: +22.5% ROI"),
            ("away_dog", 14.5, "Away underdog: +14.5% ROI"),
        ],
        "ou_note": "Consistent UNDER lean — 45% home overs, 47% away",
        "fade_situation": "away_fav",  # -9.6% ROI
    },
    "Ohio State": {
        "tier": "ELITE",
        "overall_roi": 15.11,
        "profitable_seasons": "4/5 — trending UP (2025: +43.5%)",
        "edges": [
            ("home_ppa", 22.7, "Home + PPA edge >0.15: 64.3% cover, +22.7% ROI (28 games)"),
            ("home_fav", 20.6, "Home favorite: +20.6% ROI — never a home dog"),
        ],
        "ou_note": "Under lean — 47.8% home overs",
        "fade_situation": None,
    },
    "Kentucky": {
        "tier": "STRONG",
        "overall_roi": 14.88,
        "profitable_seasons": "4/5 — 2025 was weak (-20.4%), monitor",
        "edges": [
            ("home_dog", 19.3, "Home underdog: 62.5% cover, +19.3% ROI"),
            ("home_fav", 15.4, "Home favorite: +15.4% ROI"),
            ("away_fav", 27.3, "Away favorite: +27.3% ROI (rare)"),
        ],
        "ou_note": "Strong UNDER lean — 46.7% home, 39.1% away overs",
        "fade_situation": None,
    },
    "Alabama": {
        "tier": "STRONG",
        "overall_roi": 11.69,
        "profitable_seasons": "4/5",
        "edges": [
            ("home_ppa", 52.7, "PPA edge situations: +52.7% ROI"),
        ],
        "ou_note": "Neutral",
        "fade_situation": None,
    },
    "Boise State": {
        "tier": "STRONG",
        "overall_roi": 10.97,
        "profitable_seasons": "4/5",
        "edges": [
            ("home_any", 10.97, "Consistent ATS performer — 4/5 profitable seasons"),
        ],
        "ou_note": "Neutral",
        "fade_situation": None,
    },
    "Penn State": {
        "tier": "STRONG",
        "overall_roi": 11.36,
        "profitable_seasons": "4/5",
        "edges": [
            ("overall", 11.36, "Consistent Big Ten cover — 4/5 profitable seasons"),
        ],
        "ou_note": "Neutral",
        "fade_situation": None,
    },
    "Illinois": {
        "tier": "STRONG",
        "overall_roi": 11.09,
        "profitable_seasons": "4/5",
        "edges": [
            ("overall", 11.09, "Consistent ATS performer in Big Ten"),
        ],
        "ou_note": "Neutral",
        "fade_situation": None,
    },
    "East Carolina": {
        "tier": "STRONG",
        "overall_roi": 15.08,
        "profitable_seasons": "4/5",
        "edges": [
            ("overall", 15.08, "Best ATS record in AAC — 4/5 profitable seasons"),
        ],
        "ou_note": "Neutral",
        "fade_situation": None,
    },
    "UNLV": {
        "tier": "STRONG",
        "overall_roi": 12.75,
        "profitable_seasons": "4/5",
        "edges": [
            ("ppa", 63.6, "PPA edge situations: 63.6% ROI over 14 games"),
        ],
        "ou_note": "Neutral",
        "fade_situation": None,
    },
    "South Carolina": {
        "tier": "STRONG",
        "overall_roi": 10.96,
        "profitable_seasons": "4/5",
        "edges": [
            ("overall", 10.96, "Consistently underrated in SEC"),
        ],
        "ou_note": "Neutral",
        "fade_situation": None,
    },
    "James Madison": {
        "tier": "STRONG",
        "overall_roi": 20.30,
        "profitable_seasons": "4/5",
        "edges": [
            ("overall", 20.30, "New FBS program — market still undervaluing"),
        ],
        "ou_note": "Neutral",
        "fade_situation": None,
    },

    # ── FADE teams ────────────────────────────────────────────────────────
    "North Carolina": {
        "tier": "FADE",
        "overall_roi": -35.84,
        "profitable_seasons": "0/5",
        "edges": [],
        "fade_rules": [
            ("home_fav", -39.5, "Home favorite: -39.5% ROI — NEVER BET"),
            ("home_dog", -51.8, "Home underdog: -51.8% ROI — NEVER BET"),
            ("away_fav", -46.5, "Away favorite: -46.5% ROI — NEVER BET"),
        ],
        "ou_note": "No strong lean",
        "fade_situation": "always",
    },
    "Stanford": {
        "tier": "FADE",
        "overall_roi": -35.82,
        "profitable_seasons": "0/5",
        "edges": [],
        "fade_rules": [
            ("home_fav", -76.1, "Home favorite: 12.5% cover rate, -76.1% ROI — WORST IN DATASET"),
            ("away_dog", -49.1, "Away underdog: -49.1% ROI"),
        ],
        "ou_note": "No strong lean",
        "fade_situation": "home_fav",
    },
    "Purdue": {
        "tier": "FADE",
        "overall_roi": -32.24,
        "profitable_seasons": "1/5",
        "edges": [],
        "fade_rules": [
            ("home_fav", -44.3, "Home favorite: -44.3% ROI"),
            ("home_dog", -52.3, "Home underdog: -52.3% ROI — NEVER BET AT HOME"),
        ],
        "ou_note": "54.5% home overs — slight over lean",
        "fade_situation": "home_any",
    },
    "Florida": {
        "tier": "FADE",
        "overall_roi": -24.13,
        "profitable_seasons": "1/5",
        "edges": [],
        "fade_rules": [
            ("overall", -24.13, "0/5 profitable seasons — chronically overvalued"),
        ],
        "ou_note": "No strong lean",
        "fade_situation": "home_fav",
    },
    "Cincinnati": {
        "tier": "FADE",
        "overall_roi": -26.72,
        "profitable_seasons": "1/5",
        "edges": [],
        "fade_rules": [
            ("overall", -26.72, "Worst P4 ATS record — overvalued post-AAC"),
        ],
        "ou_note": "No strong lean",
        "fade_situation": "home_fav",
    },
}

# USC over lean
USC_OVER_NOTE = "USC home games: 75% over rate — strong OVER lean at home"
RUTGERS_OVER_NOTE = "Rutgers home games: 72.2% over rate"
MISS_STATE_OVER_NOTE = "Mississippi State home: 73.6% over rate"


def cfbd_get(endpoint: str, params: dict = None) -> list | dict:
    headers = {"Authorization": f"Bearer {CFBD_TOKEN}"}
    r = requests.get(f"{API_BASE}{endpoint}", headers=headers,
                     params=params or {}, timeout=15)
    r.raise_for_status()
    return r.json()


def print_header(text: str) -> None:
    print(f"\n{'─'*60}")
    print(f"  {text}")
    print(f"{'─'*60}")


def get_team_intel(team: str) -> dict | None:
    return TEAM_INTEL.get(team)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--home",   required=True)
    p.add_argument("--away",   required=True)
    p.add_argument("--spread", type=float, default=None)
    p.add_argument("--ou",     type=float, default=None)
    p.add_argument("--year",   type=int, default=2025)
    args = p.parse_args()

    home   = args.home
    away   = args.away
    spread = args.spread
    ou     = args.ou
    year   = args.year

    con = duckdb.connect(DB_PATH, read_only=True)

    print(f"\n{'='*60}")
    print(f"  🏈 PRE-GAME EDGE REPORT")
    print(f"  {away} @ {home}")
    if spread is not None:
        fav     = home if spread < 0 else away
        dog     = away if spread < 0 else home
        print(f"  Spread: {fav} -{abs(spread):.1f} | {dog} +{abs(spread):.1f}")
    if ou is not None:
        print(f"  O/U: {ou}")
    print(f"{'='*60}")

    # ── SP+ Ratings ──────────────────────────────────────────────────────
    print_header("📊 SP+ Ratings")
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
            home_sp = sp[sp["team"] == home]["rating"].values
            away_sp = sp[sp["team"] == away]["rating"].values
            if len(home_sp) and len(away_sp):
                sp_gap = home_sp[0] - away_sp[0]
                print(f"\n  SP+ gap: {sp_gap:+.1f} ({'home' if sp_gap > 0 else 'away'} advantage)")
    else:
        print(f"  No SP+ data for {year}")

    # ── Advanced stats ───────────────────────────────────────────────────
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
    """, [year, home, away]).df()

    ppa_gap = None
    if not adv.empty:
        home_row = adv[adv["team"] == home]
        away_row = adv[adv["team"] == away]
        for _, row in adv.iterrows():
            tag = "🏠" if row["team"] == home else "✈️ "
            print(f"\n  {tag} {row['team']}")
            print(f"     Offense: PPA={row['off_ppa']} | SR={row['off_sr']} | Rush PPA={row['rush_ppa']}")
            print(f"     Defense: PPA={row['def_ppa']} | SR={row['def_sr']} | Havoc={row['def_havoc']}")
        if not home_row.empty and not away_row.empty:
            ppa_gap = float(home_row["off_ppa"].values[0]) - float(away_row["off_ppa"].values[0])
            print(f"\n  PPA Gap (home off - away off): {ppa_gap:+.3f}")
            if ppa_gap > 0.15:
                print(f"  ✅ PPA EDGE: Home team has significant offensive efficiency advantage")
            elif ppa_gap < -0.15:
                print(f"  ⚠️  PPA EDGE: Away team has significant offensive efficiency advantage")
    else:
        print(f"  No advanced stats for {year}")

    # ── Returning production ─────────────────────────────────────────────
    print_header("🔄 Returning Production")
    ret = con.execute("""
        SELECT team,
               round(percent_ppa * 100, 1) as pct_returning,
               round(percent_rushing_ppa * 100, 1) as pct_rush_returning,
               round(percent_passing_ppa * 100, 1) as pct_pass_returning
        FROM cfbd.returning_production
        WHERE season = ? AND team IN (?, ?)
    """, [year, home, away]).df()

    if not ret.empty:
        for _, row in ret.iterrows():
            tag = "🏠" if row["team"] == home else "✈️ "
            print(f"  {tag} {row['team']}: {row['pct_returning']}% returning "
                  f"(Rush: {row['pct_rush_returning']}% | Pass: {row['pct_pass_returning']}%)")
    else:
        print(f"  No returning production data for {year}")

    # ── Coaches ──────────────────────────────────────────────────────────
    print_header("🎓 Head Coaches")
    coaches = con.execute("""
        SELECT school, full_name, wins, losses
        FROM cfbd.coaches
        WHERE year = ? AND school IN (?, ?)
    """, [year, home, away]).df()

    if not coaches.empty:
        for _, row in coaches.iterrows():
            tag = "🏠" if row["school"] == home else "✈️ "
            print(f"  {tag} {row['school']}: {row['full_name']} "
                  f"({row['wins']}-{row['losses']} in {year})")

    # ── Rivalry check ────────────────────────────────────────────────────
    print_header("⚔️  Rivalry Check")
    rivalry = con.execute("""
        SELECT team1, team2, team1_wins, team2_wins, total_games,
               team1_last10_wins, team2_last10_wins, most_recent_winner
        FROM cfbd.matchup_history
        WHERE (team1 = ? AND team2 = ?) OR (team1 = ? AND team2 = ?)
    """, [home, away, away, home]).df()

    is_rivalry = not rivalry.empty
    if is_rivalry:
        row = rivalry.iloc[0]
        t1, t2 = row["team1"], row["team2"]
        print(f"  ✅ RIVALRY GAME")
        print(f"     All-time: {t1} {row['team1_wins']} — {row['team2_wins']} {t2}")
        print(f"     Last 10:  {t1} {row['team1_last10_wins']} — {row['team2_last10_wins']} {t2}")
        print(f"     ⚠️  RIVALRY NOTE: Skip this game per model rules (3/5 seasons profitable)")
    else:
        print("  Not a tracked rivalry")

    # ── Team intelligence ────────────────────────────────────────────────
    print_header("🧠 Team-Specific ATS History (2021-2025)")

    home_intel = get_team_intel(home)
    away_intel = get_team_intel(away)

    for team, intel, role in [(home, home_intel, "HOME"), (away, away_intel, "AWAY")]:
        if not intel:
            print(f"  {role} {team}: No specific ATS history flagged")
            continue

        tier_emoji = {"ELITE": "🌟", "STRONG": "✅", "FADE": "❌"}.get(intel["tier"], "")
        print(f"\n  {tier_emoji} {role} — {team} [{intel['tier']}]")
        print(f"     Overall ROI: {intel['overall_roi']:+.1f}% | "
              f"Profitable: {intel['profitable_seasons']}")

        if intel["tier"] == "FADE":
            for sit, roi, note in intel.get("fade_rules", []):
                print(f"     ⛔ {note}")
        else:
            for sit, roi, note in intel.get("edges", []):
                print(f"     💰 {note}")

        if intel.get("ou_note"):
            print(f"     📊 O/U: {intel['ou_note']}")

    # ── Edge summary ─────────────────────────────────────────────────────
    print_header("🎯 Applicable Edge Signals")

    edges    = []
    warnings = []

    # PPA gap signal
    if ppa_gap is not None:
        if ppa_gap > 0.30:
            edges.append(("🔥 PPA gap >0.30", f"STRONGEST signal — +41.9% ROI historically. Bet HOME covers."))
        elif ppa_gap > 0.15:
            edges.append(("📊 PPA gap >0.15", f"Primary signal — +19.0% ROI, profitable 5/5 seasons. Lean HOME covers."))
        elif ppa_gap < -0.15:
            edges.append(("📊 PPA gap <-0.15", f"Away team efficiency edge — lean AWAY covers."))

    # Spread filter
    if spread is not None and ppa_gap is not None and ppa_gap > 0.15:
        spread_abs = abs(spread)
        if spread_abs <= 14:
            edges.append(("✅ Spread ≤14 + PPA edge", "BEST COMBO — +31.8% ROI, 69% win rate"))
        elif spread_abs <= 17:
            edges.append(("✅ Spread ≤17 + PPA edge", "Strong combo — +28.3% ROI"))
        else:
            warnings.append("⚠️  Spread >17 with PPA edge — avoid (blowout risk)")

    # SP+ alignment
    if sp_gap is not None and ppa_gap is not None:
        sp_agrees = (sp_gap > 0 and ppa_gap > 0) or (sp_gap < 0 and ppa_gap < 0)
        if sp_agrees and ppa_gap > 0.15:
            edges.append(("📈 SP+ agrees with PPA signal", "Confirmation — both metrics aligned"))
        elif not sp_agrees and abs(ppa_gap) > 0.15:
            warnings.append("⚠️  SP+ disagrees with PPA signal — proceed with caution")

    # Team-specific edges
    if home_intel:
        if home_intel["tier"] == "FADE":
            warnings.append(f"⛔ {home} is a historical FADE ({home_intel['overall_roi']:+.1f}% ROI)")
        elif home_intel["tier"] in ("ELITE", "STRONG"):
            # Check if this is a favorable situation for this team
            if spread is not None:
                home_is_dog = spread > 0
                if home_is_dog and any(s[0] == "home_dog" for s in home_intel["edges"]):
                    edges.append((f"🌟 {home} home underdog", "Team-specific edge activated"))
                elif not home_is_dog and any(s[0] == "home_fav" for s in home_intel["edges"]):
                    edges.append((f"🌟 {home} home favorite", "Team-specific edge activated"))

    if away_intel:
        if away_intel["tier"] == "FADE":
            edges.append((f"⛔ Fade {away}", f"Historical fade — {away_intel['overall_roi']:+.1f}% ROI as away team"))
        elif away_intel["tier"] in ("ELITE", "STRONG") and spread is not None:
            away_is_dog = spread < 0  # home is favored
            if away_is_dog and any(s[0] == "away_dog" for s in away_intel["edges"]):
                edges.append((f"🌟 {away} away underdog", "Team-specific edge — strong cover history"))

    # Rivalry warning
    if is_rivalry:
        warnings.append("⚔️  Rivalry game — model says SKIP (inconsistent edge, 3/5 seasons)")

    if edges:
        print(f"\n  ✅ ACTIVE EDGES:")
        for label, detail in edges:
            print(f"     {label}")
            print(f"       → {detail}")
    else:
        print("  No strong edges identified.")

    if warnings:
        print(f"\n  ⚠️  WARNINGS:")
        for w in warnings:
            print(f"     {w}")

    # ── Bottom line ───────────────────────────────────────────────────────
    print_header("📋 Bottom Line")

    strong_edges = [e for e in edges if "🔥" in e[0] or "✅" in e[0] or "🌟" in e[0]]
    fade_signals = [e for e in edges if "⛔" in e[0]]

    if home_intel and home_intel["tier"] == "FADE" and spread and spread < 0:
        print(f"  ❌ DO NOT BET — {home} as home favorite is historically catastrophic")
    elif len(strong_edges) >= 2:
        if ppa_gap and ppa_gap > 0:
            print(f"  🔥 STRONG BET — {home} covers ({len(strong_edges)} edges stacked)")
        else:
            print(f"  🔥 STRONG BET — {away} covers ({len(strong_edges)} edges stacked)")
    elif len(strong_edges) == 1:
        print(f"  ✅ LEAN — {strong_edges[0][0]}: {strong_edges[0][1]}")
    elif fade_signals:
        print(f"  ⛔ FADE — {fade_signals[0][1]}")
    else:
        print("  ➖ PASS — No strong edge, line appears fairly priced")

    print()
    con.close()


if __name__ == "__main__":
    main()
