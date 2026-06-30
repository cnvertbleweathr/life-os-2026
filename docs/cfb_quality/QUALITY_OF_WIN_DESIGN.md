# Quality-of-Win / Strength-of-Schedule System — Design Document

Full design across all four phases, for review before any SQL or Python is written. No code in this document — pure design, grounded in confirmed real columns already in the warehouse (no new data sources required for v1).

---

## Phase A — Static Preseason Quality Score

**Grain:** one row per `(team, season)`. Computed once, before the season starts, never updated.

**Two separate outputs per your decision:** `preseason_off_quality`, `preseason_def_quality` — both on a continuous scale (not yet decided whether 0-100 or 1-10; recommend 0-100 internally for precision, with a 1-10 *display* bucket derived from it, same pattern the model already uses for `model_score` buckets).

### Inputs (all confirmed real columns, all prior-season — same no-lookahead discipline as the rest of the model)

**Component 1 — Efficiency (from `cfbd.advanced_stats`, prior season):**
- Offense: `off_ppa`, `off_success_rate`, `off_explosiveness`
- Defense: `def_ppa`, `def_success_rate`, `def_havoc_total`

**Component 2 — Talent (from `cfbd.recruiting_rankings`, prior season; `cfbd.draft_production`, trailing window):**
- `recruiting_points` (composite recruiting score)
- `draft_picks` / `first_round_picks` (NFL pipeline strength — a team that consistently produces draft picks has a talent base that outlasts any single roster)

**Component 3 — Prior-year finish (from `cfbd.coaches`, prior season — confirmed real fields):**
- `wins` / `losses` → win percentage
- `postseason_rank` (proxy for "finished strong," including bowl/playoff performance — CFBD doesn't expose a clean "won conference championship" boolean, so `postseason_rank` is the best available stand-in: a team ranked highly at season's end has, by definition, had bowl-game or championship-level success)
- `srs` (CFBD's own Simple Rating System — already a margin-adjusted-for-opponent number, useful as a sanity cross-check against whatever this system computes independently)

### Formula (proposed, open to adjustment)

```
preseason_off_quality(team, season) =
    w1 * z_score(off_ppa, prior_season)
  + w2 * z_score(off_success_rate, prior_season)
  + w3 * z_score(off_explosiveness, prior_season)
  + w4 * z_score(recruiting_points, prior_season)
  + w5 * z_score(draft_picks_trailing_4yr, prior_season)
  + w6 * z_score(win_pct, prior_season)
  + w7 * z_score(postseason_rank_inverted, prior_season)  -- lower rank number = better, so inverted
```

Same structure for `preseason_def_quality`, swapping in `def_ppa`/`def_success_rate`/`def_havoc_total` for the efficiency component (talent and prior-finish components are shared, since they're not offense/defense-specific — recruiting and win/loss record reflect the whole program).

**z-scoring rationale:** every input is on a different scale (`off_ppa` is typically -0.5 to +0.5, `recruiting_points` is in the hundreds, `wins` is 0-13). Z-scoring each component within its season (mean 0, stdev 1, computed across all FBS teams that season) before blending makes the weights (`w1`...`w7`) actually meaningful and comparable, rather than implicitly letting whichever raw stat has the largest numeric range dominate.

**Open question for you:** what should `w1`...`w7` actually be? I don't think these should be guessed — Phase D's validation step (below) is exactly where you'd empirically test different weightings against what actually predicted ATS performance historically, rather than hand-picking weights up front. Proposed default for the first pass: equal weighting (all `w = 1/7`), purely as a neutral starting point to validate the *structure* before tuning the weights.

---

## Phase B — Quality-of-Win/Loss Formula

**Grain:** one row per completed game (joins to `main_marts.mart_cfbd_line_accuracy`, which already has real final scores and spreads for every historical game).

**Your stated formula basis:** actual result vs. market expectation (the spread), not opponent quality directly — since the spread already encodes the market's read of the quality gap between the two teams.

### Formula (proposed)

```
margin_vs_spread = actual_margin - (-spread)   -- already a real column in mart_cfbd_line_accuracy

quality_of_result(winning_team) =
    5.0  -- baseline "as expected" win
  + scale_factor * margin_vs_spread             -- beat the spread = above 5, missed it = below 5
  + small_adjustment_for_opponent_quality        -- secondary term, see below

quality_of_result(losing_team) = 10.0 - quality_of_result(winning_team)
```

This directly implements your "winner gets 6, loser gets complementary 4" example — the two numbers always sum to 10, by construction, so there's no ambiguity about whether a "quality win" for one team implies an inconsistent "quality loss" read for the other.

**The opponent-quality adjustment** (smaller term, not the primary driver per your answer): a team that beats the spread against a high-`preseason_off_quality`/`preseason_def_quality` opponent should get a slightly higher quality-of-result than the identical spread-beat against a weak opponent — even though the spread *already* priced in the opponent's quality, this term catches cases where the *model's own* opponent-quality read diverges from what the spread implied (which is itself a signal worth capturing, not double-counting).

**Open question for you:** what should `scale_factor` be, and should `quality_of_result` be capped (e.g., clamped to a 0-10 range so an absurd 50-point blowout doesn't produce a meaningless 47)? Proposed: yes, clamp to [0, 10], with diminishing returns on `margin_vs_spread` beyond some threshold (e.g., beating the spread by 20+ doesn't meaningfully mean "more quality" than beating it by 15 — both are blowouts).

---

## Phase C — Live Power Rating

**Grain:** one row per `(team, season, week)` — a time series, not a single value. This is the part that updates in-season.

### Mechanics
- Initialize: `live_power_rating(team, season, week=0) = preseason_off_quality(team, season)` (and a separate defensive live rating from `preseason_def_quality`) — exactly your design, the live rating *starts* at the static preseason number.
- Update after each week: `live_power_rating(team, season, week=N) = live_power_rating(team, season, week=N-1) + k * (quality_of_result(team, that week's game) - 5.0)`
  - The `(quality_of_result - 5.0)` term is zero for an exactly-as-expected result, positive for outperformance, negative for underperformance — so the live rating only moves when a team beats or misses expectations, not just from playing games.
  - `k` is a smoothing/learning-rate constant (small, e.g., 0.05-0.15) — controls how much one game's result can move the live rating. This is directly analogous to how Elo systems tune their K-factor, and should be empirically tuned in Phase D, not guessed.

### What this produces
A full week-by-week time series per team: "this team started the season rated at X based on hype, and by Week 8 had drifted to Y based on actual performance relative to expectation." The **gap between the live rating and the static preseason rating** at any point in the season is exactly the "overhyped vs underhyped" signal you described.

---

## Phase D — Validation (before any of this touches `score_game()`)

This is the step your third answer specifically asked for, and it's the part that actually determines whether any of the above is worth keeping.

### The empirical question
Does `(live_power_rating - preseason_quality)` — the over/underperformance gap — predict anything about a team's **future** ATS performance that isn't already captured by the existing signals (PPA gap, tier, recruiting, success rate)?

### How to test it, concretely
1. Compute the full Phase A/B/C pipeline retroactively for 2021-2025 (the same seasons everything else is validated against).
2. For every game in weeks 5+ of each season (early enough weeks won't have a meaningful live-rating drift yet), bucket games by the **sign and magnitude** of the underperformance/overperformance gap for the team about to play.
3. Check: do teams with a large positive gap (overperforming their hype) cover more often than the existing model would predict, going forward? Do teams with a large negative gap (underperforming, "buy low" candidates) behave the way the market might be sleeping on?
4. Critically — run this as a **standalone correlation/predictive-power check**, the same kind of diagnostic the external review recommended for the existing `len(edges) >= 4` correlation concern: does this new gap signal add *incremental* predictive value beyond what `off_ppa_gap`/`recruiting_gap`/tier already capture, or is it just another correlated restatement of the same underlying "team is good" fact?
5. Only if it clears that bar does it get proposed as a new rule inside `score_game()` — and even then, following the same ablation-and-document pattern the existing rules use (a rule that helps 3/4 seasons gets the same governance scrutiny SP+/havoc already got, not a free pass).

### What "passing" Phase D would look like
A genuine, out-of-sample (not the same seasons used to tune `scale_factor`/`k`/weights) improvement in ROI or cover rate when this signal is added — not just "the gap correlates with something," since correlation with anything is easy to find in a large enough feature space, and the whole point of tonight's audit was learning not to trust a clean-looking number without scrutinizing how it was produced.

---

## What I need from you before writing any SQL

1. **The `w1`...`w7` weighting question** in Phase A — equal-weight as a neutral starting point, or do you have a strong prior on which component should dominate (e.g., "prior-year talent should count more than prior-year record, since record can be noisy")?
2. **Confirm the "1-10" scale is purely a display/intuition layer**, and the actual stored values can be a more precise continuous score (0-100 or raw z-score sum) — or do you want the underlying stored value to literally be bounded 0-10?
3. **Phase D's scope** — do you want this built as a one-time analysis script (run it, look at the output, decide manually whether it's promising), or do you want it built as a repeatable validation harness from the start (so if you tune `scale_factor`/`k` later, you can re-run the same validation automatically)? Given the size of this project, I'd lean toward the one-time script first — building a full repeatable harness for a signal that might not even pass validation is premature investment.

Once these are settled, the build order is Phase A → confirm real output for teams you know → Phase B → Phase C → Phase D, each phase gated on the previous one actually producing sane, checkable output — same discipline as everything else tonight.
