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

    # ── Returning production ──────────────────────────────────────────────────
    ret = con.execute("""
        SELECT team,
               percent_ppa         as pct_returning,
               percent_rushing_ppa as pct_rush_returning,
               percent_passing_ppa as pct_pass_returning
        FROM cfbd.returning_production
        WHERE season = ? AND team IN (?, ?)
    """, [year - 1, home, away]).df()

    h_ret   = ret[ret["team"] == home]
    a_ret   = ret[ret["team"] == away]
    ret_gap = None
    if not h_ret.empty and not a_ret.empty:
        h_pct   = float(h_ret["pct_returning"].values[0])
        a_pct   = float(a_ret["pct_returning"].values[0])
        ret_gap = round(h_pct - a_pct, 4)

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

    # ── Line movement ─────────────────────────────────────────────────────
    movement = None
    try:
        mv = con.execute("""
            SELECT spread_movement, movement_magnitude, sharp_signal,
                   sharp_agrees_model, composite_signal,
                   snapshots_taken, spread_latest, spread_open
            FROM main_marts.mart_cfbd_line_movement
            WHERE game_id = ? AND season = ?
            ORDER BY last_updated DESC LIMIT 1
        """, [game.get("id"), year]).df()
        if not mv.empty:
            movement = mv.iloc[0]
    except Exception:
        pass  # mart not yet built — first week of season

    # ── Rivalry check ─────────────────────────────────────────────────────
    rivalry = con.execute("""
        SELECT 1 FROM cfbd.matchup_history
        WHERE (team1 = ? AND team2 = ?) OR (team1 = ? AND team2 = ?)
    """, [home, away, away, home]).fetchone()
    is_rivalry = rivalry is not None

    # ── Coach names & H2H ────────────────────────────────────────────────
    coaches_df = con.execute(
        "SELECT school, full_name FROM cfbd.coaches WHERE year = ? AND school IN (?, ?)",
        [year - 1, home, away]
    ).df()
    home_coach_row = coaches_df[coaches_df["school"] == home]
    away_coach_row = coaches_df[coaches_df["school"] == away]
    home_coach = str(home_coach_row["full_name"].values[0]) if not home_coach_row.empty else None
    away_coach = str(away_coach_row["full_name"].values[0]) if not away_coach_row.empty else None

    coach_h2h = None
    if home_coach and away_coach:
        coach_a = min(home_coach, away_coach)
        coach_b = max(home_coach, away_coach)
        try:
            h2h_df = con.execute(
                "SELECT coach_a, coach_b, coach_a_wins, coach_b_wins, total_games, "
                "all_time_leader, recent_trend_leader, home_win_pct, home_ats_pct "
                "FROM main_marts.mart_cfbd_coach_matchups "
                "WHERE coach_a = ? AND coach_b = ? LIMIT 1",
                [coach_a, coach_b]
            ).df()
            if not h2h_df.empty:
                coach_h2h = h2h_df.iloc[0]
        except Exception:
            pass  # mart not built yet

    # ── Travel distance ───────────────────────────────────────────────────
    travel_miles  = None
    travel_bucket = None
    try:
        tdist = con.execute(
            "SELECT travel_miles, travel_bucket, long_haul, cross_country "
            "FROM main_marts.mart_cfbd_travel_distance WHERE game_id = ? LIMIT 1",
            [game.get('id')]
        ).df()
        if not tdist.empty:
            travel_miles  = tdist['travel_miles'].values[0]
            travel_bucket = str(tdist['travel_bucket'].values[0] or '')
    except Exception:
        pass

    # Inline haversine fallback when mart not yet available
    if travel_miles is None:
        try:
            gv = con.execute(
                "SELECT v.latitude, v.longitude FROM cfbd.venues v "
                "JOIN cfbd.games g ON g.venue_id = v.venue_id "
                "WHERE g.game_id = ? LIMIT 1", [game.get("id")]
            ).df()
            ah = con.execute(
                "SELECT home_team as team, v.latitude, v.longitude "
                "FROM cfbd.games g JOIN cfbd.venues v ON v.venue_id = g.venue_id "
                "WHERE g.season >= 2022 AND g.home_team = ? AND v.latitude IS NOT NULL "
                "GROUP BY home_team, v.latitude, v.longitude "
                "ORDER BY count(*) DESC LIMIT 1", [away]
            ).df()
            if not gv.empty and not ah.empty:
                import math as _math
                glat = float(gv['latitude'].values[0])
                glon = float(gv['longitude'].values[0])
                alat = float(ah['latitude'].values[0])
                alon = float(ah['longitude'].values[0])
                dlat = _math.radians(glat - alat)
                dlon = _math.radians(glon - alon)
                a = (_math.sin(dlat/2)**2 +
                     _math.cos(_math.radians(alat)) *
                     _math.cos(_math.radians(glat)) *
                     _math.sin(dlon/2)**2)
                travel_miles = round(3958.8 * 2 * _math.asin(_math.sqrt(a)), 1)
                if travel_miles < 200:    travel_bucket = 'local'
                elif travel_miles < 500:  travel_bucket = 'regional'
                elif travel_miles < 1000: travel_bucket = 'far'
                elif travel_miles < 1500: travel_bucket = 'very_far'
                else:                     travel_bucket = 'cross_country'
        except Exception:
            pass

    # ── 4-year weighted recruiting talent ────────────────────────────────
    recruiting_gap = None
    recruiting_bucket = None
    try:
        rec = con.execute(
            "SELECT home.weighted_talent - away.weighted_talent AS gap, "
            "home.talent_percentile AS home_pct, away.talent_percentile AS away_pct "
            "FROM main_marts.mart_cfbd_recruiting_talent home "
            "JOIN main_marts.mart_cfbd_recruiting_talent away "
            "ON away.team = ? AND away.season = home.season "
            "WHERE home.team = ? AND home.season = ?",
            [away, home, year - 1]
        ).df()
        if not rec.empty:
            recruiting_gap = float(rec["gap"].values[0])
            home_pct = float(rec["home_pct"].values[0])
            away_pct = float(rec["away_pct"].values[0])
            if recruiting_gap > 30:
                recruiting_bucket = "home_big"
            elif recruiting_gap > 10:
                recruiting_bucket = "home_slight"
            elif recruiting_gap < -30:
                recruiting_bucket = "away_big"
            elif recruiting_gap < -10:
                recruiting_bucket = "away_slight"
            else:
                recruiting_bucket = "even"
    except Exception:
        pass  # mart not built yet

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

    # Rule 5: Spread range
    # Validated: 3-7 → 51.9% | 10-14 → 51.8% | 14-17 → 46.4% (-11.5% ROI) | 17+ → 50.8%
    # Sweet spots: 3-7 and 10-14. Tighten upper limit to 14. Penalize 14-17.
    if 3 <= abs_spread <= 7 and ppa_gap and abs(ppa_gap) > 0.15:
        edges.append(f"Spread {spread:+.1f} in prime range (3-7)")
        confidence += 10
    elif 10 <= abs_spread <= 14 and ppa_gap and abs(ppa_gap) > 0.15:
        edges.append(f"Spread {spread:+.1f} in solid range (10-14)")
        confidence += 8
    elif 7 <= abs_spread < 10:
        pass  # neutral — 48.8% not worth adjusting
    elif 14 < abs_spread <= 17:
        confidence -= 8   # 46.4% cover — actively bad
    elif abs_spread > 17:
        confidence -= 5   # 50.8% — less bad than 14-17 surprisingly

    # Rule 6: SP+ alignment
    # Validated: PPA + SP+ agrees → 62.4% cover +19.2% ROI (1,930g)
    #            PPA + SP+ disagrees → 59.4% +13.4% (101g) — still profitable, not a kill
    # SP+ agreement: modest bump. SP+ disagreement: mild damper only.
    if sp_agrees is not None and ppa_gap and abs(ppa_gap) > 0.15:
        if sp_agrees:
            edges.append("SP+ confirms PPA direction")
            confidence += 7   # was 8 — 62.4% cover justified
        else:
            warnings.append("SP+ disagrees with PPA — reduced confidence")
            confidence -= 4   # was implicit 0 — 59.4% still covers, mild penalty

    # Rule 7: Team tier bonus
    # Validated: ELITE 62.5% +19.3% | STRONG 60.1% +14.7% | NEUTRAL 52.4% | FADE 46.0% -12.2% | STRONG_FADE 41.5% -20.8%
    # Cleanest monotonic signal in the dataset — push weights higher
    bet_team = home if (ppa_gap and ppa_gap > 0) else away
    bet_prof  = hp if bet_team == home else ap
    if bet_prof is not None:
        tier = bet_prof["tier"]
        if tier == "ELITE":
            edges.append(f"{bet_team} ELITE tier")
            confidence += 12   # 62.5% cover — strongest non-PPA signal
        elif tier == "STRONG":
            edges.append(f"{bet_team} STRONG tier")
            confidence += 7    # 60.1% cover — solid
        elif tier == "FADE":
            warnings.append(f"{bet_team} is FADE tier")
            confidence -= 12   # 46.0% — real penalty
        elif tier == "STRONG_FADE":
            warnings.append(f"{bet_team} is STRONG_FADE tier")
            confidence -= 18   # 41.5% — severe penalty

    # Rule 8: Conference filter
    # Validated ROI — Big Ten: -7.0% | ACC: -7.0% | Mountain West: -7.4% | American Athletic: -8.1%
    # Sun Belt: -5.5% (less bad than thought — keep mild penalty)
    # Big 12: +5.4% | Pac-12: +3.1% — actually worth a small bonus
    home_conf = game.get("homeConference", game.get("home_conference", ""))
    if home_conf in ("Big Ten", "ACC", "Mountain West", "American Athletic") and home_is_fav and ppa_gap and ppa_gap > 0:
        warnings.append(f"{home_conf} home team — conference ATS headwind (-7% ROI)")
        confidence -= 6   # was 5, bumped — all four are -7%+ ROI
    elif home_conf == "Sun Belt" and home_is_fav and ppa_gap and ppa_gap > 0:
        warnings.append(f"Sun Belt home team — mild ATS headwind")
        confidence -= 3   # milder — only -5.5% ROI
    elif home_conf in ("Big 12", "Pac-12") and home_is_fav and ppa_gap and ppa_gap > 0:
        edges.append(f"{home_conf} home team — conference ATS tailwind (+5% ROI)")
        confidence += 3   # new — Big 12 +5.4%, Pac-12 +3.1%

    # Rule 9a: Returning production gap
    # Validated: PPA + home returning → 64.7% cover +23.5% ROI (1,084g)
    # Standalone returning NOT predictive — only meaningful combined with PPA
    has_ppa_edge = ppa_gap is not None and abs(ppa_gap) > 0.15
    if ret_gap is not None and has_ppa_edge:
        if ret_gap > 0.05:
            edges.append(f"Home returning edge {ret_gap:+.2f} — 64.7% cover w/ PPA")
            confidence += 6
        elif ret_gap < -0.05:
            if ppa_gap and ppa_gap < 0:  # betting away, away returning more
                edges.append(f"Away returning edge {ret_gap:+.2f} — confirms away bet")
                confidence += 6
            else:
                # Away returning more but still betting home — 59.8% still covers
                warnings.append(f"Away returning edge {ret_gap:+.2f} — mild headwind")
                confidence -= 2

    # Rule 9b: Line movement (available Wed+ when ≥2 snapshots exist)
    if movement is not None:
        sharp  = str(movement.get("sharp_signal", "no_movement"))
        agrees = movement.get("sharp_agrees_model")
        mag    = float(movement.get("movement_magnitude") or 0)
        snaps  = int(movement.get("snapshots_taken") or 0)
        comp   = str(movement.get("composite_signal", "PASS"))

        if snaps >= 2:
            if comp == "STRONG_BET" and agrees:
                edges.append(f"Sharp agrees — line moved {mag:.1f} pts toward model")
                confidence += 12
            elif comp == "BET" and sharp == "no_movement":
                edges.append("Line stable — market not fading signal")
                confidence += 5
            elif comp == "FADE_SIGNAL":
                warnings.append(f"Sharp opposes model — {mag:.1f} pt move against signal")
                confidence -= 15
            elif sharp != "no_movement" and agrees is False and mag >= 1.0:
                warnings.append(f"1+ pt move against model direction")
                confidence -= 8

    # Rule 10: Coach H2H record
    # Validated: 3-4g → 72.6% cover +38.7% ROI | 5-7g → 69.2% +32% | 8+g → 63.1% +20.4%
    # Weakens with sample size — likely confounded by program quality + home field
    if coach_h2h is not None and has_ppa_edge and int(coach_h2h.get("total_games") or 0) >= 3:
        if home_coach and away_coach:
            h_w = int(coach_h2h["coach_a_wins"] if home_coach < away_coach else coach_h2h["coach_b_wins"])
            a_w = int(coach_h2h["coach_b_wins"] if home_coach < away_coach else coach_h2h["coach_a_wins"])
        else:
            h_w, a_w = 0, 0
        total_g   = int(coach_h2h.get("total_games") or 0)
        leader    = str(coach_h2h.get("all_time_leader", ""))
        trend     = str(coach_h2h.get("recent_trend_leader", ""))
        home_ats  = coach_h2h.get("home_ats_pct")
        bet_coach = home_coach if (ppa_gap and ppa_gap > 0) else away_coach

        # Sample-size calibrated bonus
        if total_g <= 4:   h2h_bonus, h2h_pen = 8, 5
        elif total_g <= 7: h2h_bonus, h2h_pen = 6, 4
        else:              h2h_bonus, h2h_pen = 4, 3

        record_str = f"{h_w}-{a_w} ({total_g}g)"
        if leader == bet_coach:
            edges.append(f"Coach H2H: {bet_coach} leads {record_str}")
            confidence += h2h_bonus
        elif leader and leader != "even" and leader != bet_coach:
            warnings.append(f"Coach H2H: opponent leads {record_str}")
            confidence -= h2h_pen

        if trend == bet_coach and trend != "even":
            edges.append(f"Coach recent trend: {bet_coach} dominant")
            confidence += 3
        elif trend and trend != "even" and trend != bet_coach:
            warnings.append("Coach recent trend favors opponent")
            confidence -= 2

        if home_ats is not None and home_is_fav:
            ha = float(home_ats)
            if ha >= 65:
                edges.append(f"Home covers {ha:.0f}% ATS vs this coach")
                confidence += 4
            elif ha <= 35:
                warnings.append(f"Home covers only {ha:.0f}% ATS vs this coach")
                confidence -= 3

    # Rule 11: Travel distance
    # Validated: 1000-1499mi → 51.3% cover | 1500+mi → 52.9% cover +1.1% ROI
    # Weak signal — tiebreaker only, weights reduced significantly
    if travel_miles is not None and has_ppa_edge:
        tm = float(travel_miles)
        betting_away = bool(ppa_gap and ppa_gap < 0)
        if tm >= 1500:
            if not betting_away:
                edges.append(f'Away travels {tm:.0f} mi (cross-country)')
                confidence += 2
            else:
                warnings.append(f'Betting away team traveling {tm:.0f} mi')
                confidence -= 2
        elif tm >= 1000:
            if not betting_away:
                edges.append(f'Away travels {tm:.0f} mi (long haul)')
                confidence += 1
            else:
                warnings.append(f'Away team traveling {tm:.0f} mi')
                confidence -= 1

    # Rule 12: 4-year weighted recruiting talent gap
    # Validated findings (COUNTERINTUITIVE):
    #   PPA + even talent:  71.2% cover +35.9% ROI (628g) — STRONGEST COMBO
    #   PPA + home talent:  63.1% cover +20.5% ROI (3,029g)
    #   PPA + away talent:  63.1% cover +20.5% ROI (1,152g)
    #   Recruiting standalone: NO predictive value — market prices talent in
    #
    # Key insight: when a less-talented team has a PPA edge, the market
    # undervalues them most. Talent parity + PPA = maximum mispricing.
    if recruiting_gap is not None and has_ppa_edge:
        rg = float(recruiting_gap)
        bet_home = bool(ppa_gap and ppa_gap > 0)

        # Even talent + PPA = most underpriced situation
        if abs(rg) <= 10:
            edges.append(f"Talent parity ({rg:+.0f} pts) + PPA edge — 71.2% cover historically")
            confidence += 10  # strongest recruiting signal

        # Talent disadvantage for bet team — market overvalues talent, PPA corrects
        elif rg < -10 and bet_home:
            # Betting home team that's less recruited — efficiency overcoming talent
            edges.append(f"Home efficiency beats talent gap ({rg:+.0f} pts) — market mispricing")
            confidence += 6
        elif rg > 10 and not bet_home:
            # Betting away team that's less recruited
            edges.append(f"Away efficiency beats talent gap ({rg:+.0f} pts) — market mispricing")
            confidence += 6

        # Talent confirms PPA — modest bonus (already priced in somewhat)
        elif rg > 10 and bet_home:
            edges.append(f"Home talent confirms PPA edge ({rg:+.0f} pts)")
            confidence += 3
        elif rg < -10 and not bet_home:
            edges.append(f"Away talent confirms PPA edge ({rg:+.0f} pts)")
            confidence += 3

    # ── Determine if this qualifies ───────────────────────────────────────
    # has_ppa_edge already set in Rule 9a above
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

    pick = _build_pick(
        game, line, spread, ou, bet_team, None,
        edges=edges, confidence=min(confidence, 95),
        bet_type="EDGE", ppa_gap=ppa_gap, sp_gap=sp_gap,
    )
    if pick:
        pick["ret_gap"]          = round(ret_gap, 3)          if ret_gap          is not None else None
        pick["recruiting_gap"]   = round(recruiting_gap, 1)   if recruiting_gap   is not None else None
        pick["recruiting_bucket"] = recruiting_bucket
        pick["travel_miles"]  = round(float(travel_miles), 1) if travel_miles is not None else None
        pick["travel_bucket"] = travel_bucket
        pick["home_coach"]    = home_coach
        pick["away_coach"] = away_coach
        if coach_h2h is not None and home_coach and away_coach:
            h_w = int(coach_h2h["coach_a_wins"] if home_coach < away_coach else coach_h2h["coach_b_wins"])
            a_w = int(coach_h2h["coach_b_wins"] if home_coach < away_coach else coach_h2h["coach_a_wins"])
            pick["coach_h2h"] = {
                "home_record": h_w,
                "away_record": a_w,
                "total":       int(coach_h2h.get("total_games") or 0),
                "leader":      str(coach_h2h.get("all_time_leader", "")),
                "trend":       str(coach_h2h.get("recent_trend_leader", "")),
            }
    if pick and movement is not None:
        pick["line_movement"] = {
            "open":    float(movement["spread_open"])     if movement.get("spread_open")     is not None else None,
            "current": float(movement["spread_latest"])   if movement.get("spread_latest")   is not None else None,
            "move":    float(movement["spread_movement"]) if movement.get("spread_movement") is not None else None,
            "sharp":   str(movement.get("sharp_signal", "")),
            "snaps":   int(movement.get("snapshots_taken") or 0),
        }
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

    edge_str = " · ".join(edges[:5]) if edges else "Model signal"

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
