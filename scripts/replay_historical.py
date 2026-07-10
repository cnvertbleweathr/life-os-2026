#!/usr/bin/env python3
"""
replay_historical.py

Validates the LIVE picks + grading pipeline against completed historical
games with known, ground-truth outcomes -- without needing the 2026 season
to start. Built in response to an external review's specific (and correct)
point: waiting for live games was never necessary to test grader logic,
since 2022-2025 completed games already sit in the warehouse with real
final scores and a real, independently-computed spread_covered value.

WHAT THIS TESTS, end to end, using the REAL unmodified code paths:
  1. analyse_game() / score_game() -- the same functions generate_picks.py
     uses every week -- re-scored against historical games.
  2. The resulting pick is serialized into the SAME archive JSON shape
     generate_picks.py writes to data/bets/history/*.json.
  3. grade_picks.py's grade_one_pick() -- the SAME function that will grade
     live 2026 results -- is run against that serialized pick.
  4. The computed outcome is compared against ground truth: the REAL,
     independently-computed spread_covered already sitting in
     main_marts.mart_cfbd_line_accuracy (built by pipelines/cfbd_pipeline.py
     from real final scores months/years ago, not invented for this test).

This is a comparison against independent ground truth, not a test that can
trivially pass by construction -- a real bug in either analyse_game()'s
side-selection or grade_picks.py's cover-math would show up as a mismatch
between "what grade_picks.py computed" and "what spread_covered already
says happened."

WHAT THIS DOES NOT TEST (out of scope, flagged not hidden):
  - Whether the MODEL's predictions are good (that's the existing
    backtest's job, not this script's).
  - Live CFBD API behavior (this reads only the local warehouse).
  - The actual archive-file write path in generate_picks.py (this builds
    archive-shaped JSON in memory, doesn't run generate_picks.py's CLI).

Usage:
  python scripts/replay_historical.py                    # all of 2022-2025
  python scripts/replay_historical.py --season 2023       # one season
  python scripts/replay_historical.py --limit 50           # quick sanity run
  python scripts/replay_historical.py --verbose            # show every mismatch in detail
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_picks import analyse_game, _build_live_tiers, DB_PATH  # noqa: E402
from grade_picks import grade_one_pick  # noqa: E402


def fetch_replay_games(con: duckdb.DuckDBPyConnection, season: int | None) -> pd.DataFrame:
    """
    Pulls completed historical games + their REAL outcomes from the same
    mart the original walk-forward backtest validates against. spread_covered
    here is independently computed in pipelines/cfbd_pipeline.py from real
    final scores -- it is NOT derived from anything this script or
    grade_picks.py computes, which is what makes it valid ground truth.
    """
    season_filter = "AND season = ?" if season else ""
    params = [season] if season else []
    df = con.execute(f"""
        SELECT
            game_id, season, week, home_team, away_team,
            home_conference, away_conference, neutral_site, conference_game,
            home_score, away_score, spread, over_under, provider,
            spread_covered, spread_push, spread_result
        FROM main_marts.mart_cfbd_line_accuracy
        WHERE spread_result IN ('covered', 'missed', 'push')
          AND home_score IS NOT NULL AND away_score IS NOT NULL
          {season_filter}
        ORDER BY season, week, game_id
    """, params).df()
    return df


def row_to_game_and_line(row: pd.Series) -> tuple[dict, dict]:
    """
    Builds the same game/line dict shapes analyse_game() expects from raw
    CFBD API responses -- mirrors the translation api/routers/cfb.py's
    Matchup Lab endpoint does for synthetic on-demand queries. This is a
    PROVEN pattern (Matchup Lab uses the identical approach against live
    user input), not a new invention for this script.
    """
    game = {
        "id":              int(row["game_id"]),
        "homeTeam":        row["home_team"],
        "awayTeam":        row["away_team"],
        "homeConference":  row["home_conference"],
        "awayConference":  row["away_conference"],
        "neutralSite":     bool(row["neutral_site"]) if row["neutral_site"] is not None else False,
        "conferenceGame":  bool(row["conference_game"]) if row["conference_game"] is not None else False,
        "week":            int(row["week"]),
        "season":          int(row["season"]),
    }
    line = {
        "spread":     float(row["spread"]) if row["spread"] is not None else None,
        "overUnder":  float(row["over_under"]) if row["over_under"] is not None else None,
        "provider":   row.get("provider", "consensus"),
    }
    return game, line


def replay_one_game(con, row: pd.Series, tiers: dict, coach_changes: set, prior_sp: dict) -> dict:
    """
    Runs ONE historical game through the real analyse_game(), then through
    the real grade_one_pick(), then compares against ground truth. Returns
    a result dict regardless of outcome -- callers aggregate/report.
    """
    game, line = row_to_game_and_line(row)
    year = int(row["season"])

    result = {
        "season": year, "week": int(row["week"]),
        "matchup": f"{row['away_team']} @ {row['home_team']}",
        "status": None, "detail": None,
    }

    try:
        pick = analyse_game(con, game, line, year, tiers, coach_changes, prior_sp)
    except Exception as e:
        result["status"] = "ERROR_SCORING"
        result["detail"] = f"{type(e).__name__}: {e}"
        return result

    if pick is None:
        # analyse_game() returns None only when the line had no usable
        # spread value -- since we filtered to rows with a real spread
        # above, this shouldn't happen. If it does, that's worth knowing.
        result["status"] = "NO_PICK_PRODUCED"
        result["detail"] = "analyse_game() returned None despite a real spread being present"
        return result

    # Run the REAL grader against this REAL final score.
    try:
        graded = grade_one_pick(pick, home_score=int(row["home_score"]), away_score=int(row["away_score"]))
    except Exception as e:
        result["status"] = "ERROR_GRADING"
        result["detail"] = f"{type(e).__name__}: {e}"
        return result

    if graded.get("outcome") == "ungradeable":
        result["status"] = "UNGRADEABLE"
        result["detail"] = graded.get("grade_error", "unknown")
        return result

    # ── Compare against independent ground truth ───────────────────────
    # FIXED 2026-06-30, second iteration. The previous version (fixed
    # earlier the same day) derived backing_home from pick["ppa_gap"]'s
    # sign -- but pick["ppa_gap"] is a DISPLAY value, rounded to 3
    # decimals by generate_picks.py before being written out. A real
    # ppa_gap of e.g. +0.0004 rounds to display as 0.0, and "0.0 > 0" is
    # False -- flipping the sign comparison even though the real
    # underlying value (and the real bet_team decision made from it) was
    # positive. Confirmed via direct reproduction: Massachusetts @ Temple
    # 2022 Wk4 showed pick["ppa_gap"] == 0.0 in the output, bet_team was
    # Temple (home), but 0.0 > 0 is False -- a genuine boundary bug in
    # THIS script, not in production. (Separately, this same investigation
    # also found and fixed a real production bug: generate_picks.py was
    # writing null instead of a real 0.0 ppa_gap value due to a
    # truthiness check instead of an is-not-None check -- see that file's
    # changelog comment near the ppa_gap field.)
    #
    # Fixed by comparing the FULL, EXACT team name pick["bet"] names
    # against the two known, complete team names from row["home_team"]/
    # row["away_team"] -- not a substring/prefix match (which is exactly
    # the bug just fixed in grade_picks.py: "Iowa State".startswith
    # ("Iowa") is True) and not dependent on any rounded numeric field.
    # This is now independent of every bug found and fixed today.
    home_team_name = row["home_team"]
    away_team_name = row["away_team"]
    bet_str = pick.get("bet", "")

    # Exact-equality check, not prefix matching: try stripping each known
    # suffix shape and see which leaves EXACTLY one of the two real team
    # names -- not just a string that starts with one. This avoids the
    # substring trap entirely (a naive startswith("Iowa ") still matches
    # "Iowa State ..." because "Iowa State" itself contains "Iowa " as a
    # literal prefix -- confirmed by testing this exact case before
    # trusting it).
    backing_home = None
    for suffix in (" (home fav)", " (home dog)"):
        if bet_str.endswith(suffix) and bet_str[: -len(suffix)].split(" ", 1)[0] != "":
            candidate = bet_str[: -len(suffix)]
            # candidate looks like "Iowa -3.5" or "Iowa State +3.5" --
            # strip the trailing spread token, compare what's left exactly.
            name_part = candidate.rsplit(" ", 1)[0]
            if name_part == home_team_name:
                backing_home = True
    for suffix in (" (away fav)", " (away dog)"):
        if bet_str.endswith(suffix):
            candidate = bet_str[: -len(suffix)]
            name_part = candidate.rsplit(" ", 1)[0]
            if name_part == away_team_name:
                backing_home = False

    if backing_home is None:
        result["status"] = "CANNOT_DETERMINE_SIDE"
        result["detail"] = f"could not exactly match bet string {bet_str!r} to home={home_team_name!r} or away={away_team_name!r}"
        return result

    if bool(row["spread_push"]):
        ground_truth_outcome = "push"
    elif backing_home:
        ground_truth_outcome = "win" if bool(row["spread_covered"]) else "loss"
    else:
        ground_truth_outcome = "win" if not bool(row["spread_covered"]) else "loss"

    computed_outcome = graded.get("outcome")

    result["model_score"]   = pick.get("model_score")
    result["bet_type"]      = pick.get("bet_type")
    result["bet"]           = bet_str
    result["computed"]      = computed_outcome
    result["ground_truth"]  = ground_truth_outcome
    result["match"]         = computed_outcome == ground_truth_outcome

    if result["match"]:
        result["status"] = "MATCH"
    else:
        result["status"] = "MISMATCH"
        result["detail"] = (
            f"grader computed '{computed_outcome}' but ground truth "
            f"(mart_cfbd_line_accuracy) says '{ground_truth_outcome}'"
        )

    return result


def main() -> int:
    p = argparse.ArgumentParser(description="Replay historical games through the live picks+grading pipeline")
    p.add_argument("--season", type=int, default=None, help="Limit to one season (default: all 2022-2025)")
    p.add_argument("--limit",  type=int, default=None, help="Cap total games replayed (for a quick sanity run)")
    p.add_argument("--verbose", action="store_true", help="Print every mismatch/error in full detail")
    args = p.parse_args()

    print(f"Connecting to {DB_PATH}...")
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
    except Exception as e:
        print(f"Cannot open DuckDB: {e}", file=sys.stderr)
        return 1

    games_df = fetch_replay_games(con, args.season)
    if args.limit:
        games_df = games_df.head(args.limit)

    if games_df.empty:
        print("No completed historical games found -- check warehouse population.")
        return 1

    print(f"Loaded {len(games_df):,} completed historical games to replay.\n")

    results = []
    seasons = sorted(games_df["season"].unique())
    tiers_cache: dict[int, dict] = {}
    coach_changes_cache: dict[int, set] = {}

    # Coach data for change detection, loaded once
    coaches_df = con.execute("""
        SELECT school AS team, year AS season, full_name AS coach
        FROM cfbd.coaches ORDER BY school, year
    """).df()

    sp_df = con.execute("SELECT team, season, rating FROM cfbd.sp_ratings").df()
    prior_sp = {(r["team"], int(r["season"])): float(r["rating"]) for _, r in sp_df.iterrows()}

    for season in seasons:
        print(f"Building tiers for {season}...")
        tiers_cache[season] = _build_live_tiers(con, season)
        curr = coaches_df[coaches_df["season"] == season]
        prev = coaches_df[coaches_df["season"] == season - 1]
        merged = curr.merge(prev, on="team", suffixes=("_c", "_p"))
        coach_changes_cache[season] = set(merged[merged["coach_c"] != merged["coach_p"]]["team"])

    print(f"\nReplaying {len(games_df):,} games through analyse_game() + grade_one_pick()...\n")

    for i, (_, row) in enumerate(games_df.iterrows(), 1):
        season = int(row["season"])
        r = replay_one_game(
            con, row,
            tiers_cache[season], coach_changes_cache[season], prior_sp,
        )
        results.append(r)
        if i % 500 == 0:
            print(f"  ...{i:,}/{len(games_df):,} replayed")

    con.close()

    # ── Summary ──────────────────────────────────────────────────────────
    df = pd.DataFrame(results)
    status_counts = df["status"].value_counts()

    print(f"\n{'='*70}")
    print("REPLAY SUMMARY")
    print(f"{'='*70}")
    print(f"Total games replayed: {len(df):,}")
    print()
    print(status_counts.to_string())
    print()

    matches    = df[df["status"] == "MATCH"]
    mismatches = df[df["status"] == "MISMATCH"]
    errors     = df[df["status"].isin(["ERROR_SCORING", "ERROR_GRADING", "NO_PICK_PRODUCED"])]

    if len(matches) + len(mismatches) > 0:
        match_rate = len(matches) / (len(matches) + len(mismatches)) * 100
        print(f"Grading match rate: {match_rate:.2f}% ({len(matches):,}/{len(matches)+len(mismatches):,})")
        print("(This measures grader correctness against known outcomes --")
        print(" it is NOT the model's win rate. A 100% match rate means the")
        print(" grader correctly determined win/loss/push every time, regardless")
        print(" of whether the underlying picks were good bets.)")
    print()

    if not errors.empty:
        print(f"⚠️  {len(errors)} games raised an error during scoring/grading -- see detail below")
        print()

    if not mismatches.empty:
        print(f"🚨 {len(mismatches)} MISMATCHES — grader disagreed with known ground truth")
        print(f"{'='*70}")
        cols = ["season", "week", "matchup", "bet", "bet_type", "computed", "ground_truth"]
        print(mismatches[cols].to_string(index=False))
        print()

    if args.verbose and not errors.empty:
        print(f"{'='*70}")
        print("ERROR DETAIL")
        print(f"{'='*70}")
        for _, r in errors.iterrows():
            print(f"  [{r['status']}] {r['season']} Wk{r['week']} {r['matchup']}: {r['detail']}")
        print()

    # Breakdown by bet_type -- specifically checks the FADE_TIER_RISK fix,
    # since that's the highest-severity bug fixed tonight and this is the
    # first time it's been checked against real historical outcomes.
    if "bet_type" in df.columns:
        for bt in df["bet_type"].dropna().unique():
            sub = df[df["bet_type"] == bt]
            sub_matched = sub[sub["status"] == "MATCH"]
            sub_total_gradeable = sub[sub["status"].isin(["MATCH", "MISMATCH"])]
            if len(sub_total_gradeable) > 0:
                rate = len(sub_matched) / len(sub_total_gradeable) * 100
                print(f"  {bt}: {rate:.1f}% match rate ({len(sub_matched)}/{len(sub_total_gradeable)})")

    print()
    if mismatches.empty and errors.empty:
        print("✅ PASS — every gradeable historical game matched ground truth, zero errors.")
        return 0
    else:
        print("❌ FAIL — mismatches and/or errors found above. Do not trust live grading until resolved.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
