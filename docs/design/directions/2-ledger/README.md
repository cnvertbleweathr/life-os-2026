# 2 · Ledger: the year as a balance sheet

**Idea.** Treat the year like an account you reconcile. The chrome has no colour at all: ink on white over a blue-grey ground. Every figure is set in Geist Mono so the numbers stack like a ledger's columns. The one hue (`#1d5fbf`) goes on the main data element only: on Home, the projection of where each goal lands by **Dec 31 at this year's rate**; on the slate, the cumulative-units line. The title row states one finding ("At this year's rate you finish 2 of 6 tracked goals"), and the primary action (Start check-in) is a near-black button in the top-right.

| | |
|---|---|
| **Palette** | Ground `#f2f4f7`, cards `#fff`, borders `#e3e6ea`. Ink `#0b0c0e`, muted `#5d636b`. One data hue `#1d5fbf`. Change signals: `#23744a` up and `#b8262c` down, used only on gaps and misses. |
| **Type** | Geist 400/500/600 for words (24px title, 16px card titles, 14px body). Geist Mono 500 for every figure (28px KPIs, tabular). |
| **Density** | Medium. Fluid canvas, 12 columns, 12px gap, 8px card radius. KPIs are one divided strip, not tiles. |
| **Motion** | None beyond press (`scale(.97)`) and 150ms hover tone steps. Charts are static. |
| **Shell** | Open plane: labelled sidebar on the ground, a grey pill for the active item, scope ("Karey · 2026") under the mark, sync status at the foot. The phone gets a bottom tab bar and two-line table rows. |

**Signature element:** *Where the year lands*. One row per wired goal: now (ink), projected by Dec 31 (blue), target (tick), with the gap signed. It's the single chart that answers "am I going to make it", and it replaces the wall of red "Behind 0%".

**How it fixes the top critique problems**

1. *Trust:* the backtest sits in a greyed KPI labelled "not this season". The listening goal reads from the Music mart, ending the Goals/Music contradiction. Totals reconcile (17 × 0.909 − 11 = +4.45; week 9: 3 × 0.91 − 2 = +0.73).
2. *Coaching:* each goal row carries "Needs 10.0 mi a week"-style sublines plus a signed gap.
3. *Legibility:* 12px is the floor, and muted text passes 4.5:1.
4. *States:* "No check-in yet" and a grey "–" for readiness, not a blank ring.
6. *IA:* "Due today" is one queue for the four habits, the check-in and capture.
7. *Density:* tables replace card feeds; the slate shows the graded week 9 alongside week 10.
9. *Colour:* one hue only, on data. Status colour appears only on misses.

**Trade-offs.** It's the most corporate of the five: it reads as a fintech dashboard. It's lightest on personality, so its brand rests on the mono figures and the projection chart. The taste gate warns that phone rows left-align numbers (a deliberate choice for two-line rows) and that the projection card has a band of space at desktop.

Files: `home.html`, `cfb.html`, `style.css`; screenshots `*-1440.png`, `*-390.png`.
