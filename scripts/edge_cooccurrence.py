#!/usr/bin/env python3
"""
edge_cooccurrence.py

Two analyses the review required:

1. Edge co-occurrence matrix: how often do pairs of edges fire together
   in the same pick? If two edges co-occur 90% of the time they are
   not independent signals -- they're measuring the same thing.

2. Incremental ROI beyond PPA: for each rule, what's the cover rate
   of picks where that rule fires vs doesn't fire, among picks that
   already have a PPA edge? This answers whether the rule adds value
   beyond what PPA alone provides.

Reads from the live warehouse, re-scores all 2021-2025 qualifying games.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import duckdb
import pandas as pd
import numpy as np
from backtest_walk_forward import score_game, build_tiers

DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")
FBS = ('SEC','Big Ten','Big 12','ACC','Pac-12','American Athletic',
       'Mountain West','Conference USA','Mid-American','Sun Belt','FBS Independents')

# Canonical edge labels from score_game() -- map to display names
EDGE_DISPLAY = {
    "PPA_extreme":          "PPA extreme (>0.30)",
    "PPA_primary":          "PPA primary (0.15-0.30)",
    "underdog_edge":        "Underdog bonus",
    "talent_parity":        "Talent parity",
    "home_eff_beats_talent":"Home eff beats talent",
    "talent_confirms_home": "Talent confirms home",
    "away_eff_beats_talent":"Away eff beats talent",
    "talent_confirms_away": "Talent confirms away",
    "SR_parity":            "Success rate parity",
    "SR_confirms":          "SR confirms bet",
    "home_eff_beats_SR":    "Home eff beats SR",
    "away_eff_beats_SR":    "Away eff beats SR",
    "ret_high_home":        "Ret prod high (home)",
    "ret_slight_home":      "Ret prod slight (home)",
    "ret_high_away":        "Ret prod high (away)",
    "ret_slight_away":      "Ret prod slight (away)",
    "ELITE_tier":           "ELITE tier",
    "STRONG_tier":          "STRONG tier",
    "FADE_tier":            "FADE tier (penalty)",
    "STRONG_FADE_tier":     "STRONG FADE (penalty)",
    "conf_tailwind":        "Conference tailwind",
}

# Grouped by signal family for co-occurrence analysis
SIGNAL_FAMILIES = {
    "PPA":          {"PPA_extreme", "PPA_primary"},
    "Underdog":     {"underdog_edge"},
    "Talent":       {"talent_parity", "home_eff_beats_talent", "talent_confirms_home",
                     "away_eff_beats_talent", "talent_confirms_away"},
    "Success Rate": {"SR_parity", "SR_confirms", "home_eff_beats_SR", "away_eff_beats_SR"},
    "Returning":    {"ret_high_home", "ret_slight_home", "ret_high_away", "ret_slight_away"},
    "Tier":         {"ELITE_tier", "STRONG_tier", "FADE_tier", "STRONG_FADE_tier"},
    "Conference":   {"conf_tailwind"},
}


def load_and_score(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Load all qualifying 2021-2025 picks with edge lists."""
    df = con.execute("""
        SELECT m.game_id, m.season, m.week, m.home_team, m.away_team,
               m.spread, m.over_under, m.off_ppa_gap, m.def_ppa_gap,
               m.home_off_success_rate, m.away_off_success_rate,
               m.home_def_success_rate, m.away_def_success_rate,
               m.home_def_havoc, m.away_def_havoc,
               m.returning_production_gap, m.recruiting_gap,
               m.spread_covered, m.spread_push, m.spread_result,
               m.home_conference
        FROM main_marts.mart_cfbd_game_context m
        WHERE m.spread IS NOT NULL
          AND m.spread_result IN ('covered', 'missed', 'push')
          AND m.season BETWEEN 2021 AND 2025
          AND m.home_conference IN {}
    """.format(FBS)).df()

    df = (df.sort_values('off_ppa_gap', key=abs, ascending=False)
            .drop_duplicates(subset='game_id', keep='first')
            .reset_index(drop=True))

    rows = []
    for season in sorted(df['season'].unique()):
        sdf = df[df['season'] == season]
        tiers = build_tiers(con, season)
        sp_df = con.execute('SELECT team, season, rating FROM cfbd.sp_ratings').df()
        coaches_df = con.execute(
            'SELECT school AS team, year AS season, full_name AS coach FROM cfbd.coaches'
        ).df()
        prior_sp = {(r['team'], int(r['season'])): float(r['rating'])
                    for _, r in sp_df.iterrows()}
        curr = coaches_df[coaches_df['season'] == season]
        prev = coaches_df[coaches_df['season'] == season - 1]
        merged = curr.merge(prev, on='team', suffixes=('_c', '_p'))
        coach_changes = set(merged[merged['coach_c'] != merged['coach_p']]['team'])

        for _, row in sdf.iterrows():
            ms, edges, _ = score_game(row, tiers, coach_changes, prior_sp)
            if ms < 70 or len(edges) < 4 or bool(row['spread_push']):
                continue

            ppa_gap  = float(row.get('off_ppa_gap') or 0)
            bet_home = ppa_gap > 0
            win = bool(row['spread_covered']) if bet_home else not bool(row['spread_covered'])

            edge_set = set(edges)
            row_dict = {
                'game_id':    row['game_id'],
                'season':     season,
                'model_score': ms,
                'win':        int(win),
                'edges':      edges,
            }
            # Binary flags for each edge
            for edge in EDGE_DISPLAY:
                row_dict[f'has_{edge}'] = int(edge in edge_set)
            # Binary flags for each family
            for family, members in SIGNAL_FAMILIES.items():
                row_dict[f'family_{family}'] = int(bool(edge_set & members))

            rows.append(row_dict)

    return pd.DataFrame(rows)


def edge_cooccurrence_matrix(scored: pd.DataFrame) -> None:
    """Print pairwise co-occurrence rates between signal families."""
    print("=" * 65)
    print("SIGNAL FAMILY CO-OCCURRENCE MATRIX")
    print("(% of picks where BOTH families fire simultaneously)")
    print("=" * 65)

    families = list(SIGNAL_FAMILIES.keys())
    family_cols = [f'family_{f}' for f in families]

    # Compute pairwise co-occurrence
    n = len(scored)
    print(f"\nBase rates (% of {n} picks where family fires at all):")
    for fam in families:
        col = f'family_{fam}'
        rate = scored[col].mean() * 100
        print(f"  {fam:<16} {rate:>5.1f}%")

    print(f"\nCo-occurrence rates (row fires AND col fires):")
    header = f"{'':16}" + "".join(f"{f[:8]:>10}" for f in families)
    print(header)
    print("-" * (16 + 10 * len(families)))

    for fam_a in families:
        row_str = f"{fam_a:<16}"
        col_a = f'family_{fam_a}'
        for fam_b in families:
            col_b = f'family_{fam_b}'
            if fam_a == fam_b:
                rate = scored[col_a].mean() * 100
                row_str += f"  ({rate:>4.0f}%)"
            else:
                both = (scored[col_a] & scored[col_b]).mean() * 100
                row_str += f"  {both:>5.1f}%"
        print(row_str)

    print()
    print("High co-occurrence (>70%) suggests non-independent signals.")
    print("Low co-occurrence (<20%) suggests truly distinct signal families.")


def incremental_roi_beyond_ppa(scored: pd.DataFrame) -> None:
    """
    For each signal family, compare cover rate when:
    A) The family fires (in addition to PPA which always fires)
    B) The family does not fire (PPA fires alone or with other families)
    """
    print()
    print("=" * 65)
    print("INCREMENTAL VALUE BEYOND PPA")
    print("(All picks already have PPA -- does each additional family help?)")
    print("=" * 65)
    print()

    n_total = len(scored)
    total_cover = scored['win'].mean() * 100
    print(f"All {n_total} qualifying picks: {total_cover:.1f}% cover")
    print()

    print(f"{'Family':<16} {'Fires N':>8} {'Fires%':>8} {'No fire%':>10} {'Delta':>8}")
    print("-" * 52)

    for fam in list(SIGNAL_FAMILIES.keys()):
        if fam == "PPA":
            continue  # PPA always fires -- no meaningful split
        col = f'family_{fam}'
        fires    = scored[scored[col] == 1]
        no_fires = scored[scored[col] == 0]

        if len(fires) < 10 or len(no_fires) < 10:
            continue

        fires_cover    = fires['win'].mean() * 100
        no_fires_cover = no_fires['win'].mean() * 100
        delta = fires_cover - no_fires_cover

        direction = "✓ adds value" if delta > 3 else ("✗ hurts" if delta < -3 else "~ neutral")
        print(f"  {fam:<14} {len(fires):>8,} {fires_cover:>7.1f}% {no_fires_cover:>9.1f}% "
              f"{delta:>+7.1f}  {direction}")

    print()
    print("Delta = cover% when family fires minus cover% when it doesn't.")
    print("Positive delta: the family is associated with better outcomes.")
    print("Near-zero delta: the family adds no incremental value.")
    print("Negative delta: the family is associated with worse outcomes.")


def edge_trigger_frequency(scored: pd.DataFrame) -> None:
    """Show how often each individual edge fires."""
    print()
    print("=" * 65)
    print("INDIVIDUAL EDGE TRIGGER RATES")
    print(f"(Among {len(scored)} qualifying picks)")
    print("=" * 65)
    print()

    edge_stats = []
    for edge, display in EDGE_DISPLAY.items():
        col = f'has_{edge}'
        if col not in scored.columns:
            continue
        fires = scored[scored[col] == 1]
        n_fires = len(fires)
        if n_fires == 0:
            continue
        cover = fires['win'].mean() * 100
        no_fires = scored[scored[col] == 0]
        no_cover = no_fires['win'].mean() * 100 if len(no_fires) > 0 else float('nan')
        edge_stats.append({
            'edge':     display,
            'n_fires':  n_fires,
            'pct':      n_fires / len(scored) * 100,
            'cover':    cover,
            'no_cover': no_cover,
            'delta':    cover - no_cover,
        })

    edge_stats.sort(key=lambda x: -x['n_fires'])
    print(f"{'Edge':<32} {'N':>6} {'Rate':>6} {'Cover%':>8} {'NoCover%':>10} {'Delta':>8}")
    print("-" * 72)
    for e in edge_stats:
        print(f"  {e['edge']:<30} {e['n_fires']:>6,} {e['pct']:>5.0f}% "
              f"{e['cover']:>7.1f}% {e['no_cover']:>9.1f}% {e['delta']:>+7.1f}")


def run() -> None:
    con = duckdb.connect(DB_PATH, read_only=True)
    print("Loading and scoring all 2021-2025 qualifying picks...")
    scored = load_and_score(con)
    con.close()

    print(f"Loaded {len(scored):,} qualifying picks\n")

    edge_trigger_frequency(scored)
    edge_cooccurrence_matrix(scored)
    incremental_roi_beyond_ppa(scored)

    print()
    print("=" * 65)
    print("KEY QUESTIONS TO ANSWER FROM THIS OUTPUT")
    print("=" * 65)
    print("""
1. Do Talent and Success Rate co-occur >70%?
   If yes: the 4-edge minimum may be inflated by correlated signals.
   If no: they genuinely provide independent evidence.

2. Does the Underdog family show positive delta vs no-underdog picks?
   Expected: yes -- this is what the ablation already showed.
   If delta is near zero here: the family-level analysis dilutes the signal.

3. Does the Tier family show positive delta?
   If ELITE/STRONG tiers are driving the delta: good, tiers work.
   If FADE penalties are the primary contribution: the bonus side may be noise.

4. Any family with negative delta should be reviewed for potential removal.
   This is the incremental-value diagnostic the review specifically requested.
""")


if __name__ == "__main__":
    run()
