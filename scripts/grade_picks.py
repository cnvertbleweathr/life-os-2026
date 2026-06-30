#!/usr/bin/env python3
"""
grade_picks.py

Grades archived CFB picks (data/bets/history/{season}_wk{week}.json) against
real final scores from CFBD. Designed to run daily via daily_sync.py --
idempotent and safe to re-run: already-graded games are skipped, partially-
finished weeks get re-checked until every game resolves.

Cover-result math is copied verbatim from pipelines/cfbd_pipeline.py's
lines_resource() -- the SAME formula that builds cfbd.lines and, downstream,
mart_cfbd_line_accuracy for historical seasons. This is intentional: grading
live 2026 picks with a different formula than the one that grades 2021-2025
would make any "live model vs backtest" comparison meaningless. One formula,
two call sites (historical ETL, live grading) -- not a reimplementation.

Usage:
  python scripts/grade_picks.py                  # grade every ungraded week found
  python scripts/grade_picks.py --season 2026 --week 1   # grade one week only
  python scripts/grade_picks.py --dry-run        # show what would change, write nothing
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_picks import cfbd_get  # noqa: E402  -- one source of truth for CFBD fetches

ROOT        = Path(__file__).resolve().parents[1]
HISTORY_DIR = ROOT / "data" / "bets" / "history"


# ─────────────────────────────────────────────────────────────────────────────
# Cover-result math -- copied from pipelines/cfbd_pipeline.py::lines_resource()
# Keep these two in sync if either changes; see module docstring for why.
# ─────────────────────────────────────────────────────────────────────────────

def compute_cover(spread: float, home_score: int, away_score: int) -> tuple[bool | None, bool]:
    """
    Returns (spread_covered, spread_push). spread_covered is from the HOME
    team's perspective, matching lines_resource()'s convention exactly:
    negative spread = home favored; home covers if actual_margin > -spread.
    """
    actual_margin = home_score - away_score
    if spread + actual_margin == 0:
        return None, True
    return actual_margin > -spread, False


def grade_one_pick(pick: dict, home_score: int, away_score: int) -> dict:
    """
    Returns {"outcome": "win"|"loss"|"push", "pnl": float} for a single
    archived pick, given the final score.

    UPDATED 2026-06-29: generate_picks.py's bet_type == "FADE" reversal
    bug is fixed (it used to silently swap bet_team to the opposite side
    from whatever score_game() actually scored, producing a "Fade X — bet
    Y" string with X and Y as genuinely different teams). bet_type is now
    "FADE_TIER_RISK" purely as a risk label -- the bet itself is always on
    whichever team score_game()'s PPA-direction selection chose, and
    pick["bet"] always has the normal "{team} {spread} (home/away fav/dog)"
    shape regardless of bet_type. The old special-cased "— bet " string
    parsing below is removed -- it was built around the buggy shape and
    would silently misattribute the backed team if left in place.
    """
    matchup = pick["matchup"]
    away_team, home_team = [s.strip() for s in matchup.split(" @ ")]
    spread = None
    try:
        # pick["line"] looks like "-7.0 (DraftKings)" -- the spread is
        # everything before the first space.
        spread = float(pick["line"].split(" ")[0])
    except (KeyError, ValueError, IndexError):
        return {"outcome": "ungradeable", "pnl": 0.0, "grade_error": "could not parse spread from line"}

    spread_covered, push = compute_cover(spread, home_score, away_score)

    if push:
        return {"outcome": "push", "pnl": 0.0}

    # pick["bet"] always starts with the backed team's name now
    # ("Georgia Tech -7.0 (home fav)", "Notre Dame -20.5 (away fav)") --
    # bet_type no longer changes this shape.
    bet_str = pick.get("bet", "")
    backed_team = home_team if bet_str.startswith(home_team) else away_team

    backing_home = backed_team == home_team

    if backing_home:
        win = bool(spread_covered)
    else:
        win = not spread_covered

    return {
        "outcome": "win" if win else "loss",
        "pnl": 0.909 if win else -1.0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Per-file grading
# ─────────────────────────────────────────────────────────────────────────────

def grade_history_file(path: Path, dry_run: bool) -> dict:
    """
    Grades every game in one history file against real CFBD results.
    Re-checks games already marked "pending" (not yet played) but leaves
    already-resolved games (win/loss/push) untouched -- safe to re-run daily.
    Returns a small summary dict for logging.
    """
    data = json.loads(path.read_text())
    season, week = data["season"], data["week"]

    ungraded_exists = any(
        g.get("outcome") in (None, "pending") for g in data["games"]
    )
    if not ungraded_exists:
        return {"path": path.name, "status": "already fully graded", "changed": 0}

    print(f"Fetching {season} Week {week} results from CFBD...")
    cfbd_games = cfbd_get("/games", {"year": season, "week": week, "division": "fbs"})
    if not cfbd_games:
        return {"path": path.name, "status": "CFBD returned no games — skipping", "changed": 0}

    # Index by team-pair for matching against pick["matchup"] ("Away @ Home")
    results_by_pair: dict[tuple[str, str], dict] = {}
    for g in cfbd_games:
        home = g.get("homeTeam")
        away = g.get("awayTeam")
        if home and away:
            results_by_pair[(away, home)] = g

    changed = 0
    still_pending = 0
    for pick in data["games"]:
        if pick.get("outcome") not in (None, "pending"):
            continue  # already resolved, never re-grade a settled outcome

        away_team, home_team = [s.strip() for s in pick["matchup"].split(" @ ")]
        cfbd_game = results_by_pair.get((away_team, home_team))

        if not cfbd_game:
            pick["outcome"] = "pending"
            pick["grade_note"] = "no matching CFBD game found"
            still_pending += 1
            continue

        if not cfbd_game.get("completed"):
            pick["outcome"] = "pending"
            still_pending += 1
            continue

        home_score = cfbd_game.get("homePoints")
        away_score = cfbd_game.get("awayPoints")
        if home_score is None or away_score is None:
            # completed=true but scores missing is a genuine CFBD data gap,
            # not the same as "not played yet" -- flag distinctly.
            pick["outcome"] = "pending"
            pick["grade_note"] = "marked completed but score missing from CFBD"
            still_pending += 1
            continue

        result = grade_one_pick(pick, home_score, away_score)
        pick["home_score"] = home_score
        pick["away_score"] = away_score
        pick.update(result)
        changed += 1

    if changed and not dry_run:
        any_pending_left = any(g.get("outcome") == "pending" for g in data["games"])
        data["graded_at"] = datetime.now().isoformat(timespec="seconds")
        data["fully_graded"] = not any_pending_left
        path.write_text(json.dumps(data, indent=2))

    return {
        "path": path.name,
        "status": "dry-run, not written" if (changed and dry_run) else "graded",
        "changed": changed,
        "still_pending": still_pending,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description="Grade archived CFB picks against real results")
    p.add_argument("--season", type=int, default=None)
    p.add_argument("--week",   type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if not HISTORY_DIR.exists():
        print(f"No history directory at {HISTORY_DIR} — nothing to grade")
        return 0

    if args.season and args.week:
        files = [HISTORY_DIR / f"{args.season}_wk{args.week:02d}.json"]
        files = [f for f in files if f.exists()]
        if not files:
            print(f"No archive file found for {args.season} Week {args.week}")
            return 1
    else:
        files = sorted(HISTORY_DIR.glob("*.json"))

    if not files:
        print("No archived weeks found to grade.")
        return 0

    print(f"Checking {len(files)} archived week(s) for ungraded picks...")
    any_changed = False
    for path in files:
        summary = grade_history_file(path, args.dry_run)
        print(f"  {summary['path']}: {summary['status']} "
              f"(changed {summary.get('changed', 0)}, "
              f"still pending {summary.get('still_pending', 0)})")
        if summary.get("changed"):
            any_changed = True

    if not any_changed:
        print("\nNothing new to grade — all caught up.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
