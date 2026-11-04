# 1 · Almanac II: the evolved Almanac

**Idea.** Keep what already works (the masthead sentence, the ruled stat band, forest on cream) and fix the system around it. The masthead does the coaching: one sentence of what happened, then one sentence of what it means for the year ("That's the pace 350 needs… CrossFit is the slipping one"). Inputs move onto Today, so habits and the three key check-in ratings are tappable without leaving the page. Every goal shows the rate it *needs* beside the rate you're *doing*, and the clerk's small caps are gone: labels are sentence case, at 12–13px, in a darker Muted.

| | |
|---|---|
| **Palette** | Canvas `#f6f5f2`, recess `#efebe1`, surface `#fbfaf5`. Ink `#232a22`. Muted darkened to `#5d584a` (6.3:1 on surface). Forest `#1d5536` is the only accent. Ochre `#85570f` and brick `#a3402f` are status only, with pale washes for pills. |
| **Type** | Spectral 600 for the masthead (42px) and band figures (32px). Spline Sans 14–16px for text. Spline Sans Mono for figures only, never for labels. No tracked uppercase anywhere. |
| **Density** | Medium. A 1100px centred column on a 12-column grid (77px × 12 + 16px gutters). The stat band as before, then 8/4 stacks. |
| **Motion** | Press feedback only (`scale(.97)`, 120ms ease-out) and 150ms colour transitions on hover. No entrance animation (the old `ons-rise` page animation is dropped), and nothing moves when data updates. Respects `prefers-reduced-motion`. |
| **Shell** | Labelled sidebar on the recess tone, regrouped by job: **Today** (Today, Habits, Check-in, Capture), **Track** (Goals, Fitness, Reading), **Edge**, **Play**. The active item is a tone-step pill, with no left bar. The phone bottom tab bar is kept. |

**How it fixes the top critique problems**

1. *Trust:* the stat band shows CFB **live** units (17–11, +4.45 u); the backtest appears only in a labelled footnote. Unwired goals are left off the pace table and counted in a note, never shown as "Behind".
2. *Coaching:* the masthead's second sentence and the "Needs / Doing" columns answer "what next".
3. *Legibility:* the smallest text is 12px, the lowest text colour passes 4.5:1, and there are no 8–9px mono labels.
5. *Phone:* habits and check-in sit right after the band. Check-in buttons are 44px.
6. *IA:* one place to tick habits (Today); the nav is grouped by job.
7. *Density:* the slate is a ruled table with kickoff times. Six picks fit in about 600px instead of 1,150px.
8. *Machine voice:* signal keys are rewritten ("Underdog edge · efficiency gap 0.25"), and the line is always shown from our side.

**Trade-offs.** It is still Almanac: three typefaces, a serif headline larger than the app-screen norm (42px), and a cream ground. The taste gate flags all three as warnings; they're kept on purpose as the brand. It's the lowest-risk direction and the least new.

Files: `home.html`, `cfb.html`, `style.css`; screenshots `*-1440.png`, `*-390.png`.
