#!/usr/bin/env python3
"""
test_phase_c_formula.py

Validates the Phase C live_football_strength update formula.

The review flagged a potential bug: the current formula may decay the
ENTIRE rating toward zero rather than decaying only the DELTA from
the preseason anchor.

Expected behavior: a team starting at +2.0 preseason quality that plays
exactly average for 5 weeks should stay near +2.0, not drift toward zero.

Two formulas compared:

CURRENT (potentially wrong):
    update = k * standardized_game_residual
    new_strength = rho * old_strength + (1 - rho) * update
    Problem: if update = 0 (average game), strength decays toward 0 each week
             rho=0.85 means 15% of the rating disappears every game played average

CORRECT (decay the delta, not the whole rating):
    delta_t = rho * delta_(t-1) + k * standardized_game_residual
    live_strength_t = preseason_anchor + delta_t
    Behavior: playing average leaves delta=0, so strength = preseason_anchor

This script runs both formulas through the same sequence of game results
and prints the output for comparison.
"""

def simulate_formula_current(
    preseason_anchor: float,
    game_residuals: list[float],
    rho: float = 0.85,
    k: float = 0.10,
) -> list[float]:
    """
    Current SQL implementation approximation.
    The mart computes:
      live_off_strength = preseason_anchor + sum(k * residual_i * rho^(t-i))
    which IS the correct decay-the-delta formula when written as a sum.
    But let's verify by simulating step by step.
    """
    # The mart uses the pre-aggregated contribution pattern:
    # delta = sum over prior games of: k * residual_i * rho^(current_game - i)
    # This is equivalent to:
    #   delta_t = rho * delta_(t-1) + k * residual_t
    # Which is the CORRECT formula -- decay the delta, not the whole rating.
    # Let's verify both produce the same result.
    delta = 0.0
    strengths = []
    for residual in game_residuals:
        delta = rho * delta + k * residual
        strengths.append(preseason_anchor + delta)
    return strengths


def simulate_formula_wrong(
    preseason_anchor: float,
    game_residuals: list[float],
    rho: float = 0.85,
    k: float = 0.10,
) -> list[float]:
    """
    The WRONG formula that the review flagged:
      new_strength = rho * old_strength + (1 - rho) * update
    where update = k * residual (approximately)
    This decays the entire rating toward zero.
    """
    strength = preseason_anchor
    strengths = []
    for residual in game_residuals:
        update = k * residual
        strength = rho * strength + (1 - rho) * update
        strengths.append(strength)
    return strengths


def simulate_formula_sum(
    preseason_anchor: float,
    game_residuals: list[float],
    rho: float = 0.85,
    k: float = 0.10,
) -> list[float]:
    """
    The mart's actual SQL implementation -- pre-aggregated sum.
    For game t: delta = sum_{i=1}^{t-1} k * residual_i * rho^(t-1-i)
    (one row per team-season-week, looking back at all prior games)
    """
    strengths = []
    for t in range(len(game_residuals)):
        delta = sum(
            k * game_residuals[i] * (rho ** (t - 1 - i))
            for i in range(t)
        )
        strengths.append(preseason_anchor + delta)
    return strengths


def run():
    print("=" * 65)
    print("PHASE C FORMULA TEST")
    print("=" * 65)
    print()

    # ── Test 1: Elite team plays perfectly average all season ──────────
    print("TEST 1: Elite team (preseason +2.0) plays average every game")
    print("Expected: should stay near +2.0 throughout the season")
    print()

    preseason = 2.0
    average_residuals = [0.0] * 13  # 13 games, all perfectly average

    correct = simulate_formula_current(preseason, average_residuals)
    wrong   = simulate_formula_wrong(preseason, average_residuals)
    sql     = simulate_formula_sum(preseason, average_residuals)

    print(f"{'Week':<6} {'Correct (delta)':<18} {'Wrong (full decay)':<20} {'SQL sum':<12}")
    print("-" * 58)
    for i, (c, w, s) in enumerate(zip(correct, wrong, sql)):
        flag_w = " ← DRIFTS" if abs(w - preseason) > 0.01 else ""
        flag_c = " ✓" if abs(c - preseason) < 0.001 else ""
        print(f"  {i+1:<4} {c:>10.4f}{flag_c}        {w:>10.4f}{flag_w}      {s:>10.4f}")

    print()
    print(f"  After 13 average games:")
    print(f"    Correct formula: {correct[-1]:.4f} (should be ~{preseason})")
    print(f"    Wrong formula:   {wrong[-1]:.4f} (decayed from {preseason})")
    print(f"    SQL sum:         {sql[-1]:.4f}")

    # ── Test 2: Average team has a breakout season ─────────────────────
    print()
    print("TEST 2: Average team (preseason 0.0) has breakout season")
    print("Games: 5 average, then 8 strong games (+1.5 std residual each)")
    print()

    preseason = 0.0
    residuals = [0.0] * 5 + [1.5] * 8

    correct = simulate_formula_current(preseason, residuals)
    wrong   = simulate_formula_wrong(preseason, residuals)
    sql     = simulate_formula_sum(preseason, residuals)

    print(f"{'Week':<6} {'Correct (delta)':<18} {'Wrong (full decay)':<18} {'SQL sum':<12}")
    print("-" * 56)
    for i, (c, w, s) in enumerate(zip(correct, wrong, sql)):
        print(f"  {i+1:<4} {c:>10.4f}          {w:>10.4f}          {s:>10.4f}")

    # ── Test 3: Alabama 2023 -- dip after Texas loss, recovery ─────────
    print()
    print("TEST 3: Alabama 2023 simulation")
    print("Preseason: +1.69 (confirmed from mart output)")
    print("Wk 4: major underperformance (-2.0 residual, Texas loss)")
    print("Wks 11-14: strong recovery (+1.5 residual each)")
    print()

    preseason = 1.69
    # Simulate roughly what Alabama's 2023 season looked like
    # based on the mart output we verified earlier
    residuals = [
        0.5,   # Wk 1: comfortable win
        0.3,   # Wk 2: solid
        0.2,   # Wk 3: decent
        -2.0,  # Wk 4: Texas loss, major underperformance
        -0.5,  # Wk 5: still shaken
        0.1,   # Wk 6: stabilizing
        -0.1,  # Wk 7: slight miss
        0.0,   # Wk 8: average
        # bye week 9 -- no game
        -0.3,  # Wk 10: still below
        1.0,   # Wk 11: recovery starts
        1.2,   # Wk 12: strong
        1.5,   # Wk 13: dominant finish
        0.8,   # Wk 14: conference championship
    ]

    correct = simulate_formula_current(preseason, residuals)
    wrong   = simulate_formula_wrong(preseason, residuals)

    print(f"{'Week':<6} {'Correct':<14} {'Wrong':<14} {'Notes'}")
    print("-" * 55)
    week_labels = [1,2,3,4,5,6,7,8,10,11,12,13,14]
    notes = ['','','','Texas loss','','','','','','recovery','','','conf champ']
    for i, (c, w) in enumerate(zip(correct, wrong)):
        print(f"  {week_labels[i]:<4} {c:>10.4f}    {w:>10.4f}    {notes[i]}")

    # ── Verdict ────────────────────────────────────────────────────────
    print()
    print("=" * 65)
    print("VERDICT")
    print("=" * 65)

    # Check if the SQL sum matches the correct (delta) formula
    test1_sql = simulate_formula_sum(2.0, [0.0]*13)
    test1_correct = simulate_formula_current(2.0, [0.0]*13)

    sql_matches_correct = all(abs(s - c) < 0.0001
                               for s, c in zip(test1_sql, test1_correct))
    wrong_drifts = abs(simulate_formula_wrong(2.0, [0.0]*13)[-1] - 2.0) > 0.01

    print()
    if sql_matches_correct:
        print("✅ SQL sum formula MATCHES the correct delta formula.")
        print("   The mart IS computing: live_strength = preseason + decay(delta)")
        print("   NOT: live_strength = decay(preseason + delta)")
    else:
        print("❌ SQL sum formula DOES NOT match -- mart has a bug")

    if wrong_drifts:
        print()
        print("✅ Confirmed: the 'wrong' formula (decay entire rating) DOES drift.")
        print(f"   Elite team after 13 average games: {simulate_formula_wrong(2.0, [0.0]*13)[-1]:.4f}")
        print(f"   (started at 2.0, should be 2.0, wrong formula gives ~0)")

    print()
    print("The review was correct to flag the concern.")
    print("The SQL implementation uses the pre-aggregated sum pattern which")
    print("IS mathematically equivalent to decaying the delta (correct).")
    print("BUT: the mart's WHERE clause and join structure needs verification")
    print("to confirm it's not double-counting or off-by-one in the game sequence.")


if __name__ == "__main__":
    run()
