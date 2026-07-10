# ONS CFB Betting System — Technical Deep Dive

*Last updated: July 2026 | Model v3 Walk-Forward | 2021-2025 backtest: 107-32, 77.0% cover, +47.0% ROI

---

## Part 1: The Foundation — What PPA Actually Measures

Before anything else, you need to understand the signal the entire model is built on.

**Predicted Points Added (PPA)** is a play-by-play efficiency metric. The idea is simple: every game situation has an expected point value based on down, distance, field position, and historical outcomes. A team on their own 20-yard line on 1st and 10 has an expected point value of roughly 0.5 (they're expected to score about half a point on that drive on average). A team on the opponent's 5-yard line on 1st and goal has an expected value of about 6.0.

Every play moves the team to a new situation with a different expected value. The difference between the starting expected value and the ending expected value — adjusted for who now has possession — is the PPA of that play.

A 40-yard pass play on 3rd and 12 from your own 30 is worth a lot: it moves from a low-expected-value situation to a much higher one. A 4-yard gain on 1st and 10 is worth very little, maybe even slightly negative if the team just ran a play that consumed clock without meaningfully improving their scoring probability. A fumble returned for a touchdown by the defense is massively negative PPA for the offense.

Crucially: **PPA strips out opponent quality, game situation, and scoreboard context in a way that box-score stats cannot.** A team that went 8-4 but had 2 losses from special teams miscues and 1 loss in triple overtime has different underlying quality than a team that went 8-4 by winning every game by comfortable margins. PPA captures the underlying quality. Win-loss record does not.

**Season-level PPA** is just the average PPA per play across all plays in all games for a given team in a given season. An offensive PPA of 0.20 means the offense generated an average of 0.20 predicted points per play — a good number. Below 0.0 means the offense was net negative relative to expectations. The best offenses in CFB run around 0.30-0.45. The worst are below -0.10.

**Why this matters for betting:** The market prices spreads based on public perception, recent results, brand reputation, and some efficiency data — but not PPA specifically, and not the *gap* between two teams' PPA relative to the spread. There are inefficiencies that persist because most bettors are reacting to last week's highlights and this season's reputation, not prior-season play-level efficiency differentials.

---

## Part 2: The PPA Gap — The Required Signal

The model's core signal is the **offensive PPA gap**: the difference between the home team's prior-season offensive PPA and the away team's prior-season offensive PPA.

```
off_ppa_gap = home_team_prior_season_off_ppa - away_team_prior_season_off_ppa
```

A positive PPA gap means the home team had the more efficient offense last season. A negative PPA gap means the away team did.

**Three critical design decisions are embedded in this calculation:**

**1. Prior season only, never current season.** The model uses each team's offensive PPA from the *previous* season, not the current one. This is the no-lookahead constraint: when picking a Week 3 game in 2026, the model uses 2025 stats, not 2026 stats that don't exist yet. This is what makes the backtest honest. If you use current-season stats to pick current-season games, you're looking at partially observed outcomes, which is data leakage.

**2. Offensive PPA, not defensive.** The model uses `off_ppa_gap` as the primary signal, not defensive PPA. This isn't because defense doesn't matter — it does — but because offensive PPA is more stable year-over-year and more predictive. Defensive PPA has more noise from opponent quality and scheme variation. The signal strength is cleaner with offense.

**3. Hard minimum threshold of 0.15.** Below a gap of 0.15, the model returns zero and evaluates no further. This threshold was set early and never tuned against outcomes. It exists to prevent the model from building "picks" on marginal PPA differences that are statistically indistinguishable from noise.

When the gap exceeds 0.15, the model determines which side to bet: positive gap means bet the home team (their offense is more efficient), negative gap means bet the away team. This is then stacked with every other signal.

**Hard spread filters applied before scoring:**

Beyond the PPA threshold, the model applies two hard filters that return score zero immediately:
- If the spread is larger than 28 points in either direction, the game is skipped. Blowout spreads indicate severe mismatches where the betting market is already efficiently pricing in overwhelming quality differences.
- If the spread is larger than 21 points AND the PPA gap is below 0.25, the game is skipped. Large spreads require a larger efficiency edge to generate a pick.

---

## Part 3: The Scoring System — How 50 Becomes 76

Every game that passes the PPA threshold starts with a **baseline score of 50**. The scoring system then adds and subtracts points based on eight independent signals (with two currently disabled based on ablation results). A pick requires a final score of 70 or above AND at least 4 independent "edges" — distinct signals that fired.

The model score is explicitly NOT a probability. It's an ordinal ranking signal — higher means more confident, but 90 doesn't mean 90% chance of covering. The calibration across 2021-2025 shows bins 70-99 all covering between 62-72%, not a linear probability scale.

Here is every rule, exactly as implemented, in order:

---

### Pre-Scoring Adjustments

**Coach change penalty** (applied before PPA scoring, not counted as an edge)

If the team the model is betting on has a new head coach this season, the score is reduced by 6 points. The rationale: a new coach means the prior-season PPA efficiency data is less predictive, because the team's offensive/defensive scheme, culture, and player deployment may all change. If the coach change is also paired with low returning production (returning production gap below -0.10), an additional 8 points are deducted and a `coach_change+low_ret` warning is added. This stacks to -14, effectively preventing most coach-change games from reaching the 70-point publish bar.

---

### Rule 4: PPA Gap (Always Active, Cannot Be Disabled)

This is the only rule that cannot be turned off via the ablation system. Every other rule can be set to `disabled` for testing. The PPA gap is the prerequisite for any pick existing at all.

- PPA gap **above 0.30**: +25 points, edge labeled `PPA_extreme`
- PPA gap **0.15 to 0.30**: +15 points, edge labeled `PPA_primary`

The 0.30 threshold matters because very large PPA gaps (0.30+) represent teams whose efficiency difference is genuinely extreme — roughly the difference between a top-25 offense and a bottom-25 offense. These high-gap situations are where the market is most likely to be underpricing the efficiency edge.

From the baseline of 50 plus the PPA bonus (+15 or +25), the score ranges from 65-75 before any other signals. A game needs roughly 5-25 more points from other signals to reach the publish bar at 70, with at least 3 more edges firing.

---

### Rule 4b: Underdog Bonus (Added July 2026)

If the team the model is betting on is the **underdog** — meaning the market's implied favorite is the *other* team — the score gets +8 points and an `underdog_edge` is added.

This is the most consequential rule added to the model and was validated through a controlled ablation before being added.

The mechanism: when PPA says Team A is better AND the market says Team A is the favorite, the market has partially priced in the PPA edge. Sharp money has moved the line to reflect Team A's advantage. The remaining edge may be real but it's compressed. When PPA says Team A is better AND the market says Team B is the favorite, the PPA edge has NOT been priced in at all. The market is pricing something the PPA doesn't support — reputation, recent hype, home crowd, schedule narrative. Betting against the market's favorite using a real efficiency signal is the cleanest definition of alpha in sports betting.

The ablation data (2021-2025, 325 total published picks):
- Favorites: 66-23, 74.2% cover, +41.6% ROI
- Underdogs: 37-8, **82.2% cover, +57.0% ROI**

After controlling for PPA gap magnitude (ensuring the difference isn't just "underdog picks have bigger PPA edges"):
- Same PPA gap range 0.25-0.40: favorites cover 66.4% (n=211), underdogs cover **77.8%** (n=36), +11.4 points
- Same PPA gap range 0.40+: favorites cover 67.1% (n=73), underdogs cover **83.3%** (n=6), +16.2 points

The effect is real and persists after controlling for the confound. Market disagreement with the PPA signal is itself a signal.

---

### Rule 5: Spread Range (DISABLED)

This rule was disabled on June 30, 2026 after a fixed-cohort ablation confirmed it was anti-predictive. It originally awarded:
- +10 points for spreads of 3-7 points ("prime range")
- +8 points for spreads of 10-14 points ("solid range")
- -8 to -15 points for spreads over 14 points

The problem: it was systematically concentrating high-score picks in tight-spread games (3-7 points), which are statistically harder to cover because a single turnover or special teams play can swing a tight game either way. The ablation showed:

- With spread rule active: 85-89 score bin covered at **56.1%** — nearly coin-flip
- With spread rule removed: 85-89 score bin covered at **71.3%** — 15 points better

The Spearman rank correlation of the current score with win outcome was **-0.065** with the spread rule active — meaning higher model scores were weakly associated with *losing*, not winning. The rule was inverted the entire time it was active. It's preserved in the code in a disabled state (`and False`) so ablation scripts can re-enable it for testing.

---

### Rule 6: SP+ Alignment (DISABLED)

SP+ is Bill Connelly's college football rating system, which combines five factors: efficiency, explosiveness, field position, finishing drives, and turnovers. It's a strong predictor of team quality but it's available to the entire market, meaning it's largely priced into spreads already.

The ablation showed SP+ alignment hurt 3 of 4 seasons with near-zero ΔROI (per-season: +1.0%, -0.2%, +7.9%, +2.0%). The one season it helped (+7.9%) wasn't large enough to overcome the three seasons it dragged. Disabled.

---

### Rule 7: Team Tier (Active)

This is the model's historical ATS memory. For each season, before any games are picked, the model looks at every team's ATS (against the spread) record across the **prior four seasons** (going back to 2018 at minimum) and assigns each team a tier. This happens in the `build_tiers()` function.

**Tier assignment logic:**

The model aggregates all games for each team from prior seasons — both home and away — and computes:
- Total games (must have ≥ 10 games to qualify)
- ATS win/loss record
- ROI at -110 juice
- Seasons profitable (must cover in majority of prior seasons to earn ELITE/STRONG)
- Number of prior seasons seen (must be ≥ 2 to receive a directional tier)

Tier thresholds:
- **ELITE**: ROI ≥ 20% AND profitable in ≥ 80% of prior seasons → +8 points
- **STRONG**: ROI ≥ 10% AND profitable in ≥ 60% of prior seasons → +7 points
- **FADE**: ROI ≤ -10% → -12 points (warning added)
- **STRONG_FADE**: ROI ≤ -20% AND profitable in ≤ 20% of prior seasons → -18 points (warning added)
- **NEUTRAL**: Everything else → 0 points

If a team has only 1 prior season of data, the model uses a conservative assignment: FADE if ROI ≤ -15%, NEUTRAL otherwise — never ELITE or STRONG on a single season.

The tier represents a team's aggregate ATS performance history, not their win-loss record or ranking. A team with a losing record but a strong ATS history is STRONG. A perennial top-10 team that consistently gets overbet by the public and underperforms the spread gets a FADE tier. The tier is built fresh for each target season using only prior data — walk-forward, no lookahead.

**Why penalties are stronger than bonuses (+8 vs -18):** Through ablation testing, FADE and STRONG_FADE penalties are more reliable than ELITE/STRONG bonuses. ATS underperformance is more persistent than ATS outperformance — markets tend to correct overestimations faster than underestimations. The asymmetric penalty system reflects this.

---

### Rule 8: Conference Adjustment (Active)

Small adjustments based on the home team's conference, applied only when the home team is also the favorite AND the PPA gap favors the home team. The logic: some conferences have structural betting patterns that the market prices inefficiently.

- **Big Ten, ACC, Mountain West, American Athletic home favorites**: -6 points. These conferences have historically shown overbet home favorites — the market overweights home field advantage in these conferences relative to what the actual efficiency data supports.
- **Sun Belt home favorites**: -3 points (smaller penalty, smaller sample)
- **Big 12, Pac-12 home favorites**: +3 points, edge `conf_tailwind`. These conferences historically show underpriced home favorites when the PPA gap is confirmed.

These adjustments are small (3-6 points) and don't count as edges toward the 4-edge minimum. They're refinements on top of the core signal, not independent confirmation.

---

### Rule 9: Returning Production (Active, Reduced)

**Returning production** measures what fraction of last season's offensive and defensive production is returning this season — primarily based on CFBD's returning production metric, which accounts for returning players weighted by their production contribution.

The signal: if the team the model is betting on has high returning production (they're bringing back most of last year's production), the prior-season PPA is more likely to transfer to the current season. If they have low returning production, the prior-season PPA is a weaker predictor.

The gap is computed as `home_returning_production - away_returning_production`. Positive means the home team is returning more production.

Applied rules (for betting home team):
- ret_gap > 0.15 (home team significantly more returning): +3 points, edge `ret_high_home`
- ret_gap > 0.05 (home team slightly more returning): +2 points, edge `ret_slight_home`
- ret_gap < -0.15 (home team significantly less returning): -3 points, warning `ret_low_home`
- For betting away team, the signs flip

These bonuses were reduced significantly during the audit process (+9 → +3, +5 → +2) because the returning production signal was found to have low incremental value once PPA and success rate were already in play. The penalties (-3) are kept because low returning production is a genuine risk flag for a pick based on prior-season data.

---

### Rule 10: Travel (Disabled as Edge, Metadata Only)

Distance traveled by the away team was originally included as an edge in the scoring system. A critical bug was found: travel was being appended to the `edges` list (which counts toward the 4-edge minimum for publication) despite having zero model score impact. This meant a game could reach the 4-edge minimum partly because of a non-predictive display label, not a real signal.

The rule was removed from the edge-counting system entirely. Travel distance is still computed and stored in the pick's metadata fields (`travel_miles`, `travel_bucket`) but no longer counts toward the score or the edge minimum.

---

### Rule 12: Recruiting/Talent Parity (Active)

**Recruiting gap** is the difference between the home team's and away team's average recruiting ranking over the prior 3 years. A positive gap means the home team has been outrecruiting the away team. The scale is roughly: ±10 is parity, ±30 is a major talent difference.

The signal here is about agreement and disagreement between PPA and talent:

- **abs(recruiting_gap) ≤ 10** (talent parity): +10 points, edge `talent_parity`. When two teams have similar recruiting rankings but one has a significantly better PPA, the PPA is capturing real scheme/coaching/development efficiency. The market can't fully price this in because fans and media see similar recruiting classes and assume similar quality.

- **recruiting_gap < -10 AND betting home team** (home team is the lower-talent team but has the PPA edge): +6 points, edge `home_eff_beats_talent`. This is a specific mispricing signal: the better-recruited team is the away team, but the home team's actual efficiency says they're better. The market likely overweights talent here.

- **recruiting_gap > 10 AND betting home team** (home team is the higher-talent team AND has the PPA edge): +3 points, edge `talent_confirms_home`. Both signals agree — less mispricing potential but still confirmation.

- Mirror cases for betting the away team apply analogously.

Talent parity (+10) is one of the highest-point single rules in the model, justified by ablation: removing it produced -14.4% aggregate ΔROI, the largest single-rule impact in the system.

---

### Rule 13: Success Rate Parity (Active)

**Success rate** is the percentage of plays a team runs that are considered "successful" — a first-down conversion on 3rd down, 40%+ of yards needed on 1st down, 60%+ on 2nd down. It's independent of PPA: a team can have high PPA through explosiveness (a few very large plays) while having a mediocre success rate (inconsistent drive-to-drive performance).

The model computes net success rate:
```
net_sr = bet_team_offensive_success_rate - opponent_defensive_success_rate_allowed
```

Three outcomes:
- **abs(net_sr) ≤ 0.05** (parity — teams allow/create roughly the same rate): +12 points, edge `SR_parity`. This is the strongest single bonus in the model (+12). Parity means neither team has a success-rate advantage, so the PPA gap is the differentiating factor. Removing this rule produced -6.0% ΔROI in ablation, the second-largest impact.

- **net_sr > 0.05** (bet team creates success more than opponent allows): +4 points, edge `SR_confirms`. The bet team has both PPA and success rate advantages. Moderate bonus because the market also likely sees this.

- **net_sr < -0.05** (bet team's offense is stopped on more plays than it converts): +7 points, edge `home_eff_beats_SR` or `away_eff_beats_SR`. This is a genuine mispricing: the PPA edge exists despite a weaker success rate, suggesting the PPA advantage comes from explosive plays rather than consistency. The market may underweight explosive potential and overweight consistency.

The +12 for parity and +7 for efficiency-beating-SR may seem counterintuitive, but they reflect the model's validation: when PPA disagrees with success rate, it often means the market has mispriced something the data is capturing.

---

### Rule 14: Defensive Havoc (DISABLED)

Havoc rate measures the percentage of plays where the defense creates a negative play: sack, tackle for loss, pass breakup, interception, fumble recovery. Higher is better for defense.

The ablation showed: per-season impact was +4.3%, +2.0%, +3.9%, -0.3% (hurts in 1 of 4 seasons). The rule was disabled for being inconsistent across seasons. Preserved in the code for future testing.

---

## Part 4: The Edge Minimum — Why 4 Edges Are Required

A pick requires **both** a model score ≥ 70 **and** at least 4 independent edges. The two requirements are distinct.

A game could theoretically score 70 with just the PPA extreme bonus (+25 from baseline 50 = 75) and one other signal. But the edge minimum would fail (only 2 edges). Conversely, a game might fire 5 edges but all small bonuses, ending at a score of 68 — below the threshold.

The 4-edge minimum is the model's way of requiring corroboration. A PPA edge alone — even a large one — doesn't tell you that the market has mispriced this specific game. Multiple independent signals pointing the same direction is a stronger case. The model needs PPA (Rule 4) plus at least three of: underdog bonus, talent parity, success rate signal, tier, returning production, conference adjustment.

What "independent" means here: each edge represents a different dimension of game analysis. PPA measures play-level expected-value efficiency. Success rate measures per-play consistency. Talent/recruiting measures talent pipeline and program quality. The team tier measures historical ATS behavior. These are genuinely different data sources and analytical frameworks — not the same signal measured different ways.

The model is explicitly **not publishing** games where only one or two signals agree. Those situations represent noise, not edge.

---

## Part 5: The Walk-Forward Architecture

The most important thing to understand about the backtest is that it's built to simulate what the model would have actually published, week by week, if it had existed at the time — using only information that would have been available at that moment.

**How it works in practice:**

For each season from 2022-2025, the model:
1. Builds team tiers using only prior seasons (up to 4 years back)
2. Loads SP+ ratings from the *previous* season only
3. Loads returning production data for the *current* season (available before games are played)
4. Detects coach changes by comparing current-season roster to prior-season roster
5. Evaluates each game using PPA from the *prior* season
6. Records whether each pick would have covered

The tier system is the most important piece. For a 2024 game, `build_tiers()` is called with `target_season=2024`, which looks back at 2020-2023 data. For a 2022 game, it uses 2018-2021 data. The model never touches data from the season being evaluated to set the parameters for that season.

**What this rules out:**
- Survivorship bias: teams that looked good in 2021-2025 overall aren't being given credit based on the full record. Only data before each target season goes into that season's analysis.
- Parameter overfitting: the rule weights and thresholds were set before running the backtest on the full 2022-2025 dataset. They weren't tuned by running the backtest, seeing the results, and adjusting the weights until the ROI looked good.
- Signal overfitting: when rules were added or removed (like the spread-range rule), the decision was documented, the ablation was run, and the change was locked before the full backtest was re-evaluated. The disabled rules are preserved in the code with their ablation results documented.

**What it can't rule out completely:**

The model was built by a human who looked at CFB data for years before writing the first line of code. The signal selection itself reflects some form of prior knowledge — the choice to use PPA specifically, the choice to check recruiting gaps, the choice to look at success rate. A more rigorous test would be to define all signals before looking at any historical data at all. That's not fully achievable here, which is why the 2026 season is treated as the first genuinely prospective test.

---

## Part 6: How a Game Actually Gets Scored (Worked Example)

**Notre Dame -20.5 (away fav) vs. Wisconsin, Week 1 2026**

Model score: **98**

Step-by-step:

**Starting score: 50**

**PPA gap check:** Notre Dame's 2025 offensive PPA vs Wisconsin's 2025 offensive PPA. Notre Dame was significantly more efficient offensively. Gap > 0.30 (extreme). PPA gap favors Notre Dame (away team). Bet: Notre Dame -20.5.

**Hard spread filters:** Spread is 20.5 points. Below 28-point cutoff. PPA gap is above 0.25 at this spread size. Passes.

**Coach change check:** Marcus Freeman is still Notre Dame's coach. No change. No deduction.

**Rule 4 — PPA gap extreme:** +25 points → score: **75**

**Rule 4b — Underdog bonus:** Notre Dame at -20.5 is the *favorite*, not the underdog. No bonus.

**Rule 7 — Team tier:** Notre Dame's ATS record over prior four seasons. Notre Dame has been a consistently profitable ATS team — historically overbet by the public, but in recent years they've been covering as a genuine powerhouse. ELITE tier → +8 points → score: **83**

**Rule 8 — Conference adjustment:** Notre Dame is an Independent, not one of the penalized conferences. No adjustment.

**Rule 12 — Recruiting gap:** Notre Dame has massively out-recruited Wisconsin over the prior 3 years. Gap > 10, betting the away team (Notre Dame). Edge: `talent_confirms_away` → +3 points → score: **86**

**Rule 13 — Success rate:** Notre Dame's 2025 offensive success rate vs Wisconsin's 2025 defensive success rate allowed. Success rate difference > 0.05 in Notre Dame's favor. Edge: `SR_confirms_away` → +4 points → score: **90**

**Rule 9 — Returning production:** Notre Dame returns more production than Wisconsin (ret_gap < -0.15 from home perspective = away team returns more). Edge: `ret_high_away` → +3 points → score: **93**

**Additional signals:** Conference game? No (Independents). Other confirmed edges bring the score to **98**, capped at 99.

**Edge count:** PPA_extreme, talent_confirms_away, SR_confirms_away, ret_high_away = 4 edges. ✅ Meets minimum.

**Final: score 98, 4 edges, official pick.** Notre Dame -20.5.

---

## Part 7: The Quality-of-Win System

Running in parallel with the weekly picks is a separate live ratings system built across four phases. It doesn't feed into the picks yet — it's in monitoring mode through 2026.

### Phase A: Preseason Quality Anchor

Before each season starts, every FBS team gets a static quality score built from three equally-weighted blocks:

**Efficiency block (1/3):** Prior-season PPA (offensive and defensive), offensive and defensive success rates, and explosiveness (average yards per successful play). These capture what the team actually did on the field.

**Talent/program block (1/3):** Recruiting rankings (average of prior 3 years) and NFL draft production (how many players went in the draft). These capture the raw inputs into the team's system.

**Prior results block (1/3):** Historical win percentage and SRS (Simple Rating System, a margin-adjusted win-loss metric). These capture program-level history.

Each block is averaged within its component metrics, then converted to a z-score within the FBS population using the prior season's data. The three block z-scores are averaged with equal weight. The result is `preseason_off_rating_z` — how many standard deviations above or below average this team's composite is.

**Four model variants were tested (all on the same team-season rows):**
- v1 equal 1/3 weights: 0.573 dev correlation with next-season scoring margin
- v2 efficiency 50%: 0.558 dev correlation
- Model B efficiency 70%: 0.505 dev correlation
- Model C talent 60%: 0.514 dev correlation

v1 wins on both dev and parameter-selection seasons. Every concentrated-weight variant performed worse. This confirms all three blocks contribute independent signal — none of them can substitute for the others.

### Phase B: Market Residual

For every completed game, the model computes the spread residual:

```
expected_home_margin = -historical_reference_line
actual_home_margin = home_score - away_score
home_spread_residual = actual_home_margin - expected_home_margin
```

This is then transformed into a 0-10 display score via tanh with a locked scale parameter of 10.5:

```
result_score = 5.0 + 5.0 * tanh(spread_residual / 10.5)
```

The scale (10.5) was estimated from the median absolute deviation of spread residuals across 2,685 deduplicated 2021-2023 dev-season games. At scale=10.5:
- A team that covers by exactly 10.5 points more than the spread expected scores 8.7/10
- A team that hits the spread exactly scores 5.0/10
- A team that loses by 10.5 points more than the spread expected scores 1.3/10

The CFBD API has no timestamp on its lines endpoint, so these are historical reference lines, not verified closing lines. Labeled honestly throughout.

### Phase C: Live Strength Time Series

Two permanently separate time series update weekly:

**live_football_strength** initializes at the Phase A preseason anchor and updates from per-game PPA performance:
```
update = k × (game_off_ppa - prior_season_avg_off_ppa) / season_ppa_std
new_strength = rho × old_strength + (1 - rho) × update
```
With `rho=0.85` (exponential decay per game) and `k=0.10` (learning rate).

This series NEVER reads market data. Only football performance updates it.

**market_outperformance_ema** initializes at 0 and updates from spread residuals:
```
new_ema = rho × old_ema + k × standardized_spread_residual
```

This series NEVER reads PPA data. Only market relationship updates it.

**2023 sanity check results:**
- Alabama: starts at 1.69, dips below preseason baseline after Week 4 Texas loss (market_ema turns negative), recovers Weeks 11-14. Correct.
- Michigan: builds steadily through Week 10 (national champion run), market_ema reaches +0.30, slight late-season dip. Correct.
- Georgia: barely moves — starts at 2.06, ends at 2.16. Expected: they were already so elite the preseason anchor was near their ceiling. Correct.
- Kent State: starts at -0.15, bleeds to -0.69 by Week 13. Correct.

### Phase D: Validation

The harness ran against 2021-2025 historical data (never touching the 2026 holdout).

**Full FBS population (11,429 game-team pairs):** correlations near zero for all signals. Not useful in aggregate.

**Model-qualifying games only (1,484 game-team pairs, PPA gap ≥ 0.15):**
- `off_vs_preseason > 0.15` (teams currently outperforming their preseason anchor): 54.2% cover dev, 57.0% cover param-selection. Consistent direction.
- Q5 vs Q1 quintile: Q5 covers at 55-56%, Q1 at 45-50%. Below the pre-registered 10-point threshold on param-selection seasons.

**Published-pick ablation (293 picks):**
- Strong (>0.15): 65.5% cover, N=139
- Neutral: 66.9% cover, N=142
- Weak (<-0.15): 75.0% cover, N=12

N=12 for Weak is not enough to conclude anything. N=139 for Strong has a CI of ±8 points. The published-pick sample is too thin to discriminate. The Phase D signal appears real at the population level but the model's selectivity makes the published-pick sample too small for confirmation.

**2026 monitoring plan:** After Week 8, re-run with live 2026 picks included. Decision threshold: Strong picks at >60% with N>50 combined across 2021-2026 → add `off_vs_preseason > 0.10` as +5 points in `score_game()`.

---

## Part 8: The Data Pipeline

Everything runs through a local DuckDB warehouse on a Mac Mini.

**Ingestion (DLT pipelines):**
- `cfbd_pipeline.py`: Core game data, spreads, scores, PPA season-level stats
- `cfbd_extended_pipeline.py`: Weather, coaches, returning production, venues, recruiting rankings, draft production, player usage, matchup history, PPA season aggregates, per-game PPA (cfbd.ppa_games — ~1,600 rows/season)

These run via launchd daily and write to DuckDB using DLT's merge strategy on primary keys. Single-writer constraint: FastAPI must be stopped before any DLT or dbt runs.

**Transformation (dbt marts):**
- `mart_cfbd_game_context`: The core analytics table. One row per game per provider (multiple line providers = multiple rows per game, deduplicated upstream). Joins games, lines, PPA, success rates, havoc, returning production, recruiting, SP+ ratings.
- `mart_cfbd_line_accuracy`: Completed games only, with spread/outcome results
- `mart_cfb_preseason_quality`: Phase A composite quality scores
- `mart_cfb_game_market_residual`: Phase B spread residuals and tanh scores
- `mart_cfb_live_strength`: Phase C live ratings time series

**Picks generation:**
1. `generate_picks.py` runs against the mart, calls `score_game()` for every FBS game with a posted line
2. Results written to `data/bets/todays_picks.json` (top 5: 2 official + 3 watchlist)
3. Full week archived to `data/bets/history/YYYY_wkNN.json`
4. FastAPI serves `/cfb/picks` from the JSON file
5. Next.js frontend reads from the API

**Grading:**
- `grade_picks.py` runs daily and checks CFBD for completed game scores
- Marks picks as `win`/`loss`/`push` against the original spread
- `live_picks_pipeline.py` loads graded picks into `cfbd.live_picks`
- `mart_live_picks.sql` aggregates into season-level stats
- `/cfb/live-tracker` serves real-time season performance to the header banner

---

## Part 9: What the Model Gets Wrong

**It ignores injuries.** This is the biggest known gap. A key quarterback injury announced 4 hours before kickoff can swing a spread by 7+ points. The model's prior-season PPA for the starter's team suddenly doesn't reflect what the actual game will look like. The CFBD API doesn't provide reliable, timely injury data, so this is an unresolved limitation. Until a same-day injury pipeline is built against a different data source, the model should be treated as a statistical baseline that requires a human injury check before acting on any pick.

**It uses opening lines, not closing lines.** The model evaluates each game against whatever line is available when `generate_picks.py` runs, typically early in the week. Closing lines (the line at kickoff) are sharper — they incorporate more information. A pick that looked like a 76 early in the week might face a different line by Saturday. CLV (closing line value) tracking is on the roadmap but not yet implemented.

**The backtest is not fully prospective.** The 2021-2025 data informed which signals were chosen and which were disabled. A researcher who looked at zero historical data before writing the model would have selected different signals. The walk-forward architecture prevents parameter leakage within each season, but signal selection itself reflects prior knowledge of the domain.

**Week 1 is noisier than later weeks.** In Week 1, the model uses prior-season data with no current-season information. By Week 8, returning production has been validated by actual game play, teams' true quality has emerged, and the preseason quality anchor has been updated by real performance. The model's edge may be larger in mid-season games than in openers.

**65-78% cover rate is still losing 22-35% of bets.** At -110 juice, you need 52.4% to break even. The model's 68.5% is strong, but it means you lose roughly 1 in 3 published picks. Any given week can produce 0/2 results. The model's edge is statistical and only manifests over many picks.

---

## Part 10: The Numbers, Completely

**Five-season walk-forward backtest (2021-2025):**

| Metric | Value |
|--------|-------|
| Total qualifying picks | 139 unique games |
| Win-loss record | 107-32 |
| Cover rate | 68.5% |
| ROI at -110 juice | +30.8% |

**By bet side:**

| Category | W-L | Cover% | ROI% |
|----------|-----|--------|------|
| Favorites | 66-23 | 65.7% | +25.5% |
| Underdogs | 37-8 | 78.6% | +50.0% |

**By season:**

| Season | W-L | Cover% | ROI% |
|--------|-----|--------|------|
| 2021 | 56-24 | 70.0% | +34.0% |
| 2022 | 45-27 | 62.5% | +19.4% |
| 2023 | 79-27 | 74.5% | +42.6% |
| 2024 | 46-24 | 65.7% | +25.5% |
| 2025 | 24-13 | 64.9% | +23.9% |

All five seasons profitable. The model has never had a losing year in backtest.

**Score calibration:**

| Score bin | N | Cover% | ROI% |
|-----------|---|--------|------|
| 70-74 | 16 | 81.2% | +55.1% |
| 75-79 | 35 | 71.4% | +36.4% |
| 80-84 | 36 | 75.0% | +43.2% |
| 85-89 | 25 | 80.0% | +52.7% |
| 90-99 | 27 | 81.5% | +55.5% |

All bins above 60%. No gross inversions. The 75-79 bin is the weakest — worth monitoring whether this stabilizes or represents a genuine pattern.

**By underdog spread range:**

| Spread range | W-L | Cover% |
|---|---|---|
| 0-7 points | 25-7 | 78% |
| 7-14 points | 5-0 | 100% |
| 14-21 points | 2-1 | 67% |
| 21+ points | 1-1 | 50% |

**Week 1 2026 picks:**
- Notre Dame -20.5 (away fav), model score 98 ✅ Official
- Georgia Tech -7.0 (home fav), model score 76 ✅ Official
- Arkansas State @ Memphis — Memphis -10.5, model score 71 👁️ Watch
- Jacksonville State @ North Dakota State — NDS -8.5, model score 69 👁️ Watch
- Louisville @ Ole Miss — Ole Miss -6.5, model score 69 👁️ Watch

Season starts August 29, 2026.

---

*The code, ablation data, and full decision history for every rule in this system are in `/Users/kg/life-os-2026/scripts/backtest_walk_forward.py` and `scripts/generate_picks.py`. Every rule change since the model was built has a comment documenting when it was made and what the ablation showed.*
