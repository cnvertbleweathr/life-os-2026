#!/usr/bin/env python3
"""
generate_picks_report.py

Generates a human-readable weekly CFB picks report from todays_picks.json.
Saves to data/bets/picks_report_YYYY_WkN.md

Run every Thursday during CFB season after generate_picks.py.

Usage:
  python scripts/generate_picks_report.py
  python scripts/generate_picks_report.py --week 1 --year 2025
  python scripts/generate_picks_report.py --stdout  # print only, no file
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT       = Path(__file__).resolve().parents[1]
PICKS_PATH = ROOT / "data" / "bets" / "todays_picks.json"
REPORT_DIR = ROOT / "data" / "bets"

# Signal labels for human-readable explanations
SIGNAL_EXPLANATIONS = {
    "PPA gap":              "Offensive efficiency edge — the most validated signal in the model (60.9% cover historically)",
    "Spread":               "Spread falls in historically profitable range",
    "SP+ confirms":         "SP+ composite rating agrees with the efficiency signal",
    "SP+ disagrees":        "SP+ disagrees — reduces confidence but PPA still holds (59.4% cover)",
    "STRONG tier":          "Team has a strong 5-year ATS profile (60.1% cover historically)",
    "ELITE tier":           "Team has an elite 5-year ATS profile (62.5% cover historically)",
    "STRONG_FADE":          "Opponent is a historically poor ATS performer (41.5% cover)",
    "returning edge":       "4-year returning production advantage — coaching continuity signal",
    "talent parity":        "Equal recruiting + PPA edge = most underpriced scenario (71.2% cover historically)",
    "talent confirms":      "Recruiting talent confirms the efficiency edge",
    "efficiency beats":     "Less-recruited team has a PPA edge — market mispricing",
    "Coach H2H":            "Head-to-head coaching record — historical matchup advantage",
    "Coach recent trend":   "Coach has won recent matchups against this opponent",
    "Home covers":          "Home team historically covers ATS in this coaching matchup",
    "conference ATS":       "Conference-level historical ATS tendency",
    "Away travels":         "Travel distance burden on away team",
    "Sharp agrees":         "Line movement confirms the model signal — sharp money on same side",
    "Line stable":          "No significant line movement — market not fading the signal",
}

TIER_MEANING = {
    "PRIME_BET":   ("💰", "PRIME BET",   "All major signals aligned — highest conviction"),
    "STRONG BET":  ("💰", "STRONG BET",  "Strong signal stack — bet with confidence"),
    "LEAN BET":    ("📊", "LEAN",        "Solid signal but fewer confirmations"),
    "PASS":        ("⏭️",  "PASS",        "Insufficient edge"),
}

CONF_STARS = {
    range(85, 101): ("⭐⭐⭐⭐⭐", "PRIME"),
    range(75,  85): ("⭐⭐⭐⭐",  "STRONG"),
    range(65,  75): ("⭐⭐⭐",    "LEAN"),
    range(0,   65): ("⭐⭐",     "MARGINAL"),
}

def conf_to_stars(confidence: int) -> tuple[str, str]:
    for r, v in CONF_STARS.items():
        if confidence in r:
            return v
    return ("⭐⭐", "MARGINAL")


def parse_edge_signals(edge_str: str) -> list[tuple[str, str]]:
    """Parse edge string into (signal, explanation) pairs."""
    signals = []
    for part in edge_str.split(" · "):
        part = part.strip()
        if not part:
            continue
        explanation = ""
        for keyword, expl in SIGNAL_EXPLANATIONS.items():
            if keyword.lower() in part.lower():
                explanation = expl
                break
        signals.append((part, explanation))
    return signals


def format_pick(pick: dict, rank: int) -> str:
    lines = []

    matchup    = pick.get("matchup", "")
    bet        = pick.get("bet", "")
    line       = pick.get("line", "")
    confidence = int(pick.get("model_score", 0))
    week       = pick.get("week", "?")
    ou         = pick.get("ou", "N/A")
    bet_type   = pick.get("bet_type", "EDGE")
    stars, tier_label = conf_to_stars(confidence)

    ppa_gap        = pick.get("ppa_gap")
    sp_gap         = pick.get("sp_gap")
    ret_gap        = pick.get("ret_gap")
    travel_miles   = pick.get("travel_miles")
    travel_bucket  = pick.get("travel_bucket")
    home_coach     = pick.get("home_coach")
    away_coach     = pick.get("away_coach")
    coach_h2h      = pick.get("coach_h2h")
    recruiting_gap = pick.get("recruiting_gap")
    rec_bucket     = pick.get("recruiting_bucket")
    line_movement  = pick.get("line_movement")

    # Header
    lines.append(f"---\n")
    lines.append(f"## {rank}. {matchup}")
    lines.append(f"**{bet}** · Line: {line} · O/U: {ou}")
    lines.append(f"{stars} **{tier_label}** · {confidence}% confidence · Week {week}\n")

    # The bet in plain English
    away, home = matchup.split(" @ ")
    bet_team = home if "home fav" in bet or "home dog" in bet else away
    if bet_type == "FADE":
        lines.append(f"**The bet:** Fade the line — bet {bet_team} to cover.")
    else:
        lines.append(f"**The bet:** {bet_team} covers the spread.")
    lines.append("")

    # Signal breakdown
    lines.append("**Why:**")
    edge_str = pick.get("edge", "")
    signals = parse_edge_signals(edge_str)
    for signal, explanation in signals:
        if explanation:
            lines.append(f"- **{signal}** — {explanation}")
        else:
            lines.append(f"- {signal}")
    lines.append("")

    # Key numbers
    lines.append("**Key numbers:**")
    if ppa_gap is not None:
        direction = "home" if ppa_gap > 0 else "away"
        lines.append(f"- PPA gap: `{ppa_gap:+.3f}` ({direction} team efficiency edge)")
    if sp_gap is not None:
        direction = "home" if sp_gap > 0 else "away"
        lines.append(f"- SP+ gap: `{sp_gap:+.1f}` ({direction} team)")
    if ret_gap is not None:
        direction = "home" if ret_gap > 0 else "away"
        lines.append(f"- Returning production: `{ret_gap:+.2f}` ({direction} returning more)")
    if recruiting_gap is not None:
        direction = "home" if recruiting_gap > 0 else "away"
        lines.append(f"- 4yr recruiting talent: `{recruiting_gap:+.1f}` pts ({direction} more talented)")
    if travel_miles is not None:
        lines.append(f"- Away team travel: `{travel_miles:.0f} miles` ({travel_bucket})")
    lines.append("")

    # Coaching
    if home_coach or away_coach:
        lines.append("**Coaches:**")
        if home_coach:
            lines.append(f"- Home: {home_coach}")
        if away_coach:
            lines.append(f"- Away: {away_coach}")
        if coach_h2h and coach_h2h.get("total", 0) >= 3:
            h2h = coach_h2h
            lines.append(
                f"- H2H record: {h2h.get('leader', 'even')} leads "
                f"{h2h.get('home_record',0)}-{h2h.get('away_record',0)} "
                f"({h2h.get('total',0)} games) · Recent trend: {h2h.get('trend','even')}"
            )
        lines.append("")

    # Line movement (if available)
    if line_movement and line_movement.get("snaps", 0) >= 2:
        mv = line_movement
        lines.append("**Line movement:**")
        if mv.get("open") is not None and mv.get("current") is not None:
            lines.append(
                f"- Open: `{mv['open']:+.1f}` → Current: `{mv['current']:+.1f}` "
                f"(moved `{mv.get('move', 0):+.1f}` pts)"
            )
        lines.append(f"- Sharp signal: {mv.get('sharp', 'no_movement')}")
        lines.append("")

    # Risk flags
    risk_flags = []
    if ppa_gap is not None and abs(ppa_gap) < 0.20:
        risk_flags.append("PPA gap is marginal (0.15-0.20) — weaker edge")
    if recruiting_gap is not None and recruiting_gap < -30 and (ppa_gap and ppa_gap > 0):
        risk_flags.append(f"Home team is less recruited by {abs(recruiting_gap):.0f} pts — talent disadvantage")
    if travel_miles is not None and travel_miles < 300 and (ppa_gap and ppa_gap > 0):
        risk_flags.append("Away team has short trip — no travel fatigue")
    if coach_h2h and coach_h2h.get("trend") != home_coach and coach_h2h.get("total", 0) >= 3:
        trend_holder = coach_h2h.get("trend", "")
        if trend_holder and trend_holder != "even" and trend_holder == away_coach:
            risk_flags.append(f"Away coach ({away_coach}) has won the recent trend")

    if risk_flags:
        lines.append("**Risk flags:**")
        for flag in risk_flags:
            lines.append(f"- ⚠️ {flag}")
        lines.append("")

    return "\n".join(lines)


def generate_report(picks: list[dict], week: int, year: int) -> str:
    today = date.today()
    lines = []

    # Header
    lines.append(f"# 🏈 CFB Picks — {year} Week {week}")
    lines.append(f"*Generated {today.strftime('%B %d, %Y')} · ONS Degenerates Corner*\n")

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append("| # | Matchup | Bet | Confidence | Tier |")
    lines.append("|---|---------|-----|-----------|------|")
    for i, pick in enumerate(picks, 1):
        stars, tier = conf_to_stars(int(pick.get("model_score", 0)))
        lines.append(
            f"| {i} | {pick.get('matchup','')} | "
            f"{pick.get('bet','')} | "
            f"{stars} {pick.get('model_score',0)}% | {tier} |"
        )
    lines.append("")

    # Model context
    lines.append("## How to read this report")
    lines.append("""
The picks are generated by a model trained on 5 seasons (2021-2025) of FBS games.
Every signal has been validated against historical ATS cover rates.

**Signal hierarchy (strongest → weakest):**
1. PPA gap >0.15 — 60.9% cover rate, validated 5/5 seasons
2. Talent parity + PPA — 71.2% cover rate (most underpriced scenario)
3. Team tier (ELITE/STRONG) — 62.5% / 60.1% cover rates
4. SP+ alignment — 62.4% cover rate when combined with PPA
5. Returning production — 64.7% cover rate combined with PPA
6. Coach H2H (3-4 games) — 72.6% cover rate (likely confounded by home field)
7. Travel distance — 52.9% cover rate at 1500+ miles (tiebreaker only)

**Confidence score:** Starts at 50 (coin flip). Each validated signal adds or subtracts
based on its historical cover rate. 80+ = strong bet, 70-79 = lean, <70 = marginal.

**This model does not guarantee results.** Bet responsibly.
""")

    # Individual picks
    lines.append("## The Picks\n")
    for i, pick in enumerate(picks, 1):
        lines.append(format_pick(pick, i))

    # Footer
    lines.append("---")
    lines.append(f"*ONS CFB Model · {year} Season · Week {week}*")
    lines.append(f"*All signals validated against 2021-2025 historical data*")

    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Generate weekly CFB picks report")
    p.add_argument("--week",   type=int, default=None)
    p.add_argument("--year",   type=int, default=date.today().year)
    p.add_argument("--stdout", action="store_true", help="Print to stdout only")
    p.add_argument("--input",  type=str, default=None, help="Path to picks JSON (default: todays_picks.json)")
    args = p.parse_args()

    picks_path = Path(args.input) if args.input else PICKS_PATH

    if not picks_path.exists():
        print(f"No picks file found at {picks_path}")
        print("Run: python scripts/generate_picks.py --week N --year YYYY first")
        return 1

    picks = json.loads(picks_path.read_text())
    if not picks:
        print("No qualifying picks this week.")
        return 0

    # Determine week from picks if not specified
    week = args.week or picks[0].get("week", 1)
    year = args.year

    report = generate_report(picks, week, year)

    if args.stdout:
        print(report)
        return 0

    # Save to file
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORT_DIR / f"picks_report_{year}_Wk{week:02d}.md"
    out_path.write_text(report)
    print(f"Report saved to {out_path}")
    print(f"{len(picks)} picks · Week {week} · {year}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
