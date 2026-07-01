#!/usr/bin/env python3
"""
cfb_quality_validation.py

Phase 0.2 — Stage 1 validation scaffold (skeleton).

Per design v5 (docs/cfb_quality/QUALITY_OF_WIN_DESIGN.md): this harness
answers "does X predict future football performance" — nothing about
betting markets or ATS results belongs here. That's Stage 2, gated on
Stage 1 passing, and explicitly NOT built yet (see design doc Phase D).

WHY THIS EXISTS BEFORE PHASE A: the design's build order puts the scaffold
before Phase A specifically so Phase A's real quality scores can be
checked against this harness the moment they exist, rather than building
all four phases first and validating at the end -- the same lesson
tonight's live-model audit already taught the hard way.

WHAT THIS SCRIPT CURRENTLY DOES: runs the scaffold against the simplest
possible baseline that needs nothing from Phase A -- does a team's own
prior-season off_ppa predict next season's off_ppa? This proves the
harness's data access, season-pairing, and metric-reporting machinery
work correctly BEFORE any quality-score logic exists to plug in. Once
Phase A produces preseason_off_rating_z/preseason_def_rating_z, those
get passed through the exact same `validate_predictor()` function --
no scaffold changes needed, by design.

CONFIG-DRIVEN, per design v5's "repeatable harness, not a one-off
script" requirement: every parameter that could be tuned is a function
argument, not a hardcoded constant, so future Phase A/C parameter sweeps
go through this same harness rather than spawning ad hoc variants.

Usage:
  python scripts/cfb_quality_validation.py                  # run the baseline self-test
  python scripts/cfb_quality_validation.py --target off_ppa  # test a different stat
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import pandas as pd

ROOT    = Path(__file__).resolve().parents[1]
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")


# ─────────────────────────────────────────────────────────────────────────────
# Season classification — Phase 0.3, read directly from the data contract
# rather than re-decided here. See docs/cfb_quality/CFB_QUALITY_DATA_CONTRACT.md
# finding #8 for the reasoning behind this exact split.
# ─────────────────────────────────────────────────────────────────────────────

SEASON_CLASSIFICATION = {
    2021: "previously_examined_dev",
    2022: "previously_examined_dev",
    2023: "previously_examined_dev",
    2024: "parameter_selection",
    2025: "parameter_selection",
    2026: "future_live_holdout",  # never touched by this script until Stage 2 is built and frozen
}

DEV_SEASONS               = [s for s, c in SEASON_CLASSIFICATION.items() if c == "previously_examined_dev"]
PARAMETER_SELECTION_SEASONS = [s for s, c in SEASON_CLASSIFICATION.items() if c == "parameter_selection"]
HOLDOUT_SEASONS            = [s for s, c in SEASON_CLASSIFICATION.items() if c == "future_live_holdout"]


def fetch_team_season_stat(con: duckdb.DuckDBPyConnection, stat_column: str) -> pd.DataFrame:
    """
    Pulls one column from cfbd.advanced_stats for every (team, season) row
    available. Generic by design -- this is the data-access layer every
    future Stage 1 predictor (including real Phase A quality scores, once
    they exist in their own mart) will reuse, not something specific to
    one baseline test.
    """
    df = con.execute(f"""
        SELECT team, season, {stat_column}
        FROM cfbd.advanced_stats
        WHERE {stat_column} IS NOT NULL
        ORDER BY team, season
    """).df()
    return df


def build_predictor_pairs(df: pd.DataFrame, stat_column: str, seasons: list[int]) -> pd.DataFrame:
    """
    For every team, pairs season N's value with season N+1's value --
    "does X this year predict X next year" is the trivial self-test;
    swapping in a real predictor column (e.g. preseason_off_rating_z)
    against a real target column (e.g. next season's actual off_ppa) is
    the same shape of join, just different column names. Restricted to
    the given season list so dev/parameter-selection/holdout splits are
    enforced at this layer, not left to the caller to remember.
    """
    df = df[df["season"].isin(seasons)]
    pairs = df.merge(
        df, on="team", suffixes=("_prior", "_next")
    )
    pairs = pairs[pairs["season_next"] == pairs["season_prior"] + 1]
    return pairs[["team", "season_prior", "season_next", f"{stat_column}_prior", f"{stat_column}_next"]]


def validate_predictor(pairs: pd.DataFrame, predictor_col: str, target_col: str) -> dict:
    """
    The core, reusable metric-reporting function. Every future Stage 1
    validation run -- including real preseason_quality vs future PPA,
    once Phase A exists -- calls this same function. Keeping this one
    function as the single source of truth for "how do we measure
    predictive power" is what makes the harness repeatable rather than
    a pile of one-off correlation checks.
    """
    if len(pairs) < 10:
        return {"n": len(pairs), "status": "insufficient_sample", "correlation": None}

    correlation = pairs[predictor_col].corr(pairs[target_col])

    return {
        "n":             len(pairs),
        "status":        "ok",
        "correlation":   round(float(correlation), 3) if correlation is not None else None,
        "predictor_mean": round(float(pairs[predictor_col].mean()), 4),
        "target_mean":    round(float(pairs[target_col].mean()), 4),
    }


def run_baseline_self_test(stat_column: str = "off_ppa") -> None:
    """
    Proves the scaffold works end-to-end using a trivial, already-known-
    to-be-reasonable baseline (a stat predicting its own next-season
    value) BEFORE any real quality score exists. If this baseline shows
    a sane, non-zero correlation, the harness's data access and pairing
    logic are trustworthy; if it shows something nonsensical (near-zero,
    or a sign that doesn't make sense), that's a scaffold bug to fix
    before Phase A ever touches this code, not a finding about football.
    """
    con = duckdb.connect(DB_PATH, read_only=True)
    df = fetch_team_season_stat(con, stat_column)
    con.close()

    print(f"Stage 1 scaffold self-test: does prior-season {stat_column} predict next-season {stat_column}?")
    print(f"{'='*70}")

    for label, seasons in [
        ("Dev seasons (2021-2023)",              DEV_SEASONS),
        ("Parameter-selection seasons (2024-2025)", PARAMETER_SELECTION_SEASONS),
    ]:
        pairs = build_predictor_pairs(df, stat_column, seasons + [s + 1 for s in seasons])
        result = validate_predictor(pairs, f"{stat_column}_prior", f"{stat_column}_next")
        print(f"\n{label}:")
        for k, v in result.items():
            print(f"  {k}: {v}")

    print(f"\n{'='*70}")
    print("BOUNDARY NOTE (not a bug, but worth being explicit): season pairs")
    print("near the dev/parameter-selection split (e.g. 2023 predictor -> 2024")
    print("target) cross that boundary. This is fine for a READ-ONLY")
    print("correlation check like this self-test -- no parameter is being")
    print("tuned against the result. It would NOT be fine for an actual")
    print("weight-fitting step (e.g. estimating beta_off/beta_def per design")
    print("v5) without explicit care about which season's data is allowed to")
    print("influence which fitted value. Future tuning code reusing this")
    print("scaffold's pairing logic must handle that distinction itself --")
    print("this harness does not currently enforce it beyond the dev vs.")
    print("holdout (2026) boundary.")
    print(f"{'='*70}")

    print(f"\nHOLDOUT SEASONS (2026): {HOLDOUT_SEASONS} — never queried by this self-test.")
    print("Confirms the harness respects the season split even when it would")
    print("be technically easy to peek (2026 data doesn't exist yet anyway,")
    print("but the season list itself enforces the boundary going forward).")
    print(f"{'='*70}")


def run_phase_a_validation() -> None:
    """
    The first real Stage 1 validation: does preseason_off_rating_z
    (Phase A's composite quality score) predict next-season off_ppa
    better than the raw prior-season off_ppa baseline?

    This is the question the scaffold was built to answer. If
    preseason_off_rating_z doesn't beat 0.40-0.43, the additional
    complexity of the talent/program and prior_results blocks isn't
    earning its keep and the design needs revisiting before Phase B.
    """
    con = duckdb.connect(DB_PATH, read_only=True)

    # Pull preseason_off_rating_z (the predictor) paired with next
    # season's actual off_ppa (the target). The quality score for
    # season N was built from season N-1 data, so it's already a
    # valid prior-season predictor of season N outcomes.
    df = con.execute("""
        SELECT
            q.team,
            q.season AS predictor_season,
            q.season + 1 AS target_season,
            q.preseason_off_rating_z AS predictor,
            a.off_ppa AS target
        FROM main_marts.mart_cfb_preseason_quality q
        JOIN cfbd.advanced_stats a
            ON a.team = q.team AND a.season = q.season
        WHERE q.preseason_off_rating_z IS NOT NULL
          AND a.off_ppa IS NOT NULL
    """).df()
    con.close()

    print("Phase A Stage 1 validation: does preseason_off_rating_z predict next-season off_ppa?")
    print("Baseline to beat: raw prior-season off_ppa -> next-season off_ppa = 0.43 (dev) / 0.40 (param-selection)")
    print(f"{'='*70}")

    for label, seasons in [
        ("Dev seasons (2021-2023)",               DEV_SEASONS),
        ("Parameter-selection seasons (2024-2025)", PARAMETER_SELECTION_SEASONS),
    ]:
        subset = df[df["predictor_season"].isin(seasons)]
        result = validate_predictor(subset, "predictor", "target")
        print(f"\n{label}:")
        for k, v in result.items():
            print(f"  {k}: {v}")

    print(f"\n{'='*70}")
    print("INTERPRETATION GUIDE:")
    print("  > 0.45: clearly beats the raw off_ppa baseline -- the extra inputs add value")
    print("  0.40-0.45: roughly matches baseline -- extra complexity not yet justified")
    print("  < 0.40: worse than baseline -- something in the composite is hurting signal")
    print(f"{'='*70}")


def run_phase_a_def_validation() -> None:
    """
    Defensive equivalent of run_phase_a_validation(). Tests whether
    preseason_def_rating_z predicts next-season def_ppa better than
    raw prior-season def_ppa alone.

    Note: def_ppa is stored as "points allowed per play" -- lower is
    better defense. So a NEGATIVE correlation between
    preseason_def_rating_z (higher = better defense) and next-season
    def_ppa (lower = better defense) would be the correct, expected
    direction here -- not a sign error.
    """
    con = duckdb.connect(DB_PATH, read_only=True)

    # Baseline: does raw def_ppa predict itself year-over-year?
    baseline_df = con.execute("""
        SELECT team, season, def_ppa
        FROM cfbd.advanced_stats
        WHERE def_ppa IS NOT NULL
    """).df()

    # Phase A composite vs next-year def_ppa
    df = con.execute("""
        SELECT
            q.team,
            q.season AS predictor_season,
            q.preseason_def_rating_z AS predictor,
            a.def_ppa AS target
        FROM main_marts.mart_cfb_preseason_quality q
        JOIN cfbd.advanced_stats a
            ON a.team = q.team AND a.season = q.season
        WHERE q.preseason_def_rating_z IS NOT NULL
          AND a.def_ppa IS NOT NULL
    """).df()
    con.close()

    print("Phase A Stage 1 defensive validation")
    print("preseason_def_rating_z vs next-season def_ppa")
    print("(Note: expected direction is NEGATIVE -- higher rating = better defense = lower def_ppa allowed)")
    print(f"{'='*70}")

    for label, seasons in [
        ("Dev seasons (2021-2023)",               DEV_SEASONS),
        ("Parameter-selection seasons (2024-2025)", PARAMETER_SELECTION_SEASONS),
    ]:
        # Baseline
        b_pairs = build_predictor_pairs(baseline_df, "def_ppa",
                                        seasons + [s + 1 for s in seasons])
        b_result = validate_predictor(b_pairs, "def_ppa_prior", "def_ppa_next")

        # Phase A composite
        subset = df[df["predictor_season"].isin(seasons)]
        result = validate_predictor(subset, "predictor", "target")

        print(f"\n{label}:")
        print(f"  Baseline (raw def_ppa -> next def_ppa): {b_result.get('correlation')}")
        print(f"  Phase A  (preseason_def_rating_z -> next def_ppa):")
        for k, v in result.items():
            print(f"    {k}: {v}")

    print(f"\n{'='*70}")


def run_phase_a_margin_validation() -> None:
    """
    Alternative Stage 1 target: future scoring margin instead of future
    off_ppa. The betting model cares about margins, not efficiency metrics
    -- if preseason_off_rating_z predicts actual scoring margins better
    than it predicts PPA, that's more directly useful signal.
    """
    con = duckdb.connect(DB_PATH, read_only=True)

    # Need team-season avg scoring margin -- compute from game results
    margin_df = con.execute("""
        SELECT
            home_team AS team,
            season,
            avg(home_score - away_score) AS avg_margin
        FROM main_marts.mart_cfbd_line_accuracy
        WHERE home_score IS NOT NULL AND away_score IS NOT NULL
          AND home_conference IN (
              'SEC', 'Big Ten', 'Big 12', 'ACC', 'Pac-12',
              'American Athletic', 'Mountain West', 'Conference USA',
              'Mid-American', 'Sun Belt', 'FBS Independents'
          )
        GROUP BY home_team, season
        UNION ALL
        SELECT
            away_team AS team,
            season,
            avg(away_score - home_score) AS avg_margin
        FROM main_marts.mart_cfbd_line_accuracy
        WHERE home_score IS NOT NULL AND away_score IS NOT NULL
          AND home_conference IN (
              'SEC', 'Big Ten', 'Big 12', 'ACC', 'Pac-12',
              'American Athletic', 'Mountain West', 'Conference USA',
              'Mid-American', 'Sun Belt', 'FBS Independents'
          )
        GROUP BY away_team, season
    """).df()

    # Collapse home + away into one margin per team-season
    margin_df = margin_df.groupby(["team", "season"])["avg_margin"].mean().reset_index()

    df = con.execute("""
        SELECT q.team, q.season AS predictor_season,
               q.preseason_off_rating_z AS predictor
        FROM main_marts.mart_cfb_preseason_quality q
        WHERE q.preseason_off_rating_z IS NOT NULL
    """).df()
    con.close()

    # Pair predictor_season N with actual margin in season N
    pairs = df.merge(margin_df, left_on=["team", "predictor_season"],
                     right_on=["team", "season"])

    print("Phase A Stage 1 (margin target): preseason_off_rating_z vs next-season scoring margin")
    print(f"{'='*70}")

    for label, seasons in [
        ("Dev seasons (2021-2023)",               DEV_SEASONS),
        ("Parameter-selection seasons (2024-2025)", PARAMETER_SELECTION_SEASONS),
    ]:
        subset = pairs[pairs["predictor_season"].isin(seasons)]
        result = validate_predictor(subset, "predictor", "avg_margin")
        print(f"\n{label}:")
        for k, v in result.items():
            print(f"  {k}: {v}")
    print(f"{'='*70}")


def main() -> int:
    p = argparse.ArgumentParser(description="Phase 0.2 Stage 1 validation scaffold")
    p.add_argument("--target", default="off_ppa",
                   help="Which cfbd.advanced_stats column to run the baseline self-test against")
    p.add_argument("--phase-a", action="store_true",
                   help="Run Phase A offensive validation (preseason_off_rating_z vs next-season off_ppa)")
    p.add_argument("--phase-a-def", action="store_true",
                   help="Run Phase A defensive validation (preseason_def_rating_z vs next-season def_ppa)")
    p.add_argument("--phase-a-margin", action="store_true",
                   help="Run Phase A margin validation (preseason_off_rating_z vs next-season scoring margin)")
    args = p.parse_args()

    if args.phase_a:
        run_phase_a_validation()
    elif args.phase_a_def:
        run_phase_a_def_validation()
    elif args.phase_a_margin:
        run_phase_a_margin_validation()
    else:
        run_baseline_self_test(args.target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
