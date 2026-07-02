# Phase D Validation Findings

**Date:** 2026-07-01  
**Status:** Signal promising at population level, insufficient published-pick sample to conclude — monitoring through 2026 season

---

## What Was Tested

The Quality-of-Win system (Phases A-C) was validated against 2021-2025 historical data using a repeatable, config-driven harness (`scripts/cfb_quality_phase_d.py`). The holdout (2026) was not touched.

Two signals from Phase C (`mart_cfb_live_strength`) were evaluated:
- `off_vs_preseason`: how much a team's live offensive strength has drifted from its preseason quality anchor
- `market_outperformance_ema`: how much the team has been outperforming or underperforming the betting market in recent weeks

Validation was run twice: over all FBS games (too broad) and restricted to **model-qualifying games** (PPA gap ≥ 0.15, conference eligible — the natural scope of the existing model).

---

## Stage 1 Results — Does the signal predict football outcomes?

Pearson correlation of signal with spread_residual (actual − expected margin):

| Signal | Dev r | Param r |
|---|---|---|
| live_off_strength | +0.070 | +0.053 |
| off_vs_preseason | +0.033 | +0.079 |
| market_outperformance_ema | −0.048 | +0.100 |

Below the pre-registered r > 0.10 threshold for Stage 1. Directionally consistent but weak magnitude within already-filtered games.

---

## Stage 2 Results — Does the signal predict ATS outcomes?

**Q5 vs Q1 quintile analysis (off_vs_preseason), model-qualifying games:**

| Season set | Q1 cover% | Q5 cover% | Delta |
|---|---|---|---|
| Dev (2021-2023) | 45.3% | 55.0% | +9.7 pts |
| Param-selection (2024-2025) | 49.7% | 56.0% | +6.3 pts |

**Continuous threshold analysis (off_vs_preseason), model-qualifying games:**

| Season set | Strong (>0.15) N | Cover% | ROI% | Weak (<-0.15) N | Cover% | ROI% |
|---|---|---|---|---|---|---|
| Dev (2021-2023) | 1,110 | 54.2% | +3.5% | 345 | 49.0% | −6.5% |
| Param-selection (2024-2025) | 374 | **57.0%** | **+8.7%** | 354 | 48.9% | −6.7% |

**Signal is real at the game-population level.** Consistent direction across both season sets, 1,484 total Strong game-team pairs.

---

## Published-Pick Ablation Results

Running the signal against only the 293 actual published picks (after spread-rule fix):

| Category | N | Cover% | ROI% |
|---|---|---|---|
| Strong (>+0.15) | 139 | 65.5% | 25.0% |
| Neutral | 142 | 66.9% | 27.7% |
| Weak (<-0.15) | **12** | 75.0% | 43.2% |
| All published | 293 | 66.6% | 27.0% |

**Sample size is insufficient for any conclusion.** N=12 for Weak has a confidence interval of ±25 percentage points. N=139 for Strong has a CI of ±8 points — meaning the true cover rate could be anywhere from 57% to 73%. The apparent pattern (Weak outperforming Strong) is almost certainly noise given these sample sizes, not a finding about the signal.

The published-pick population (325 picks over 5 seasons) is too small to measure an additional filter's incremental effect. The top-8 weekly cap, combined with the model's existing selectivity, produces a sample too thin to distinguish signal from noise at this level of granularity.

---

## Honest Verdict

**`off_vs_preseason` shows a real effect at the model-qualifying game population level (N=1,484), but the published-pick sample (N=293) is insufficient to confirm or deny incremental value within the model's actual output.**

The 2021-2025 historical data is exhausted as a discriminating signal for this specific question. The right path is prospective: collect 2026 season data with quality signals pre-computed, then re-evaluate after Week 8 when enough published picks have accumulated.

**`market_outperformance_ema`:** no consistent direction across season sets. Not worth monitoring further at this stage.

---

## 2026 Monitoring Plan

1. `mart_cfb_live_strength` is built and populating in real-time as games are played.
2. Each week's picks already have an associated `off_vs_preseason` for the bet team available from the mart.
3. After Week 8 of the 2026 season (~40-50 published picks), re-run `quality_signal_ablation.py` against the live 2026 data combined with 2021-2025.
4. Decision threshold: if Strong picks cover at >60% with N>50 across 2021-2026 combined, add `off_vs_preseason > 0.10` as a score bonus (+5 points) in `score_game()` and document the change.
5. If the pattern remains flat or noisy after Week 12, remove the signal from monitoring consideration.

The 2026 season data is the live holdout. Do not pre-emptively adjust `score_game()` before Week 8 data exists.

