# Quality-of-Win / Strength-of-Schedule System — Design Document (v5, approved for Phase 0)

**Revision history:** v1 blended three concepts into one rating and had a defensive-sign bug. v2 fixed the sign bug and renamed concepts but, on inspection, never actually separated them at the formula level — `live_strength` was relabeled as "fundamental quality" while its update rule only ever read market residuals, which I verified by tracing the formula directly: a team improving in real football terms while running into tough lines would show declining "strength" under v2's math, a concrete contradiction. v2 also specified percentiles for Phase A's internal scale, then added z-score-style residuals on top in Phase C without reconciling units — verified numerically: a 90th→99th percentile move represents roughly 4x the standardized change of a 50th→60th move, so adding decayed residuals in percentile units would distort unevenly across the distribution. Both findings are adopted here, not just acknowledged, along with the rest of this round's corrections.

---

## Core principle, now actually enforced at the formula level (not just the naming level)

Three permanently separate time series, each driven by a **different input class**, never reading from each other's update mechanism:

1. **`live_football_strength`** — updates from real football performance (PPA, success rate, explosiveness, scoring-margin residual vs. the system's *own* prior expectation) — never touches the betting line.
2. **`market_outperformance_ema`** — updates only from `actual margin - market expected margin` — never touches play-level football stats.
3. **`preseason_quality`** — static, computed once, used as the Phase A anchor for `live_football_strength`. `market_outperformance_ema` initializes at zero — it measures only in-season market-relative performance and has no preseason equivalent to anchor to.

Comparisons (`live_football_strength - preseason_quality`, `market_outperformance_ema`, `live_football_strength - market_implied_strength`) happen only as read-time queries in Phase D, never as a write-time blend into a single stored number. This is the structural fix v2's wording implied but its math didn't deliver.

---

## Phase 0 — Data Contracts and Scaffold

Before any of Phase A is finalized, two things must be verified against the real warehouse, not assumed. **Output is a real artifact, not an informal investigation**: `CFB_QUALITY_DATA_CONTRACT.md`, recording available seasons, row counts by source/season, provider coverage, whether opening/closing lines are genuinely distinguishable, whether spreads and totals share a provider/timestamp, price/juice availability, game-level vs. season-level advanced-stat availability, garbage-time filtering availability, regulation-score availability, overtime representation, FCS naming/coverage, null percentages by feature, team-name canonicalization rules (directly relevant given tonight's substring-collision bug in the betting model itself), and known conference/subdivision anomalies. This gives every later phase a stable evidence base instead of letting code silently assume something Phase 0 never actually checked.

### 0.1 — Closing-line data verification
Check directly: does CFBD supply a true timestamped closing line distinct from opening, or only a single historical line value per provider? Can spread and total be pulled from the *same* provider and approximately the *same* timestamp? Is "consensus" an actual synchronized snapshot or a blended artifact? If true closing data isn't available, every downstream field gets named honestly: `historical_reference_line`, `historical_reference_total`, `is_verified_close = false` — never labeled "closing" unless verified as such.

### 0.2 — Stage 1 validation scaffold (skeleton only, before Phase A is finalized)
A minimal harness that can already score "does X predict future football performance" for trivial baselines (e.g., does last season's raw PPA predict this season's PPA at all) — so the moment Phase A produces real numbers, they can be checked against this scaffold immediately, rather than building all four phases first and validating at the end.

### 0.3 — Holdout season classification (new this round, verified as a distinct concern before adopting)

**Traced through directly rather than accepted on authority:** the existing betting model's weights and thresholds were set/validated using 2021-2025 walk-forward backtests — confirmed fact, visible in `score_game()`'s own rule comments (e.g., "ablation: -6.0% ROI — strongest confirmation signal") throughout tonight's audit. The new quality system hasn't been fitted to anything yet, but that's not the actual concern here: whoever designs this system's formulas (this session, and any future one) has already been extensively exposed to how those same seasons played out — season-by-season backtest tables, which signals worked, the 224-94/+34.5% ROI record, all quoted and analyzed multiple times tonight. That's a real, distinct contamination risk from the model-tuning contamination already caught twice in this design's earlier rounds — it's not "did the algorithm see the test set," it's "did the people designing the algorithm already have detailed knowledge of what happened in it." Confirmed as legitimate, not overcautious, before adopting.

Phase 0's data-contract report must classify every available season as one of: `previously_examined` (any season whose results have been extensively analyzed in this project, which as of tonight includes essentially all of 2021-2025), `development_eligible`, `parameter_selection_eligible`, `historically_untouched` (if any genuinely qualify), or `future_live_holdout`. A defensible setup likely uses the already-examined seasons for development/selection only, and reserves either a genuinely untouched recent historical season (if one exists) or **2026 itself as a prospective live holdout** — not a season simply labeled "locked" because this particular script hasn't processed it yet, when its outcomes are already well known from other analysis.

---

## Phase A — Static Preseason Quality

**Grain:** one row per `(team, season)`.

**Outputs:**
- `preseason_off_rating_z`, `preseason_def_rating_z` — standardized units, what every later calculation actually uses
- `preseason_off_percentile`, `preseason_def_percentile` — interpretability-only fields, for humans reading the table, never fed back into modeling
- `preseason_quality_uncertainty` — confirmed in scope for v1

**Scaling:** compute season percentiles for inspection, but convert to z-units before any modeling step touches them. **Corrected conversion, per this round's review:** use a rank-based transform (`p = (rank - 0.5) / n`, then `z = inverse_normal_cdf(p)`) rather than naive percentile-to-CDF conversion, which allows exact 0 or 1 percentiles and produces undefined/infinite z-values at the endpoints. Robust standardized values (`(value - median) / MAD`) remain the alternative for skewed inputs. Percentile and z-score fields are never mixed in a calculation.

**Block structure, locked to the simplest defensible baseline:**
```
preseason_quality = (1/3) * efficiency_block + (1/3) * talent_program_block + (1/3) * prior_results_block
```
Equal weighting within each block, equal weighting across blocks — not tuned, not chosen by inspecting ATS results. A ridge-regression-based alternative is the designated **second benchmark** in Stage 1, compared against this simple baseline, not used to replace it without evidence.

**Continuity block** affects `preseason_quality_uncertainty` only, never the quality mean directly — confirmed unchanged from v2, and now explicitly required to actually do something downstream (see Phase C uncertainty-coupling below) rather than sit as inert metadata. Uses **team-level returning production**, not the matchup-level `returning_production_gap` field that exists elsewhere in the warehouse — a real, specific correction, since the gap field is relative to an opponent and isn't meaningful for a single team's own continuity read.

**Validation target (Stage 1, never ATS):** does `preseason_quality` predict the team's own future opponent-adjusted efficiency or scoring margin? Confirmed unchanged from v2 — this was already correct and survived both review rounds.

---

## Phase B — Game-Level Result Decomposition

**Grain:** one row per `(team, game)` — the safest underlying grain, per the corrected temporal-handling section below, with a weekly mart selecting the latest available rating as of each week's end, rather than week itself being the storage grain.

### Honest field naming (corrected from v2's "offensive/defensive residual" framing)

The market-implied-points algebra (verified algebraically, unchanged from v2) produces **scoring** residuals, not pure offensive/defensive performance — points can come from defensive or special-teams scores, turnovers creating short fields, pace effects. v2 called this offense/defense; that overclaims what the math actually isolates. Renamed:

```
points_for_residual       (was: home_off_residual)
points_against_residual   (was: home_def_residual)
scoring_performance_rating
scoring_prevention_rating
```

These remain useful as a **scoring-result layer**, kept distinct from true unit-level football performance. The more rigorous offense/defense read — and the one that actually drives `live_football_strength` per the corrected Phase C below — comes from play-level data already in the warehouse: offensive PPA, defensive PPA, success rate, explosiveness, ideally with garbage-time filtering if that's available from CFBD.

### Result score (market surprise, unchanged from v2, still correctly separate)
```
home_result_score = 5 + 5 * tanh(home_residual / scale)
away_result_score = 10 - home_result_score
```
`scale` empirically estimated from historical spread-error dispersion, prior seasons only — unchanged.

### Line provenance, made strict
Spread and total used in the same decomposition must come from the **same provider, same approximate timestamp** — never DraftKings spread combined with a consensus total from a different snapshot. Every row stores `line_provider`, `line_timestamp`, `is_verified_close`. If Phase 0.1 finds true closing data isn't available, this entire decomposition is computed against `historical_reference_line`/`total` instead, labeled honestly as such.

### Opponent quality — confirmed unchanged
`opponent_pregame_quality` stored separately, frozen at the value known before the game, never the opponent's final-season strength. This was already correct in v2 and survived this round.

---

## Phase C — Two Independent Time Series (corrected from v2's single blended `live_strength`)

**Grain:** one row per `(team, game)` — confirmed corrected from "per week," per the temporal-handling fix below. A weekly view is derived by selecting the latest row available as of each week's end.

### Series 1 — `live_football_strength`

**Formally defined per this round's review, replacing the previously undefined `standardized_football_residual_t` placeholder:**

```
off_performance_residual = mean(
    standardized_game_off_ppa_residual,
    standardized_game_off_success_rate_residual,
    standardized_game_off_explosiveness_residual
)
def_performance_residual = mean(
    -standardized_game_def_ppa_residual,        -- sign-reversed, same reasoning as Phase A
    -standardized_game_def_success_rate_residual,
     standardized_game_def_havoc_residual
)
```
Each game-level residual is computed relative to a **pregame expectation**: `team's pregame unit rating` vs. `opponent's pregame opposing-unit rating`, adjusted for location. Whether scoring-margin residual is included as a secondary confirmation alongside this play-level block, or excluded entirely to avoid double-counting what PPA/success-rate already express, is an open implementation choice to resolve during Phase C build — not decided here, flagged explicitly rather than silently picked.

Garbage-time filtering, opponent-adjustment method, and missing-component handling (a game lacking explosiveness data, for instance) are Phase 0 data-contract questions — resolved there, not assumed here.

```
football_delta_t = rho_f * football_delta_(t-1) + k_f * off_performance_residual_t   (separately for defense)
live_football_strength_off(t) = preseason_off_rating_z + football_delta_t
```
The betting market never enters this series's update rule, by construction — this is the structural enforcement v2's wording implied but its formula didn't deliver, now actually true at the formula level.

### Series 2 — `market_outperformance_ema`

```
market_delta_t = rho_m * market_delta_(t-1) + k_m * standardized_market_residual_t
market_outperformance_ema(t) = market_delta_t   -- initializes at zero, no preseason anchor
```
**Corrected input, per this round's review:** the EMA is driven by the **raw standardized signed spread residual** (`home_residual` from Phase B, standardized), not the 0-10 `tanh`-transformed `result_score`. Layering one nonlinear transform (tanh) inside an already-decayed process loses directional precision around zero and makes the series harder to interpret statistically. The 0-10 result score remains useful for UI/résumé display, but is never fed into this series's update.

### Composite team strength — formally defined (was previously referenced but never specified)

Offense and defense ratings stay separate throughout Phase A and Phase C, but `opponent_pregame_quality`, `sos_to_date`, and similar fields need a single overall-strength number. Defined as an **expected-margin-style combination**, not a naive average of two z-scores with potentially different units:
```
expected_neutral_margin_vs_average = offense_points_above_average + defense_points_better_than_average
```
A simpler `overall_strength_z = 0.5 * live_off_rating_z + 0.5 * live_def_rating_z` baseline is acceptable for early Phase 0/A inspection work, but the points-above-average formulation is the one actually used wherever this composite feeds a real comparison (SOS, opponent quality, Stage 2 features) — averaging z-scores whose units don't cleanly translate into expected scoring margin risks the same kind of unit-mismatch error already found and fixed once in this design (the percentile/z-score inconsistency).

**Implementation ticket (resolve during Phase 0/A, not yet defined here):** the conversion from a standardized rating difference to expected points isn't specified. Estimate `expected_points_component = beta * rating_z` with `beta_off`/`beta_def` fit on development seasons only, then frozen — do not use the points-based composite anywhere until both betas are estimated and locked. The simple z-score average remains the inspection-only baseline until then.

### Uncertainty now actively affects updates, not just stored as metadata
```
effective_k = base_k * uncertainty_multiplier(games_played, preseason_uncertainty) * early_season_multiplier(week)
effective_k = clip(effective_k, k_min, k_max)
```
**Explicit clamp added per this round** — without it, a high-uncertainty team early in the season could receive an unintentionally extreme update when multipliers compound. `rho` decays **per game**, not per calendar week — already implied by the bye-week handling below (rating carries forward unchanged through a bye), now stated explicitly rather than left implicit.
A team with high preseason uncertainty (new coach, low returning production) gets a **larger** early-season learning rate — its rating should move faster once real evidence arrives, since the preseason anchor was less trustworthy to begin with. `uncertainty_t` itself declines as `games_played`/`data_completeness` accumulate. **Expanded scope per this round:** uncertainty now also reflects missing input blocks, number of prior-season games available, FCS/transition-season data, recruiting/draft-history reliability, subdivision/conference changes, and whether any feature was imputed — not just roster continuity. `preseason_quality_uncertainty` represents both football continuity and data reliability.

### Comparisons, computed at read time only
```
strength_vs_hype = live_football_strength - preseason_quality
market_trend     = market_outperformance_ema
```
**`market_implied_strength` / `strength_vs_market` are explicitly out of v1 scope, not just "not yet defined."** A single posted spread only gives the market's expected *difference* between two teams, not an absolute strength rating for either one — deriving a true market-implied team rating requires a network-style rating procedure solved across the full schedule with regularization and a normalization constraint, which is its own subproject. Removed from required v1 outputs rather than left as an undefined placeholder that implies it's coming soon.

---

## Phase D — Validation

### Two-stage test, now with a locked holdout (corrected from v2's walk-forward-only design)

**Three layers, not two:**
1. **Development/training seasons** — free exploration
2. **Parameter-selection seasons** — where `rho`, `k`, `scale`, block weights, thresholds actually get tuned
3. **Locked final holdout season(s)** — touched exactly once, after every parameter above is frozen.

**Corrected procedure, per a confirmed contradiction in the prior draft:** the earlier wording ("Stage 2 only after Stage 1 passes on the locked holdout") makes running Stage 2 conditional on having already observed Stage 1's holdout result — which means the holdout informed a decision (whether to proceed), making it no longer a one-shot evaluation. Verified by tracing the logic directly: this is the same model-selection-contamination failure mode the locked holdout exists to prevent, just relocated to a different decision point. Fixed: on development/parameter-selection seasons only, establish that Stage 1 works and freeze the entire pipeline — every block weight, `rho`, `k`, `scale`, threshold, and feature-inclusion decision. Pre-register all Stage 1 *and* Stage 2 metrics before touching the holdout. Run both stages exactly once on the locked holdout. Report everything, regardless of whether either stage's result is favorable. No re-tuning, and no decision to skip Stage 2, based on what the holdout shows. **Primary outcome metrics now include continuous margin-vs-spread and closing-line value, not just binary win/loss** — a team missing the spread by half a point and one missing by 28 points are meaningfully different signals that a binary win/loss outcome discards. Plus: confidence intervals, team/season block bootstrap, parameter sensitivity, feature stability by season, a multiple-testing log (given how many parameter combinations this harness can run, tracking how many were tried matters for honestly interpreting any "significant" result), and ROI under -110/-115/adverse-line assumptions.

### Repeatable harness — confirmed unchanged, correctly reversed from v1's one-off-script lean in the prior round.

---

## Quality-of-result and strength-of-schedule — now genuinely built (the actual original ask, missing from v2)

v2 renamed "quality of win" to "spread residual" — correctly, since margin-vs-spread measures market surprise, not win impressiveness — but in doing so, never actually built a strength-of-schedule or résumé-quality output, which was the real original request. Added back explicitly, as its own concept, kept separate from the predictive machinery above:

### Predictive schedule strength (pregame-safe, usable in Phase D Stage 2 and eventually `score_game()`)
```
sos_to_date = weighted average of opponent_pregame_quality across games played so far
offensive_sos_to_date, defensive_sos_to_date, recent_sos, next_4_games_sos
```
Accounts for home/away/neutral, FCS opponents, and number of games played (a 2-game SOS read is noisier than an 8-game one — `data_completeness` from Phase A's uncertainty framework applies here too).

**Snapshot semantics, made precise per this round's review (previously ambiguous):**
- `sos_to_date` uses each completed opponent's rating **as it existed immediately before that matchup** — not their current rating, not their final-season rating. This answers "how difficult did the schedule appear at the time each game was played," and is the version used in any predictive feature.
- A separate `sos_to_date_revalued` (opponents revalued using their *current* ratings) may be useful descriptively, but must never replace the frozen pregame version in predictive testing — keeping both avoids quietly mixing the two questions.
- `next_4_games_sos` freezes each future opponent's rating **as of the query timestamp**, not the rating that opponent will actually have immediately before the future matchup (which isn't knowable yet). Every SOS row stores `rating_as_of`/`schedule_snapshot_as_of` explicitly.
- **Opponent quality and venue difficulty are stored as two separate fields** (`opponent_strength_sos`, `venue_adjusted_schedule_difficulty`), not combined into one number — a tough opponent at home and a tough opponent on the road are related but distinct difficulty concepts, and collapsing them loses interpretability.

**Implementation ticket (resolve before building these marts, several terms above were intentionally left abstract):** for v1, prefer the simplest defensible version of each — tune or replace only after Stage 1/2 validation, not before:
```
opponent_strength_sos = unweighted mean of frozen opponent pregame strength   -- not a more complex weighting, for v1
result_quality_as_played = opponent_pregame_strength + fixed_venue_adjustment + c * tanh(actual_margin / margin_scale)
```
Still to specify explicitly before implementation: whether `sos_to_date` weights every game equally (the v1 default above) or recency-weights; how FCS opponents are represented in an SOS average; the exact home/away/neutral adjustment values; and whether `recent_sos` means last 3 games, last 4, or an exponentially weighted window. None of these block Phase 0 — they're acceptance criteria for the SOS/result-quality marts specifically, listed here so they aren't silently improvised during implementation.

```
result_quality_as_played = opponent_pregame_strength + location_adjustment + bounded_actual_margin_component
```
**Corrected naming and temporal contract, per a confirmed leakage error in the prior draft**: this was previously called `result_quality_pregame` and described as using "only information known entering the game." That was false — `bounded_actual_margin_component` requires the actual game result, which by definition isn't known before kickoff. Verified directly: the formula and the claim about the formula contradicted each other. Opponent strength and location are frozen at pregame values; the actual margin becomes available only after completion. The resulting score is safe to use as an input for *future* games, but is never a feature for the game that produced it.

### Retrospective résumé quality (display-only, never a feature)
```
result_quality_final, opponent_final_quality
```
Computed only after a season concludes, using final opponent strength. Powers UI displays like "this win aged well, the opponent finished top-15." **Must never flow backward into any pregame-facing feature** — confirmed and reinforced from both prior rounds; this is the one rule that's been consistent across all three design versions and is now stated with maximum explicitness given how easy this kind of leakage is to introduce accidentally.

---

## Temporal handling — now explicitly defined (was a list of open questions in v2)

**Grain changed from team-season-week to team-game**, per this round's specific correction — the safest underlying grain, with weekly views derived by selecting the latest available rating as of each week's end. This directly resolves most of the ambiguity:

- **Pregame vs. postgame**: every game-row stores both `pregame_live_rating` and `postgame_live_rating` explicitly — no ambiguity about which value a "Week 5" reference means.
- **Byes**: no game-row is created for a bye week; the most recent `postgame_live_rating` simply carries forward unchanged into the following week's view.
- **Multiple games in one "week" / rescheduled games**: handled naturally by the team-game grain — there's no assumption of exactly one game per week baked into the storage model.
- **Conference championships and bowls**: treated as normal sequential game-rows, same update mechanism, with `is_postseason` flagged for filtering in analysis if a future version wants to treat them differently (e.g., backup-player-heavy bowl games behaving differently from regular-season games).
- **Overtime**: flagged (`overtime_flag`) and, per this round's specific addition, has a **defined modeling choice, not just a flag**: for spread grading purposes, overtime counts normally (sportsbooks grade it that way). For team-strength updates, regulation-only scores are preferred when available; if not separable, the scoring residual is winsorized/capped rather than left unbounded, and multi-overtime games are downweighted in the update. Stage 1 validation runs with and without overtime games included, as an explicit ablation, not an assumption.

---

## Build order (corrected, scaffold-first)

1. Phase 0 — verify line data contracts, stand up the Stage 1 scaffold skeleton
2. Phase A — preseason quality, validated against future football performance the moment it exists
3. Phase B — game-level decomposition (honestly named scoring residuals + result score)
4. Build `live_football_strength` and `market_outperformance_ema` as genuinely separate series (not Phase C as a single step — this is the structural fix, worth calling out as its own checkpoint)
5. After Stage 1 passes on development and parameter-selection seasons, freeze the full pipeline and pre-register all Stage 1 and Stage 2 metrics; then run Stage 1 and Stage 2 together exactly once on the locked holdout, reporting both regardless of outcome
6. Add the separate quality-of-result and SOS marts
7. Only then — and only if Stage 2 shows real incremental value — consider integration with `score_game()`, through the same ablation-and-document governance every existing rule already goes through

**Approved for Phase 0 implementation**, across four independent review rounds, the last three finding zero remaining foundational architecture problems — only specification details and empirical questions, which is exactly what Phase 0 exists to resolve. Phase 0 should produce:
- `CFB_QUALITY_DATA_CONTRACT.md` (source/feature coverage tables, line-provider and timestamp findings)
- The Stage 1 baseline harness skeleton
- A proposed historical split with a genuinely defensible holdout (per 0.3 — not a season merely unprocessed by this script, but one whose outcomes aren't already extensively known from other analysis)
- Explicit unresolved-formula tickets for composite strength (`beta_off`/`beta_def`), SOS (`recent_sos` window, FCS handling, venue adjustment values), result quality, and the adaptive update rate clamp (`k_min`/`k_max`) — each listed above, none silently improvised during implementation.
