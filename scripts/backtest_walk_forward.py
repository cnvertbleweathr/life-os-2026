#!/usr/bin/env python3
"""
backtest_walk_forward.py — v3

Clean walk-forward validation. All audit points addressed:

  1. SP+ uses PRIOR-SEASON rating (l.season - 1) not same-season
  2. Spread consistency: spread_covered computed against same deduped spread
  3. Team tiers require 2+ prior seasons before ELITE/STRONG assigned
  4. Renamed confidence → model_score throughout
  5. PPA 0.30+ flagged as high-value/high-variance (small sample)
  6. Signal combination breakdown added

Usage:
  python scripts/backtest_walk_forward.py
  python scripts/backtest_walk_forward.py --min-score 70
  python scripts/backtest_walk_forward.py --combos   # show signal combo analysis
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import duckdb
import pandas as pd

ROOT    = Path(__file__).resolve().parents[1]
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")


def safe_float(val, default=None):
    if val is None: return default
    try:
        f = float(val)
        return None if f != f else f
    except (TypeError, ValueError):
        return default


def week_bucket(week: int) -> str:
    if week <= 4:  return "Wk 1-4"
    if week <= 8:  return "Wk 5-8"
    if week <= 12: return "Wk 9-12"
    return              "Wk 13+"


def ret_bucket(ret_gap) -> str:
    r = safe_float(ret_gap)
    if r is None: return "unknown"
    if r >  0.15: return "high_home_ret"
    if r >  0.05: return "slight_home_ret"
    if r > -0.05: return "parity"
    if r > -0.15: return "slight_away_ret"
    return               "high_away_ret"


def build_tiers(con, target_season: int) -> dict[str, str]:
    """
    Walk-forward tiers from prior seasons only.
    Requires 2+ prior seasons before assigning ELITE/STRONG.
    """
    prior = list(range(max(2018, target_season - 4), target_season))
    if len(prior) < 1:
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

    tiers = {}
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

        # Require 2+ seasons before assigning directional tiers
        if seasons_seen >= 2:
            if   roi >= 20 and sp >= max(2, int(n_prior * 0.8)):
                tiers[team] = "ELITE"
            elif roi >= 10 and sp >= max(2, int(n_prior * 0.6)):
                tiers[team] = "STRONG"
            elif roi <= -20 and sp <= int(n_prior * 0.2):
                tiers[team] = "STRONG_FADE"
            elif roi <= -10:
                tiers[team] = "FADE"
            else:
                tiers[team] = "NEUTRAL"
        else:
            # Only 1 prior season — conservative assignment
            if   roi <= -15: tiers[team] = "FADE"
            elif roi >= 15:  tiers[team] = "NEUTRAL"  # don't over-promote on 1 season
            else:            tiers[team] = "NEUTRAL"

    return tiers


def score_game(
    row: pd.Series,
    tiers: dict[str, str],
    coach_changes: set[str],
    prior_sp: dict[tuple, float],   # (team, season) → SP+ rating from PRIOR season
    disabled: set[str] | None = None,  # signal group names to disable entirely
) -> tuple[int, list[str], list[str]]:
    """
    Returns (model_score, edges, warnings).
    model_score is NOT a probability — it's an ordinal ranking signal.
    """
    disabled = disabled or set()
    model_score = 50
    edges: list[str] = []
    warnings: list[str] = []

    spread = safe_float(row.get("spread"))
    if spread is None:
        return 0, [], []

    abs_spread  = abs(spread)
    home_is_fav = spread < 0
    ppa_gap     = safe_float(row.get("off_ppa_gap"))
    season      = int(row.get("season", 0))
    home        = str(row.get("home_team", ""))
    away        = str(row.get("away_team", ""))

    # Hard spread filters
    if abs_spread > 28:
        return 0, [], []
    if abs_spread > 21 and (ppa_gap is None or abs(ppa_gap) < 0.25):
        return 0, [], []

    # PPA required — uses prior-season advanced stats (year-1 join in SQL)
    has_ppa_edge = ppa_gap is not None and abs(ppa_gap) > 0.15
    if not has_ppa_edge:
        return 0, [], []

    bet_home = ppa_gap > 0
    bet_team = home if bet_home else away
    ret_gap  = safe_float(row.get("returning_production_gap"))

    # Coach change filter — disabled key: "coach_change"
    if "coach_change" not in disabled:
        coach_changed = bet_team in coach_changes
        if coach_changed:
            warnings.append("coach_change")
            model_score -= 6
            if ret_gap is not None:
                if (bet_home and ret_gap < -0.10) or (not bet_home and ret_gap > 0.10):
                    warnings.append("coach_change+low_ret")
                    model_score -= 8

    # Rule 4: PPA gap — always active (required signal, not ablatable)
    if abs(ppa_gap) > 0.30:
        edges.append("PPA_extreme")
        model_score += 25
    else:
        edges.append("PPA_primary")
        model_score += 15

    # Rule 5: Spread range — disabled key: "spread"
    if "spread" not in disabled:
        if 3 <= abs_spread <= 7:
            edges.append("spread_prime")
            model_score += 10
        elif 10 <= abs_spread <= 14:
            edges.append("spread_solid")
            model_score += 8
        elif 14 < abs_spread <= 17:
            model_score -= 8
        elif 17 < abs_spread <= 21:
            model_score -= 12
        elif abs_spread > 21:
            model_score -= 15

    # Rule 6: SP+ alignment — disabled key: "sp_plus"
    if "sp_plus" not in disabled:
        home_sp_prior = prior_sp.get((home, season - 1))
        away_sp_prior = prior_sp.get((away, season - 1))
        if home_sp_prior is not None and away_sp_prior is not None:
            sp_gap    = home_sp_prior - away_sp_prior
            sp_agrees = (sp_gap > 0 and bet_home) or (sp_gap < 0 and not bet_home)
            if sp_agrees:
                edges.append("SP+_agrees")
                model_score += 3   # ablation: -0.3% ΔROI — mostly redundant after other signals
            else:
                warnings.append("SP+_disagrees")
                model_score -= 2   # disagreement still a warning, mild only

    # Rule 7: Team tier — disabled key: "tier"
    if "tier" not in disabled:
        bet_tier = tiers.get(bet_team, "NEUTRAL")
        if bet_tier == "ELITE":
            edges.append("tier_ELITE")
            model_score += 8    # reduced from 12 — small n in walk-forward, conservative
        elif bet_tier == "STRONG":
            edges.append("tier_STRONG")
            model_score += 7    # ablation: -3.3% ΔROI — keep
        elif bet_tier == "FADE":
            warnings.append("tier_FADE")
            model_score -= 12   # penalties more reliable than boosts — keep
        elif bet_tier == "STRONG_FADE":
            warnings.append("tier_STRONG_FADE")
            model_score -= 18   # keep — strong penalty validated

    # Rule 8: Conference — disabled key: "conference"
    if "conference" not in disabled:
        home_conf = str(row.get("home_conference", ""))
        if home_is_fav and ppa_gap > 0:
            if home_conf in ("Big Ten", "ACC", "Mountain West", "American Athletic"):
                model_score -= 6
            elif home_conf == "Sun Belt":
                model_score -= 3
            elif home_conf in ("Big 12", "Pac-12"):
                edges.append("conf_tailwind")
                model_score += 3

    # Rule 9a: Returning production — disabled key: "returning"
    if "returning" not in disabled and ret_gap is not None:
        if ret_gap > 0.15 and bet_home:
            edges.append("ret_high_home")
            model_score += 9
        elif ret_gap > 0.05 and bet_home:
            edges.append("ret_slight_home")
            model_score += 5
        elif ret_gap < -0.15 and bet_home:
            warnings.append("ret_low_home")
            model_score -= 7
        elif ret_gap < -0.05 and bet_home:
            warnings.append("ret_away_edge")
            model_score -= 3
        elif ret_gap < -0.15 and not bet_home:
            edges.append("ret_high_away")
            model_score += 9
        elif ret_gap < -0.05 and not bet_home:
            edges.append("ret_slight_away")
            model_score += 5
        elif ret_gap > 0.15 and not bet_home:
            warnings.append("ret_low_away")
            model_score -= 7
        elif ret_gap > 0.05 and not bet_home:
            warnings.append("ret_home_edge")
            model_score -= 3

    # Rule 11: Travel — disabled key: "travel"
    if "travel" not in disabled:
        travel = safe_float(row.get("travel_miles"))
        if travel is not None:
            if travel >= 1500:
                model_score += 1 if not (ppa_gap < 0) else -1   # ablation: -0.2% ΔROI — tiebreaker only
            # 1000-1499 miles: not worth adjusting — below noise threshold

    # Rule 12: Recruiting — disabled key: "recruiting"
    if "recruiting" not in disabled:
        rec_gap = safe_float(row.get("recruiting_gap"))
        if rec_gap is not None:
            if abs(rec_gap) <= 10:
                edges.append("talent_parity")
                model_score += 10
            elif rec_gap < -10 and bet_home:
                edges.append("home_eff_beats_talent")
                model_score += 6
            elif rec_gap > 10 and not bet_home:
                edges.append("away_eff_beats_talent")
                model_score += 6
            elif rec_gap > 10 and bet_home:
                edges.append("talent_confirms_home")
                model_score += 3
            elif rec_gap < -10 and not bet_home:
                edges.append("talent_confirms_away")
                model_score += 3

    # Rule 13: Success rate — disabled key: "success_rate"
    if "success_rate" not in disabled:
        home_sr  = safe_float(row.get("home_off_success_rate"))
        away_def = safe_float(row.get("away_def_success_rate"))
        away_sr  = safe_float(row.get("away_off_success_rate"))
        home_def = safe_float(row.get("home_def_success_rate"))
        if bet_home and home_sr is not None and away_def is not None:
            net_sr = home_sr - away_def
            if abs(net_sr) <= 0.05:
                edges.append("SR_parity")
                model_score += 12  # ablation: -6.0% ΔROI — strongest confirmation signal
            elif net_sr > 0.05:
                edges.append("SR_confirms_home")
                model_score += 4
            elif net_sr < -0.05:
                edges.append("home_eff_beats_SR")
                model_score += 7   # efficiency overcomes SR gap — strong mispricing
        elif not bet_home and away_sr is not None and home_def is not None:
            net_sr = away_sr - home_def
            if abs(net_sr) <= 0.05:
                edges.append("SR_parity")
                model_score += 12  # ablation: -6.0% ΔROI
            elif net_sr > 0.05:
                edges.append("SR_confirms_away")
                model_score += 4
            elif net_sr < -0.05:
                edges.append("away_eff_beats_SR")
                model_score += 7

    # Rule 14: Havoc — disabled key: "havoc"
    if "havoc" not in disabled:
        home_hv = safe_float(row.get("home_def_havoc"))
        away_hv = safe_float(row.get("away_def_havoc"))
        if home_hv is not None and away_hv is not None:
            hd = home_hv - away_hv
            if hd > 0.02:
                if bet_home:
                    edges.append("home_havoc")
                    model_score += 4   # ablation: -1.4% ΔROI — mild but real
                else:
                    warnings.append("home_havoc_vs_bet")
                    model_score -= 3
            elif hd < -0.02:
                if not bet_home:
                    edges.append("away_havoc")
                    model_score += 4   # ablation: -1.4% ΔROI
                else:
                    warnings.append("away_havoc_vs_bet")
                model_score -= 3

    return min(model_score, 99), edges, warnings


def combo_key(edges: list[str]) -> str:
    """Canonical signal combination string."""
    core = [e for e in edges if e not in ("PPA_primary", "PPA_extreme")]
    return "+".join(sorted(core)) if core else "PPA_only"


def print_table(rows: list[tuple]) -> None:
    for row in rows:
        print("  " + "  ".join(str(c) for c in row))


def run(min_score: int, show_combos: bool) -> None:
    print("Loading data (one row per game, consensus preferred)...")
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
    except Exception as e:
        print(f"Cannot open DuckDB: {e}"); sys.exit(1)

    df = con.execute("""
        WITH ranked AS (
            SELECT
                gc.game_id, gc.season, gc.week,
                gc.home_team, gc.away_team, gc.home_conference,
                gc.spread, gc.spread_result, gc.spread_covered,
                gc.off_ppa_gap,
                gc.returning_production_gap,
                gc.recruiting_gap,
                gc.home_off_success_rate,
                gc.away_off_success_rate,
                gc.home_def_success_rate,
                gc.away_def_success_rate,
                gc.home_def_havoc,
                gc.away_def_havoc,
                gc.home_coach, gc.away_coach,
                td.travel_miles,
                ROW_NUMBER() OVER (
                    PARTITION BY gc.game_id
                    ORDER BY CASE gc.provider
                        WHEN 'consensus' THEN 1
                        WHEN 'DraftKings' THEN 2
                        WHEN 'ESPN Bet'   THEN 3
                        ELSE 4 END
                ) AS rn
            FROM main_marts.mart_cfbd_game_context gc
            LEFT JOIN main_marts.mart_cfbd_travel_distance td
                ON td.game_id = gc.game_id
            WHERE gc.spread_result IN ('covered','missed','push')
              AND gc.season BETWEEN 2022 AND 2025
              AND gc.spread IS NOT NULL
        )
        SELECT * FROM ranked WHERE rn = 1
    """).df()

    # Load ALL SP+ ratings for prior-season lookup
    sp_df = con.execute("""
        SELECT team, season, rating FROM cfbd.sp_ratings
    """).df()
    prior_sp = {(r["team"], int(r["season"])): float(r["rating"])
                for _, r in sp_df.iterrows()}

    # Coach data for change detection
    coaches_df = con.execute("""
        SELECT school AS team, year AS season, full_name AS coach
        FROM cfbd.coaches ORDER BY school, year
    """).df()

    con.close()

    print(f"Loaded {len(df):,} games (one per game)\n")
    print("NOTE: SP+ now uses PRIOR-SEASON ratings only")
    print("NOTE: Team tiers require 2+ prior seasons for ELITE/STRONG\n")

    all_results = []

    for season in sorted(df["season"].unique()):
        print(f"Season {season}...")
        try:
            con2  = duckdb.connect(DB_PATH, read_only=True)
            tiers = build_tiers(con2, season)
            con2.close()
        except Exception as e:
            print(f"  Tier error: {e}")
            tiers = {}

        # Coach changes
        curr = coaches_df[coaches_df["season"] == season]
        prev = coaches_df[coaches_df["season"] == season - 1]
        merged = curr.merge(prev, on="team", suffixes=("_c","_p"))
        coach_changes = set(merged[merged["coach_c"] != merged["coach_p"]]["team"])

        tc = pd.Series(list(tiers.values())).value_counts().to_dict()
        print(f"  Tiers: {tc} | Coach changes: {len(coach_changes)}")

        season_df  = df[df["season"] == season]
        season_res = []

        for _, row in season_df.iterrows():
            ms, edges, warnings = score_game(row, tiers, coach_changes, prior_sp)
            if ms < min_score: continue
            if len(edges) < 4: continue

            ppa_gap  = safe_float(row.get("off_ppa_gap"), 0)
            bet_home = ppa_gap > 0
            result   = str(row.get("spread_result", ""))
            ret_gap  = safe_float(row.get("returning_production_gap"))
            week     = int(row["week"])

            if result == "push":
                pnl, outcome = 0.0, "push"
            elif bet_home:
                pnl     = 0.909 if result == "covered" else -1.0
                outcome = "win"  if result == "covered" else "loss"
            else:
                pnl     = 0.909 if result == "missed"  else -1.0
                outcome = "win"  if result == "missed"  else "loss"

            season_res.append({
                "season":      int(row["season"]),
                "week":        week,
                "week_bucket": week_bucket(week),
                "home_team":   str(row["home_team"]),
                "away_team":   str(row["away_team"]),
                "bet_team":    str(row["home_team"]) if bet_home else str(row["away_team"]),
                "spread":      float(row["spread"]),
                "model_score": ms,
                "n_edges":     len(edges),
                "ppa_gap":     ppa_gap,
                "ret_bucket":  ret_bucket(ret_gap),
                "combo":       combo_key(edges),
                "edges":       edges,
                "outcome":     outcome,
                "pnl":         pnl,
            })

        gw = sum(1 for r in season_res if r["outcome"] == "win")
        gl = sum(1 for r in season_res if r["outcome"] == "loss")
        gp = sum(r["pnl"] for r in season_res)
        n  = len(season_res)
        gr = gp / n * 100 if n else 0
        gwp = gw / (gw + gl) * 100 if (gw + gl) else 0
        mk  = "✅" if gp > 0 else "❌"
        print(f"  → {n} bets  {gw}-{gl}  {gwp:.1f}%  ${gp:+.2f}  ROI {gr:+.1f}%  {mk}\n")
        all_results.extend(season_res)

    if not all_results:
        print("No qualifying picks.")
        return

    rdf = pd.DataFrame(all_results)
    total     = len(rdf)
    wins      = (rdf["outcome"] == "win").sum()
    losses    = (rdf["outcome"] == "loss").sum()
    pushes    = (rdf["outcome"] == "push").sum()
    pnl       = rdf["pnl"].sum()
    roi       = pnl / total * 100
    total_roi = roi   # saved — never overwritten by combo loop
    wp        = wins / (wins + losses) * 100 if (wins + losses) else 0

    print("=" * 65)
    print("FULL CLEAN WALK-FORWARD — v3")
    print("Prior-season SP+ | 2+ seasons for tiers | model_score (not probability)")
    print("=" * 65)
    print(f"Seasons tested:  {', '.join(str(s) for s in sorted(rdf['season'].unique()))}")
    print(f"Min model_score: {min_score}  |  Min edges: 4")
    print(f"Total bets:      {total:,}")
    print(f"Record:          {wins}-{losses}-{pushes}")
    print(f"Win rate:        {wp:.1f}%  (breakeven: 52.4%)")
    print(f"Total P&L:       ${pnl:+.2f}")
    print(f"ROI:             {roi:+.1f}%")
    print()

    def section(title, grp_col, rdf, order=None):
        print(f"─" * 65)
        print(title)
        print(f"─" * 65)
        groups = rdf.groupby(grp_col)
        keys   = order if order else sorted(groups.groups.keys())
        for k in keys:
            if k not in groups.groups: continue
            g   = groups.get_group(k)
            if len(g) < 5: continue
            gw  = (g["outcome"] == "win").sum()
            gl  = (g["outcome"] == "loss").sum()
            gp  = g["pnl"].sum()
            gr  = gp / len(g) * 100
            gwp = gw / (gw + gl) * 100 if (gw + gl) else 0
            mk  = "✅" if gp > 0 else "❌"
            print(f"  {str(k):<38} {len(g):4d}  {gw}-{gl}  "
                  f"{gwp:.1f}%  ROI {gr:+.1f}%  {mk}")
        print()

    section("BY SEASON", "season", rdf,
            order=sorted(rdf["season"].unique()))

    section("BY WEEK — does prior-season PPA decay?", "week_bucket", rdf,
            order=["Wk 1-4","Wk 5-8","Wk 9-12","Wk 13+"])

    section("BY RETURNING PRODUCTION", "ret_bucket", rdf,
            order=["high_home_ret","slight_home_ret","parity",
                   "slight_away_ret","high_away_ret","unknown"])

    # Score buckets
    print("─" * 65)
    print("BY MODEL SCORE BUCKET  (not probability)")
    print("─" * 65)
    for lo, hi, label in [(70,80,"70-79"),(80,90,"80-89"),(90,100,"90-99")]:
        g = rdf[(rdf["model_score"] >= lo) & (rdf["model_score"] < hi)]
        if g.empty: continue
        gw = (g["outcome"]=="win").sum()
        gl = (g["outcome"]=="loss").sum()
        gp = g["pnl"].sum()
        gr = gp / len(g) * 100
        gwp = gw/(gw+gl)*100 if (gw+gl) else 0
        mk = "✅" if gp > 0 else "❌"
        print(f"  {label}:  {len(g):4d} bets  {gw}-{gl}  "
              f"{gwp:.1f}%  ROI {gr:+.1f}%  {mk}")
    print()

    section("BY SIGNAL COUNT", "n_edges", rdf,
            order=sorted(rdf["n_edges"].unique()))

    # PPA buckets
    print("─" * 65)
    print("BY PPA GAP SIZE")
    print("─" * 65)
    for lo, hi, label in [(.15,.20,"0.15-0.20"),(.20,.25,"0.20-0.25"),
                           (.25,.30,"0.25-0.30"),(.30,1.0,"0.30+ ⚠️ small n")]:
        g = rdf[(rdf["ppa_gap"].abs()>=lo)&(rdf["ppa_gap"].abs()<hi)]
        if len(g) < 5: continue
        gw = (g["outcome"]=="win").sum()
        gl = (g["outcome"]=="loss").sum()
        gp = g["pnl"].sum()
        gr = gp/len(g)*100
        gwp = gw/(gw+gl)*100 if (gw+gl) else 0
        mk = "✅" if gp > 0 else "❌"
        print(f"  PPA {label:<20} {len(g):4d}  {gw}-{gl}  "
              f"{gwp:.1f}%  ROI {gr:+.1f}%  {mk}")
    print()

    # Signal combination analysis
    if show_combos:
        print("─" * 65)
        print("SIGNAL COMBINATION ANALYSIS (min 5 bets)")
        print("─" * 65)
        combo_stats = defaultdict(lambda: {"w":0,"l":0,"pnl":0.0})
        for _, row in rdf.iterrows():
            k = row["combo"]
            combo_stats[k]["w"]   += row["outcome"] == "win"
            combo_stats[k]["l"]   += row["outcome"] == "loss"
            combo_stats[k]["pnl"] += row["pnl"]

        rows = []
        for combo, s in combo_stats.items():
            n   = s["w"] + s["l"]
            if n < 5: continue
            combo_roi = s["pnl"] / n * 100
            wp_ = s["w"] / n * 100 if n else 0
            rows.append((combo_roi, combo, n, s["w"], s["l"], wp_, s["pnl"]))

        rows.sort(reverse=True)
        print(f"  {'Combination':<45} {'N':>5}  {'W-L':<10}  "
              f"{'Win%':>6}  {'ROI':>8}")
        print(f"  {'-'*45} {'-'*5}  {'-'*10}  {'-'*6}  {'-'*8}")
        for combo_roi, combo, n, w, l, wp_, p in rows[:30]:
            mk = "✅" if p > 0 else "❌"
            print(f"  {combo:<45} {n:>5}  {w}-{l:<8}  "
                  f"{wp_:>5.1f}%  {combo_roi:>+7.1f}%  {mk}")
        print()

    if show_combos:
        print("─" * 65)
        print("INDIVIDUAL SIGNAL PRESENCE (when signal fires, does it help?)")
        print("─" * 65)
        all_signals = set()
        for edges in rdf["edges"]:
            all_signals.update(edges)
        signal_rows = []
        skip_signals = {'PPA_primary', 'PPA_extreme'}  # fires on all bets — not useful for comparison
        for sig in sorted(all_signals):
            if sig in skip_signals: continue
            has_sig  = rdf["edges"].apply(lambda e: sig in e)
            grp_yes  = rdf[has_sig]
            grp_no   = rdf[~has_sig]
            if len(grp_yes) < 5: continue
            yw  = (grp_yes["outcome"]=="win").sum()
            yl  = (grp_yes["outcome"]=="loss").sum()
            yp  = grp_yes["pnl"].sum()
            yr  = yp / len(grp_yes) * 100
            ywp = yw/(yw+yl)*100 if (yw+yl) else 0
            nw  = (grp_no["outcome"]=="win").sum()
            nl  = (grp_no["outcome"]=="loss").sum()
            nr  = grp_no["pnl"].sum() / len(grp_no) * 100 if len(grp_no) else 0
            delta = yr - nr
            signal_rows.append((delta, sig, len(grp_yes), ywp, yr))
        signal_rows.sort(reverse=True)
        print("NOTE: vs_baseline is descriptive only — samples are not controlled")
        print(f"  {'Signal':<35} {'N':>5}  {'Win%':>6}  {'ROI':>8}  {'vs_baseline':>12}")
        print(f"  {'-'*35} {'-'*5}  {'-'*6}  {'-'*8}  {'-'*12}")
        for delta, sig, n, wp_, roi_ in signal_rows:
            mk = "↑" if delta > 0 else "↓"
            print(f"  {sig:<35} {n:>5}  {wp_:>5.1f}%  {roi_:>+7.1f}%  {mk}{abs(delta):>+.1f}% vs no-signal")
        print()

    profitable = sum(1 for s in rdf["season"].unique()
                     if rdf[rdf["season"]==s]["pnl"].sum() > 0)
    print(f"Profitable seasons: {profitable}/{len(rdf['season'].unique())}")
    if pnl > 0:
        print(f"✅ PROFITABLE: ${pnl:+.2f} on {total} $1 bets  |  ROI {total_roi:+.1f}%")
    else:
        print(f"❌ NOT PROFITABLE: ${pnl:+.2f}  |  ROI {total_roi:+.1f}%")
    print()
    print("CAVEATS:")
    print("  - model_score is ordinal ranking, not a probability")
    print("  - PPA 0.30+ bucket: small sample, high variance")
    print("  - SP+ now prior-season; team tiers require 2+ seasons")
    print("=" * 65)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--min-score", type=int, default=70,
                   help="Minimum model_score to include (default: 70)")
    p.add_argument("--combos", action="store_true",
                   help="Show signal combination breakdown")
    args = p.parse_args()
    run(args.min_score, args.combos)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
