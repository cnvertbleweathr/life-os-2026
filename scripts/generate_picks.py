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
import pandas as pd
import requests
from dotenv import load_dotenv

# Import validated score_game from walk-forward backtester
sys.path.insert(0, str(Path(__file__).resolve().parent))
from backtest_walk_forward import score_game, safe_float  # noqa: E402

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

# ─────────────────────────────────────────────────────────────────────────────
# Walk-forward tier builder for live use
# ─────────────────────────────────────────────────────────────────────────────

def _build_live_tiers(con: duckdb.DuckDBPyConnection, year: int) -> dict[str, str]:
    """
    Build team tiers using only prior-season data (walk-forward, no lookahead).
    Same logic as backtest_walk_forward.py::build_tiers().
    """
    prior = list(range(max(2018, year - 4), year))
    if not prior:
        return {}
    sf = ",".join(str(s) for s in prior)
    try:
        df = con.execute(f"""
            WITH sides AS (
                SELECT home_team AS team, spread_covered, season
                FROM main_marts.mart_cfbd_line_accuracy
                WHERE season IN ({sf}) AND spread_result IN ('covered','missed')
                UNION ALL
                SELECT away_team, NOT spread_covered, season
                FROM main_marts.mart_cfbd_line_accuracy
                WHERE season IN ({sf}) AND spread_result IN ('covered','missed')
            )
            SELECT team, season, spread_covered FROM sides
        """).df()
    except Exception:
        return {}

    tiers: dict[str, str] = {}
    n_prior = len(prior)
    for team, grp in df.groupby("team"):
        n  = len(grp)
        if n < 10: continue
        w   = grp["spread_covered"].sum()
        roi = (w * 0.909 - (n - w)) / n * 100
        seasons_seen = grp["season"].nunique()
        sp  = sum(
            1 for s, sg in grp.groupby("season")
            if (sg["spread_covered"].sum() * 0.909
                - (len(sg) - sg["spread_covered"].sum())) > 0
        )
        if seasons_seen >= 2:
            if   roi >= 20 and sp >= max(2, int(n_prior * 0.8)): tiers[team] = "ELITE"
            elif roi >= 10 and sp >= max(2, int(n_prior * 0.6)): tiers[team] = "STRONG"
            elif roi <= -20 and sp <= int(n_prior * 0.2):        tiers[team] = "STRONG_FADE"
            elif roi <= -10:                                      tiers[team] = "FADE"
            else:                                                 tiers[team] = "NEUTRAL"
        else:
            if   roi <= -15: tiers[team] = "FADE"
            else:            tiers[team] = "NEUTRAL"
    return tiers


def analyse_game(
    con: duckdb.DuckDBPyConnection,
    game: dict,
    line: dict,
    year: int,
    tiers: dict[str, str],
    coach_changes: set[str],
    prior_sp: dict[tuple, float],
) -> dict | None:
    """
    Score a game using the validated walk-forward model (score_game).
    Coach H2H and travel are fetched for display only — no confidence impact.
    """
    home   = game.get("homeTeam") or game.get("home_team")
    away   = game.get("awayTeam") or game.get("away_team")
    spread = line.get("spread")
    ou     = line.get("overUnder") or line.get("over_under") or line.get("total")

    if spread is None:
        return None

    spread = float(spread)

    # ── Build row dict compatible with score_game() ───────────────────────
    # score_game() expects a pandas-Series-like object with specific field names
    # All data uses year-1 (prior season) to match walk-forward methodology

    row_data: dict = {
        "spread":          spread,
        "home_team":       home,
        "away_team":       away,
        "home_conference": game.get("homeConference") or game.get("home_conference", ""),
        "season":          year,
        "spread_result":   None,  # not known yet — live game
        "spread_covered":  None,
    }

    # PPA gap (prior season)
    try:
        adv = con.execute("""
            SELECT team, off_ppa, off_success_rate, def_success_rate, def_havoc_total
            FROM cfbd.advanced_stats WHERE season = ? AND team IN (?, ?)
        """, [year - 1, home, away]).df()
        h = adv[adv["team"] == home]
        a = adv[adv["team"] == away]
        if not h.empty and not a.empty:
            row_data["off_ppa_gap"]            = float(h["off_ppa"].values[0]) - float(a["off_ppa"].values[0])
            row_data["home_off_success_rate"]  = float(h["off_success_rate"].values[0]) if "off_success_rate" in h else None
            row_data["away_off_success_rate"]  = float(a["off_success_rate"].values[0]) if "off_success_rate" in a else None
            row_data["home_def_success_rate"]  = float(h["def_success_rate"].values[0]) if "def_success_rate" in h else None
            row_data["away_def_success_rate"]  = float(a["def_success_rate"].values[0]) if "away_def_success_rate" in a or "def_success_rate" in a else None
            row_data["home_def_havoc"]         = float(h["def_havoc_total"].values[0]) if "def_havoc_total" in h else None
            row_data["away_def_havoc"]         = float(a["def_havoc_total"].values[0]) if "def_havoc_total" in a else None
    except Exception:
        pass

    # Returning production gap (prior season)
    try:
        ret = con.execute("""
            SELECT team, percent_ppa FROM cfbd.returning_production
            WHERE season = ? AND team IN (?, ?)
        """, [year - 1, home, away]).df()
        h_ret = ret[ret["team"] == home]
        a_ret = ret[ret["team"] == away]
        if not h_ret.empty and not a_ret.empty:
            row_data["returning_production_gap"] = (
                float(h_ret["percent_ppa"].values[0]) -
                float(a_ret["percent_ppa"].values[0])
            )
    except Exception:
        pass

    # Recruiting gap (prior season 4-year weighted)
    try:
        rec = con.execute("""
            SELECT team, weighted_talent FROM main_marts.mart_cfbd_recruiting_talent
            WHERE season = ? AND team IN (?, ?)
        """, [year - 1, home, away]).df()
        h_rec = rec[rec["team"] == home]
        a_rec = rec[rec["team"] == away]
        if not h_rec.empty and not a_rec.empty:
            row_data["recruiting_gap"] = (
                float(h_rec["weighted_talent"].values[0]) -
                float(a_rec["weighted_talent"].values[0])
            )
    except Exception:
        pass

    # Travel distance
    try:
        td = con.execute("""
            SELECT travel_miles, travel_bucket FROM main_marts.mart_cfbd_travel_distance
            WHERE home_team = ? AND away_team = ? AND season = ? LIMIT 1
        """, [home, away, year]).df()
        if not td.empty:
            row_data["travel_miles"]  = td["travel_miles"].values[0]
            row_data["travel_bucket"] = td["travel_bucket"].values[0]
    except Exception:
        pass

    row = pd.Series(row_data)

    # ── Score using validated walk-forward model ──────────────────────────
    model_score, edges, warnings = score_game(
        row, tiers, coach_changes, prior_sp
    )

    if model_score < 70:
        return None
    if len(edges) < 4:
        return None

    ppa_gap  = safe_float(row_data.get("off_ppa_gap"))
    bet_home = bool(ppa_gap and ppa_gap > 0)
    bet_team = home if bet_home else away
    home_is_fav = spread < 0

    # ── Display-only metadata (coach H2H, SP+, travel) ───────────────────
    # These do NOT affect model_score — informational only
    sp_gap     = None
    coach_h2h  = None
    home_coach = None
    away_coach = None
    travel_miles  = row_data.get("travel_miles")
    travel_bucket = row_data.get("travel_bucket")

    try:
        sp = con.execute("""
            SELECT team, rating FROM cfbd.sp_ratings
            WHERE season = ? AND team IN (?, ?)
        """, [year - 1, home, away]).df()
        h_sp = sp[sp["team"] == home]
        a_sp = sp[sp["team"] == away]
        if not h_sp.empty and not a_sp.empty:
            sp_gap = float(h_sp["rating"].values[0]) - float(a_sp["rating"].values[0])
    except Exception:
        pass

    try:
        coaches = con.execute("""
            SELECT school, full_name FROM cfbd.coaches
            WHERE year = ? AND school IN (?, ?)
        """, [year, home, away]).df()
        h_c = coaches[coaches["school"] == home]
        a_c = coaches[coaches["school"] == away]
        home_coach = h_c["full_name"].values[0] if not h_c.empty else None
        away_coach = a_c["full_name"].values[0] if not a_c.empty else None
    except Exception:
        pass

    if home_coach and away_coach:
        try:
            h2h = con.execute("""
                SELECT * FROM main_marts.mart_cfbd_coach_matchups
                WHERE (coach_a = ? AND coach_b = ?) OR (coach_a = ? AND coach_b = ?)
                LIMIT 1
            """, [home_coach, away_coach, away_coach, home_coach]).df()
            if not h2h.empty:
                r = h2h.iloc[0]
                coach_h2h = {
                    "home_record":  int(r.get("coach_a_wins", 0)),
                    "away_record":  int(r.get("coach_b_wins", 0)),
                    "total":        int(r.get("total_games", 0)),
                    "leader":       str(r.get("all_time_leader", "")),
                    "trend":        str(r.get("recent_trend_leader", "")),
                }
        except Exception:
            pass

    # ── Determine bet type ────────────────────────────────────────────────
    # STRONG_FADE teams trigger a fade bet
    away_tier = tiers.get(away, "NEUTRAL")
    home_tier = tiers.get(home, "NEUTRAL")

    if home_is_fav and home_tier == "STRONG_FADE":
        bet_type  = "FADE"
        fade_team = home
        bet_team  = away
    elif not home_is_fav and away_tier == "STRONG_FADE":
        bet_type  = "FADE"
        fade_team = away
        bet_team  = home
    else:
        bet_type  = "EDGE"
        fade_team = None

    # ── Build pick ────────────────────────────────────────────────────────
    pick = _build_pick(
        game, line, spread, float(ou) if ou else None,
        bet_team, fade_team, edges, model_score, bet_type, ppa_gap, sp_gap,
    )

    # Attach metadata
    pick["ret_gap"]          = round(float(row_data["returning_production_gap"]), 3) if "returning_production_gap" in row_data else None
    pick["recruiting_gap"]   = round(float(row_data["recruiting_gap"]), 1)           if "recruiting_gap"           in row_data else None
    pick["travel_miles"]     = round(float(travel_miles), 1)                         if travel_miles is not None                else None
    pick["travel_bucket"]    = travel_bucket
    pick["home_coach"]       = home_coach
    pick["away_coach"]       = away_coach
    pick["coach_h2h"]        = coach_h2h
    pick["model_score"]      = model_score
    pick["n_edges"]          = len(edges)
    pick["warnings"]         = warnings

    return pick

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

    EDGE_LABELS = {
        "PPA_primary":           "PPA efficiency edge",
        "PPA_extreme":           "PPA gap >0.30 (extreme)",
        "spread_prime":          "Spread 3-7 (prime range)",
        "spread_solid":          "Spread 10-14 (solid range)",
        "SP+_agrees":            "SP+ confirms direction",
        "tier_ELITE":            "ELITE tier (historical ATS)",
        "tier_STRONG":           "STRONG tier (historical ATS)",
        "conf_tailwind":         "Conference ATS tailwind",
        "ret_high_home":         "Home returning production edge",
        "ret_slight_home":       "Home slight returning edge",
        "ret_high_away":         "Away returning production edge",
        "ret_slight_away":       "Away slight returning edge",
        "talent_parity":         "Talent parity + PPA (71% hist)",
        "home_eff_beats_talent": "Home efficiency beats talent gap",
        "away_eff_beats_talent": "Away efficiency beats talent gap",
        "talent_confirms_home":  "Recruiting confirms home edge",
        "talent_confirms_away":  "Recruiting confirms away edge",
        "SR_parity":             "Success rate parity + PPA",
        "SR_confirms_home":      "Success rate confirms home",
        "SR_confirms_away":      "Success rate confirms away",
        "home_eff_beats_SR":     "Home efficiency beats SR gap",
        "away_eff_beats_SR":     "Away efficiency beats SR gap",
        "home_havoc":            "Home defense havoc edge",
        "away_havoc":            "Away defense havoc edge",
    }
    readable_edges = [EDGE_LABELS.get(e, e) for e in edges]
    edge_str = " · ".join(readable_edges[:5]) if readable_edges else "Model signal"

    stars = "⭐" * min(int(confidence / 20), 5)

    return {
        "matchup":    f"{away} @ {home}",
        "bet":        bet_str,
        "line":       f"{spread_display} ({line.get('provider','consensus')})",
        "sport":      "CFB",
        "edge":       edge_str,
        "model_score": confidence,
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

    # Build walk-forward tiers once (prior seasons only — no lookahead)
    print(f"Building walk-forward tiers for {year}...")
    tiers = _build_live_tiers(con, year)

    # Load prior-season SP+ ratings for display context
    prior_sp: dict[tuple, float] = {}
    try:
        sp_df = con.execute(
            "SELECT team, season, rating FROM cfbd.sp_ratings WHERE season = ?",
            [year - 1]
        ).df()
        prior_sp = {(r["team"], int(r["season"])): float(r["rating"])
                    for _, r in sp_df.iterrows()}
    except Exception:
        pass

    # Detect coach changes (year vs year-1) for risk filter
    coach_changes: set[str] = set()
    try:
        curr = con.execute("SELECT school AS team, full_name AS coach FROM cfbd.coaches WHERE year = ?", [year]).df()
        prev = con.execute("SELECT school AS team, full_name AS coach FROM cfbd.coaches WHERE year = ?", [year-1]).df()
        merged = curr.merge(prev, on="team", suffixes=("_c","_p"))
        coach_changes = set(merged[merged["coach_c"] != merged["coach_p"]]["team"])
        print(f"Coach changes detected: {len(coach_changes)}")
    except Exception:
        pass

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
            pick = analyse_game(con, game, line, year, tiers, coach_changes, prior_sp)
            if pick:
                picks.append(pick)
                print(f"  ✅ {pick['matchup']} — {pick['bet']} ({pick['model_score']}%)")
            else:
                home = game.get('homeTeam') or game.get('home_team','?')
                away = game.get('awayTeam') or game.get('away_team','?')
        except Exception as e:
            home = game.get('homeTeam') or game.get('home_team','?')
            away = game.get('awayTeam') or game.get('away_team','?')
            print(f"  Error analysing {home} vs {away}: {e}")

    con.close()

    # Sort: EDGE picks first (higher conviction), then FADE, then by confidence
    picks.sort(key=lambda x: (0 if x["bet_type"] == "EDGE" else 1, -x["confidence"]))
    # Cap at 8 picks — more than that is noise
    picks = picks[:8]

    print(f"\n{'='*50}")
    print(f"Generated {len(picks)} qualifying picks for Week {week} (model v3 walk-forward)")
    print(f"{'='*50}")

    if args.dry_run:
        print(json.dumps(picks, indent=2))
        return 0

    OUT.write_text(json.dumps(picks, indent=2))
    print(f"Written to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
