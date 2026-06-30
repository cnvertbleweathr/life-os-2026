# CFB_QUALITY_DATA_CONTRACT.md

Phase 0 output artifact for the Quality-of-Win/Strength-of-Schedule system (design v5). Every finding below was verified against the real CFBD API or the real warehouse — none are assumed or inferred from documentation. Where a finding has a direct consequence for the design, that consequence is stated explicitly.

---

## 1. Line timestamp data — does NOT exist

**Verified directly against the raw `/lines` API response** (Temple @ Miami, 2023 Wk4, queried live): there is no timestamp field anywhere in the response — not at the game level, not per-line. No `lineUpdatedDate`, no snapshot time, nothing.

**Consequence:** the design's `line_timestamp` field cannot be populated from this endpoint, for any historical season. `is_verified_close = false` is required **unconditionally** for every historical row. Fields must be named `historical_reference_line`/`historical_reference_total`, never "closing," anywhere in this system.

## 2. Opening-line (`spreadOpen`/`overUnderOpen`) coverage — sparse before 2025

**Verified via direct count across all five seasons, Week 1 sample:**

| Season | Games w/ lines | Line-rows | `spreadOpen` populated | Coverage |
|---|---|---|---|---|
| 2021 | 89 | 353 | 85 | 24% |
| 2022 | 128 | 396 | 104 | 26% |
| 2023 | 119 | 351 | 159 | 45% |
| 2024 | 110 | 190 | 88 | 46% |
| 2025 | 127 | 270 | 239 | 89% |

**Consequence:** any Phase B feature relying on line movement (open vs. close) is unreliable for 2021-2024 — coverage is too sparse to trust as systematically present. Pre-2025 line-movement features must be explicitly marked `data_quality: sparse`, not silently computed over mostly-missing values. This is a real, material constraint on how much of the 2021-2025 backtest window can support the more sophisticated parts of Phase B.

## 3. Provider set — unstable across seasons, includes non-sportsbook sources pre-2024

**Verified directly:**
- 2021: `Bovada, Caesars (Pennsylvania), William Hill (New Jersey), consensus, numberfire, teamrankings`
- 2022: `Bovada, Caesars Sportsbook (Colorado), William Hill (New Jersey), consensus, teamrankings`
- 2023: `Bovada, Caesars Sportsbook (Colorado), DraftKings, William Hill (New Jersey), consensus, teamrankings`
- 2024: `Bovada, DraftKings, ESPN Bet`
- 2025: `Bovada, DraftKings, ESPN Bet`

**Consequence:** `numberfire` and `teamrankings` are analytics sites posting model-derived lines, not real sportsbooks — they must be explicitly excluded from any calculation that assumes real, money-backed market pricing. Any historical query not filtering to a real-sportsbook allowlist risks blending genuine market data with third-party model output. 2024-2025 is the only window with a clean, stable, all-real-sportsbook provider set.

## 4. Same-provider, same-snapshot requirement — confirmed necessary, providers genuinely disagree

**Verified directly** (Temple @ Miami, 2023 Wk4): Bovada spread 23.5/open 25, DraftKings spread 23.5/open 23, William Hill spread 23/open null. Real, material disagreement between books on the same game, plus inconsistent field completeness (William Hill has no open value at all here).

**Consequence:** confirms the design's requirement that spread and total must come from the same provider for the offense/defense decomposition — using one book's spread with another's total would describe a market state that never existed. William Hill specifically has unreliable open-value population and may need separate handling or exclusion.

## 5. `completed` field and per-quarter scoring — reliable across all seasons

**Verified directly:** `completed` matches or nearly matches total game count for every season 2021-2025 (e.g., 2025: 3745/3745 completed). `homeLineScores` (per-quarter scoring, needed to separate regulation from overtime) is present for 99%+ of games every season.

**Consequence:** no constraint here — this part of the design's data dependency is solid.

## 6. Overtime frequency — confirmed real and non-trivial

**Verified directly:** 90-141 games per season went beyond 4 scoring periods (i.e., overtime), out of roughly 2,400-3,750 total games per the unfiltered `/games` response (732-848 of which are true FBS-vs-FBS, see below). A real, recurring fraction of games, confirming the design's OT-specific handling rules (regulation-score preference, residual capping, downweighting multi-OT games) are necessary, not theoretical.

## 7. `division: 'fbs'` API parameter does NOT filter to FBS-only games — significant finding

**Verified directly:** requesting `division: 'fbs'` still returns `classifications={None, 'fbs', 'fcs', 'iii', 'ii'}` in every season's response, with total game counts (2,408-3,747/season) far exceeding a true FBS-only schedule (~750-900 games/season).

**Correct manual filter, verified:** `homeClassification == 'fbs' AND awayClassification == 'fbs'` — confirmed to produce realistic FBS-vs-FBS game counts (732/2021, 762/2025) when applied. Filtering on `homeClassification == 'fbs'` alone still includes FBS-vs-lower-division games and is insufficient.

**Consequence — open item, not yet resolved:** it is not yet confirmed whether `generate_picks.py`'s own game-fetching (the existing live betting model, not the new quality system) has this same leak. Worth checking in a future session as a cross-cutting finding, separate from this design's scope, since it could mean the existing model's `TARGET_CONFERENCES`/line-existence filters are silently doing FBS-isolation work that was assumed to be handled upstream by the API parameter.

**Also confirmed:** 41-62 games per season have a `None` classification on at least one side — these need an explicit `skipped_reason: "missing_classification"`, not silent inclusion or exclusion.

## 8. Holdout season classification — directly constrained by findings 2 and 3

Per design v5's Section 0.3 requirement: every season must be classified by both (a) prior analytical exposure and (b) actual data quality, now that both are known.

| Season | Prior exposure (this project) | Open-line data quality | Provider cleanliness |
|---|---|---|---|
| 2021 | Previously examined (existing model's backtest window, tonight's audit) | Sparse (24%) | Contaminated (numberfire/teamrankings present) |
| 2022 | Previously examined | Sparse (26%) | Contaminated |
| 2023 | Previously examined | Sparse (45%) | Contaminated |
| 2024 | Previously examined | Moderate (46%) | Clean |
| 2025 | Previously examined | Good (89%) | Clean |
| 2026 | Not yet examined (season hasn't started; only Week 1 preseason picks generated and discussed tonight) | Unknown, presumably continues 2024-2025's clean pattern | Presumably clean |

**This materially changes the holdout picture from what design v5 anticipated.** Every 2021-2025 season is both previously examined (the entire premise of Section 0.3's concern) AND has real data-quality constraints (findings 2-3) limiting what Phase B can reliably compute for it. **2026 is the only season satisfying both "not previously examined" and "presumably good data quality."** Recommendation: 2026 should be treated as the prospective live holdout, not a fallback option — there is no genuinely defensible alternative within the currently available data. Development and parameter-selection work should draw primarily from 2024-2025 (clean providers, best open-line coverage), with 2021-2023 usable for football-outcome validation (Stage 1, which doesn't depend on line-movement data) but flagged as data-quality-limited for anything in Stage 2 that needs reliable open/close comparison.

---

## Outstanding Phase 0 items (not yet verified, separate from this session)

- Garbage-time filtering availability (not yet checked against CFBD's advanced stats endpoints)
- Price/juice availability beyond moneyline (confirmed moneyline exists in raw `/lines` response; whether spread-bet juice/vig is available separately not yet checked)
- Team-name canonicalization rules (directly relevant given tonight's earlier substring-collision bug in the betting model itself — not yet re-verified in the context of this new system)
- Null percentages by feature for `cfbd.advanced_stats`, `cfbd.recruiting_rankings`, `cfbd.draft_production` specifically (only `cfbd.lines`/`cfbd.games` have been profiled tonight)
- Whether `generate_picks.py`'s existing game-fetching has the same FBS-classification leak found in finding 7
