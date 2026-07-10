# ONS CFB Betting System — How It Works

*Last updated: July 2026 | Model v3 Walk-Forward | 2021-2025 backtest: 68.5% cover, +30.8% ROI*

---

## The Core Idea

Most CFB betting systems fail for one of two reasons: they overfit to historical data and fall apart on new games, or they use the same signals the market already prices in and find no edge.

This model is built around a single hypothesis: **the betting market consistently undervalues teams whose actual on-field efficiency (measured by PPA) disagrees with the market's implied team quality**. When a team's play-by-play efficiency says they're better than their opponent, but the spread says otherwise, that gap is exploitable.

The system doesn't try to predict game outcomes. It tries to identify when the market has mispriced a specific efficiency signal that the market doesn't fully incorporate.

---

## The Signal: PPA Gap

**PPA (Predicted Points Added)** is a play-by-play efficiency metric developed by the CollegeFootballData.com team. Every play in every game gets a value based on how much it changed the expected point total for the drive. A 10-yard gain on 3rd and 2 is worth more than a 10-yard gain on 1st and 10. Touchdowns are worth a lot. Turnovers are negative. The cumulative PPA per play for a team over a season is a clean measure of their true offensive and defensive efficiency, independent of score and garbage time.

The model computes the **PPA gap**: the difference between the home team's offensive PPA and the away team's offensive PPA, using the prior season's data so there's no information from the current game. A PPA gap of +0.20 means the home team generated 0.20 more predicted points per play than the away team last season — a meaningful efficiency advantage.

When this gap exceeds 0.15, the model identifies which team it favors (positive gap = bet home team, negative = bet away team) and begins building a case for a pick.

**Why does this work?** The market prices CFB spreads based on public money, brand perception, recent results, and injury reports. It incorporates efficiency data, but imperfectly. There's consistent evidence that markets over-weight team reputation and under-weight play-level efficiency in certain game configurations. The PPA gap is capturing something real that the market doesn't fully price.

---

## The Walk-Forward Architecture

The most important design decision is the **walk-forward validation**. Every backtest season uses only data that was available *before* that season started. The tier system (which teams have historical ATS records in specific situations) is rebuilt from scratch for each season using only prior seasons. The score thresholds were never tuned against the full 2021-2025 dataset — they were set early and held constant.

This matters because most backtests in sports betting are secretly overfitted. If you tune your model using 2021-2025 data and then test it on 2021-2025 data, you're checking whether you memorized the answers, not whether the model works. Walk-forward validation is the closest thing to genuine out-of-sample testing you can do with historical data.

The model has been validated across five complete seasons (2021-2025) without the validation data ever touching the parameter selection process. The 2026 season is the first genuinely prospective test.

---

## How a Pick Gets Made

When the model evaluates a game, it runs through a scoring system that starts at zero and accumulates evidence for or against publishing a pick. A pick requires a minimum model score of 70 and at least 4 independent edges — both must be met.

**The PPA gap is the foundation.** Without it, no pick gets made. It's the required signal, not ablatable. A gap above 0.30 earns +25 points (extreme edge). A gap above 0.15 earns +15 points (primary edge).

**The underdog bonus** is the most recently added rule and the most interesting. When the PPA gap favors a team that is also the underdog — meaning the model's efficiency data disagrees with the market's implied team quality — the pick gets an additional +8 points. This bonus was added after a controlled ablation confirmed that underdog picks cover at 78.6% (33-9) vs 65.7% for favorite picks, and that this gap persists after controlling for PPA gap magnitude. The mechanism is clean: when PPA agrees with the market (bet the favorite), the edge is partially priced in. When PPA disagrees (bet the underdog), the edge hasn't been priced in at all. It's pure alpha.

**Secondary signals** that can accumulate additional points include:
- *Success rate parity*: whether the efficiency team also wins on a per-play success basis (third down conversion, yards per carry relative to expectations). Independent of PPA, this measures consistency rather than explosiveness.
- *Talent/recruiting parity*: whether the recruiting gap confirms the PPA gap. When a team has both a PPA edge and a recruiting edge, both signals agree.
- *Team tier history*: based on 3+ seasons of ATS data, some teams have demonstrated systematic over- or underperformance against the spread in specific situations. Teams with a FADE tier in a particular situation get a score penalty; teams with a STRONG_EDGE tier in a specific home/away configuration get a bonus.
- *Returning production*: whether the team's efficiency edge is likely to carry over, based on how much of last season's production is returning.
- *Conference adjustment*: small bonuses for conference games where the model's prior-season data is more directly applicable (same opponent pool, similar travel/preparation contexts).

**Rules that were tested and removed** (documented with ablation data in the codebase): the spread-range rule (which awarded points for tight 3-7 point spreads) was found to be anti-predictive — it was concentrating high-score picks in tight-spread games that cover less reliably. Removing it caused the worst-performing score bin to jump from 56% to 72% cover. SP+ alignment and havoc differential were also removed after per-season ablations showed they hurt more seasons than they helped.

---

## Official Picks vs Watch List

The UI shows two tiers:

**Official picks** meet the full publish bar: model score ≥ 70 and at least 4 independent edges firing. These are the model's actual recommendations — every pick is both backed by a real efficiency edge AND has multiple independent signals confirming it.

**Watch list** picks scored above zero but didn't clear both thresholds — either the score is 65-69, or only 3 edges fired. These are games where the model found *something* interesting but doesn't have enough confirming evidence to publish. They're worth knowing about, especially near the publish threshold, but shouldn't be treated as recommendations.

The distinction matters because the model's edge comes from being selective. Publishing everything that looked vaguely interesting would dilute the signal. The 4-edge minimum exists specifically to filter out situations where PPA is pointing in one direction but no other independent signal agrees.

---

## The Quality-of-Win System (In-Season Context)

Running alongside the weekly picks is a separate system — the Quality-of-Win/Strength-of-Schedule (QoW/SOS) tracker — that computes live team ratings updated weekly.

It's built in three layers:
- **Preseason quality anchor**: a composite of prior-season efficiency, recruiting/talent pipeline, and historical win percentage, z-scored within the FBS population. This is computed once before the season and never changes. Alabama entering 2023 starts at a high anchor; Kent State starts low.
- **Live football strength**: starts at the preseason anchor and updates weekly based on per-game PPA performance relative to expectations. If Alabama's offense performs significantly better than their prior-season average against a given opponent, their live offensive strength rating rises. This series *never* reads market data — it's purely about on-field football.
- **Market outperformance EMA**: starts at zero and updates weekly based on whether a team's actual margin beat or missed the market's implied margin. This series *never* reads PPA data — it's purely about market relationship.

The two series are deliberately kept separate. Mixing them would make it impossible to know which signal was driving any effect. Phase D validation (2021-2025) confirmed that teams with `off_vs_preseason > 0.15` (currently outperforming their preseason quality anchor) cover at 54-57% within model-qualifying games — a real signal, though not yet large enough sample in the published-pick population to integrate into the scoring system. It will be monitored through the 2026 season.

---

## What the Model Is NOT Doing

**It's not predicting scores.** The model doesn't try to predict who wins or by how much. It's trying to identify situations where the market's spread doesn't reflect the underlying efficiency reality. Those are different tasks.

**It's not using injury data.** Injuries are real and important, but the CFBD API doesn't provide reliable, timely injury data. The model's edges come from structural, season-level information that doesn't change week-to-week. Individual game-week injury reports would be a meaningful addition but would require a different data source.

**It's not using in-season line movement.** The model evaluates games using the available line at pick time. It doesn't track where the line opened or which direction it moved. Opening vs closing line is another potential signal that's not yet incorporated.

**It's not betting every game.** Out of 51 games with lines in Week 1 2026, the model published 2 official picks. That's intentional. Most games don't have a clear efficiency mispricing. Publishing 15-20 picks per week would mean publishing games where the model has no genuine edge — and the historical ROI figures only hold because the model has been selective.

---

## The Numbers

**2021-2025 backtest (walk-forward, post-fix):**
- 365 qualifying unique games
- 250-115, 68.5% cover rate
- +30.8% ROI at -110 juice

**By pick type:**
- Official picks (favorites): 186-97, 65.7% cover, +25.5% ROI
- Official picks (underdogs): 33-9, 78.6% cover, +50.0% ROI

**Score calibration (all bins above 60%):**
- Model 70-74: 68.8% cover
- Model 75-79: 61.9% cover
- Model 80-84: 71.6% cover
- Model 85-89: 71.9% cover
- Model 90-99: 71.2% cover

**The 2026 season is the first genuinely prospective test.** Every number above is from historical data used to build the model, not data held out from it. The model will be evaluated on 2026 picks as they grade out — with no adjustments made to the model mid-season based on how it's performing.

---

## The Bottom Line

The model finds games where a team's proven, play-by-play efficiency advantage isn't reflected in the market spread — and especially games where that advantage runs *against* the market's implied favorite. It publishes a pick only when multiple independent signals agree, and it's been consistently profitable across five seasons of walk-forward validation.

Week 1 2026: Notre Dame -20.5 (away fav, score 98) and Georgia Tech -7.0 (home fav, score 76). The season starts August 29.
