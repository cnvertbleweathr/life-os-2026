#!/usr/bin/env python3
"""
generate_picks.py

Fetches this week's CFB games + lines from CFBD API, runs edge analysis
against cfbd.team_profiles and cfbd.advanced_stats in DuckDB, and writes
qualifying picks to data/bets/todays_picks.json for the Sports page.

Runs weekly during CFB season (August → January).
Off-season: exits cleanly with an empty picks file.

Usage:
  python scripts/generate_picks.py
  python scripts/generate_picks.py --week 3 --year 2026
  python scripts/generate_picks.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import duckdb
import requests
from dotenv import load_dotenv

ROOT    = Path(__file__).resolve().parents[1]
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")
OUT     = ROOT / "data" / "bets" / "todays_picks.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT / ".env")

API_BASE   = "https://api.collegefootballdata.com"
CFBD_TOKEN = os.getenv("CFBD_API_TOKEN", "")

# Conferences to include (exclude G5 outliers that inflate PPA samples)
TARGET_CONFERENCES = {
    "SEC", "Big Ten", "Big 12", "ACC", "Pac-12",
    "American Athletic", "Mountain West", "Conference USA",
    "Mid-American", "Sun Belt",
}

# ─────────────────────────────────────────────────────────────────────────────
# CFBD helpers
# ─────────────────────────────────────────────────────────────────────────────

def cfbd_get(endpoint: str, params: dict) -> list[dict]:
    if not CFBD_TOKEN:
        print("⚠️  CFBD_API_TOKEN not set — cannot fetch live games", file=sys.stderr)
        return []
    headers = {"Authorization": f"Bearer {CFBD_TOKEN}"}
    url     = f"{API_BASE}{endpoint}"
    try:
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"CFBD API error: {e}", file=sys.stderr)
        return []


def current_cfb_week(year: int) -> int | None:
    """Estimate current CFB week from date. Season: Week 1 ≈ last week of Aug."""
    today = date.today()
    if today.month < 8 or today.month > 1:
        return None  # off-season
    # Rough: Week 1 starts ~Aug 24
    from datetime import timedelta
    season_start = date(year, 8, 24)
    delta = (today - season_start).days
    if delta < 0:
        return None
    week = delta // 7 + 1
    return min(week, 15)


# ─────────────────────────────────────────────────────────────────────────────
# Edge analysis (mirrors pregame_lookup.py logic)
# ─────────────────────────────────────────────────────────────────────────────

def analyse_game(
    con: duckdb.DuckDBPyConnection,
    game: dict,
    line: dict,
    year: int,
) -> dict | None:
    """
    Returns a pick dict if the game meets betting criteria, else None.
    """
    home    = game.get("homeTeam") or game.get("home_team")
    away    = game.get("awayTeam") or game.get("away_team")
    spread  = line.get("spread")
    ou      = line.get("overUnder") or line.get("over_under") or line.get("total")

    if spread is None:
        return None

    spread      = float(spread)
    abs_spread  = abs(spread)
    home_is_fav = spread < 0

    # ── Team profiles ─────────────────────────────────────────────────────
    profiles = con.execute("""
        SELECT * FROM cfbd.team_profiles WHERE team IN (?, ?)
    """, [home, away]).df()

    home_prof = profiles[profiles["team"] == home]
    away_prof = profiles[profiles["team"] == away]
    hp = home_prof.iloc[0] if not home_prof.empty else None
    ap = away_prof.iloc[0] if not away_prof.empty else None

    # ── Advanced stats (PPA) ──────────────────────────────────────────────
    adv = con.execute("""
        SELECT team, off_ppa, def_ppa, off_success_rate, def_havoc_total
        FROM cfbd.advanced_stats WHERE season = ? AND team IN (?, ?)
    """, [year - 1, home, away]).df()  # use prior season for pre-game lookup

    h_adv = adv[adv["team"] == home]
    a_adv = adv[adv["team"] == away]
    ppa_gap = None
    if not h_adv.empty and not a_adv.empty:
        ppa_gap = float(h_adv["off_ppa"].values[0]) - float(a_adv["off_ppa"].values[0])

    # ── SP+ ───────────────────────────────────────────────────────────────
    sp = con.execute("""
        SELECT team, rating FROM cfbd.sp_ratings
        WHERE season = ? AND team IN (?, ?)
    """, [year - 1, home, away]).df()

    h_sp = sp[sp["team"] == home]
    a_sp = sp[sp["team"] == away]
    sp_gap = None
    sp_agrees = None
    if not h_sp.empty and not a_sp.empty:
        sp_gap = float(h_sp["rating"].values[0]) - float(a_sp["rating"].values[0])
        sp_agrees = (sp_gap > 0 and ppa_gap and ppa_gap > 0) or \
                    (sp_gap < 0 and ppa_gap and ppa_gap < 0)

    # ── Rivalry check ─────────────────────────────────────────────────────
    rivalry = con.execute("""
        SELECT 1 FROM cfbd.matchup_history
        WHERE (team1 = ? AND team2 = ?) OR (team1 = ? AND team2 = ?)
    """, [home, away, away, home]).fetchone()
    is_rivalry = rivalry is not None

    # ── Signal accumulation ───────────────────────────────────────────────
    edges    : list[str] = []
    warnings : list[str] = []
    confidence = 50  # baseline

    # Rule 1: rivalry — skip
    if is_rivalry:
        return None

    # Rule 2: STRONG_FADE home favorite — fade home team
    if hp is not None and hp["tier"] == "STRONG_FADE" and home_is_fav:
        warnings.append(f"{home} STRONG_FADE home fav")

    # Rule 3: STRONG_FADE away favorite — fade away team
    if ap is not None and ap["tier"] == "STRONG_FADE" and not home_is_fav:
        warnings.append(f"{away} STRONG_FADE away fav")

    # Rule 3b: STRONG_FADE tier generally (any situation) — add as soft warning only
    # but don't trigger a fade bet unless they're in the bad situation (fav role)
    if hp is not None and hp["tier"] == "STRONG_FADE" and not home_is_fav:
        pass  # home dog — their worst role is fav, this isn't that
    if ap is not None and ap["tier"] == "STRONG_FADE" and home_is_fav:
        pass  # away dog — skip, not actionable

    # Rule 4: PPA gap >0.15
    if ppa_gap is not None:
        if abs(ppa_gap) > 0.30:
            edges.append(f"PPA gap {ppa_gap:+.3f} — EXTREME")
            confidence += 25
        elif abs(ppa_gap) > 0.15:
            edges.append(f"PPA gap {ppa_gap:+.3f} — primary signal")
            confidence += 15

    # Rule 5: Spread in optimal range
    if abs_spread <= 14 and ppa_gap and abs(ppa_gap) > 0.15:
        edges.append(f"Spread {spread:+.1f} in optimal range (≤14)")
        confidence += 10
    elif abs_spread > 17:
        confidence -= 10

    # Rule 6: SP+ alignment
    if sp_agrees and ppa_gap and abs(ppa_gap) > 0.15:
        edges.append("SP+ confirms PPA direction")
        confidence += 8

    # Rule 7: Team tier bonus
    bet_team = home if (ppa_gap and ppa_gap > 0) else away
    bet_prof  = hp if bet_team == home else ap
    if bet_prof is not None:
        tier = bet_prof["tier"]
        if tier == "ELITE":
            edges.append(f"{bet_team} ELITE tier")
            confidence += 10
        elif tier == "STRONG":
            edges.append(f"{bet_team} STRONG tier")
            confidence += 5
        elif tier in ("STRONG_FADE", "FADE"):
            warnings.append(f"{bet_team} is {tier}")
            confidence -= 15

    # Rule 8: Conference filter — Big Ten/ACC/Sun Belt home teams historically weak
    home_conf = game.get("homeConference", game.get("home_conference", ""))
    if home_conf in ("Big Ten", "ACC", "Sun Belt") and home_is_fav and ppa_gap and ppa_gap > 0:
        warnings.append(f"{home_conf} home team — conference ATS headwind")
        confidence -= 5

    # ── Determine if this qualifies ───────────────────────────────────────
    # Minimum: PPA gap signal + confidence > 60
    has_ppa_edge = ppa_gap is not None and abs(ppa_gap) > 0.15
    has_hard_fade = any("STRONG_FADE" in w for w in warnings)

    # Surface as a FADE only when:
    # - Spread is between 3 and 20 (no blowouts, no toss-ups)
    # - We have PPA data to confirm (no data = no bet)
    # - The fade team is actually in the expected role
    if has_hard_fade and not has_ppa_edge:
        if abs_spread > 20 or abs_spread < 3:
            return None  # blowout or toss-up — not interesting
        if ppa_gap is None:
            return None  # no efficiency data — skip
        fade_team  = home if (hp is not None and hp["tier"] == "STRONG_FADE" and home_is_fav) \
                     else away
        cover_team = away if fade_team == home else home
        # Sanity check: make sure the cover team isn't also a STRONG_FADE
        cover_prof = hp if cover_team == home else ap
        if cover_prof is not None and cover_prof["tier"] == "STRONG_FADE":
            return None  # both teams are fades — skip
        return _build_pick(
            game, line, spread, ou, cover_team, fade_team,
            edges=warnings, confidence=max(confidence, 55),
            bet_type="FADE", ppa_gap=ppa_gap, sp_gap=sp_gap,
        )

    if not has_ppa_edge or confidence < 60:
        return None

    return _build_pick(
        game, line, spread, ou, bet_team, None,
        edges=edges, confidence=min(confidence, 95),
        bet_type="EDGE", ppa_gap=ppa_gap, sp_gap=sp_gap,
    )


def _build_pick(
    game: dict, line: dict, spread: float, ou: float | None,
    bet_team: str, fade_team: str | None,
    edges: list[str], confidence: int,
    bet_type: str, ppa_gap: float | None, sp_gap: float | None,
) -> dict:
    home   = game.get("homeTeam") or game.get("home_team")
    away   = game.get("awayTeam") or game.get("away_team")
    week   = game.get("week", "?")
    spread_display = f"{spread:+.1f}"

    if bet_type == "FADE":
        bet_str = f"Fade {fade_team} — bet {bet_team}"
    else:
        # Determine what the bet is
        is_home_bet = bet_team == home
        home_is_fav = spread < 0
        if is_home_bet and home_is_fav:
            bet_str = f"{home} {spread:+.1f} (home fav)"
        elif is_home_bet and not home_is_fav:
            bet_str = f"{home} +{abs(spread):.1f} (home dog)"
        elif not is_home_bet and not home_is_fav:
            bet_str = f"{away} -{abs(spread):.1f} (away fav)"
        else:
            bet_str = f"{away} +{abs(spread):.1f} (away dog)"

    edge_str = " · ".join(edges[:3]) if edges else "Model signal"

    stars = "⭐" * min(int(confidence / 20), 5)

    return {
        "matchup":    f"{away} @ {home}",
        "bet":        bet_str,
        "line":       f"{spread_display} ({line.get('provider','consensus')})",
        "sport":      "CFB",
        "edge":       edge_str,
        "confidence": confidence,
        "stars":      stars,
        "week":       week,
        "ou":         str(ou) if ou else "N/A",
        "ppa_gap":    round(ppa_gap, 3) if ppa_gap else None,
        "sp_gap":     round(sp_gap, 1)  if sp_gap  else None,
        "bet_type":   bet_type,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description="Generate CFB picks for Degenerates Corner")
    p.add_argument("--year",    type=int, default=date.today().year)
    p.add_argument("--week",    type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    year = args.year
    week = args.week or current_cfb_week(year)

    if week is None:
        print(f"Off-season — no CFB games to analyse (today: {date.today()})")
        # Write empty picks so Sports page shows the placeholder cleanly
        OUT.write_text(json.dumps([], indent=2))
        return 0

    print(f"🏈 Generating picks for {year} Week {week}...")

    # Fetch games
    games = cfbd_get("/games", {"year": year, "week": week, "division": "fbs"})
    if not games:
        print("No games found from CFBD API")
        OUT.write_text(json.dumps([], indent=2))
        return 0

    # Fetch lines
    lines_data = cfbd_get("/lines", {"year": year, "week": week})
    lines_by_id: dict[int, dict] = {}
    for lg in lines_data:
        gid = lg.get("id")
        if not gid:
            continue
        # Prefer consensus or first available line
        game_lines = lg.get("lines", [])
        if not game_lines:
            continue
        consensus = next((l for l in game_lines if l.get("provider", "").lower() == "consensus"), None)
        lines_by_id[gid] = consensus or game_lines[0]

    print(f"Found {len(games)} games, {len(lines_by_id)} with lines")

    # Connect to DuckDB and analyse
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
    except Exception as e:
        print(f"Cannot open DuckDB: {e}", file=sys.stderr)
        return 1

    picks: list[dict] = []
    for game in games:
        gid  = game.get("id")
        line = lines_by_id.get(gid)
        if not line:
            continue

        conf = game.get("homeConference", game.get("home_conference", ""))
        if conf and conf not in TARGET_CONFERENCES:
            continue  # Skip small conferences

        try:
            pick = analyse_game(con, game, line, year)
            if pick:
                picks.append(pick)
                print(f"  ✅ {pick['matchup']} — {pick['bet']} ({pick['confidence']}%)")
        except Exception as e:
            print(f"  Error analysing {game.get('homeTeam') or game.get('home_team')} vs {game.get('awayTeam') or game.get('away_team')}: {e}")

    con.close()

    # Sort: EDGE picks first (higher conviction), then FADE, then by confidence
    picks.sort(key=lambda x: (0 if x["bet_type"] == "EDGE" else 1, -x["confidence"]))
    # Cap at 8 picks — more than that is noise
    picks = picks[:8]

    print(f"\n{'='*50}")
    print(f"Generated {len(picks)} qualifying picks for Week {week}")
    print(f"{'='*50}")

    if args.dry_run:
        print(json.dumps(picks, indent=2))
        return 0

    OUT.write_text(json.dumps(picks, indent=2))
    print(f"Written to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
