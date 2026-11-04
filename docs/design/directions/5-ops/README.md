# 5 · Ops: the dark terminal

**Idea.** ONS really is a data system (pipelines, marts, a model), so let its home look like the console for one. Home is a **status board**: a strip of readings; goal *monitors* that compare the rate needed against the rate this year and report `ok`, `behind`, `out of reach` or `not wired`; a keyboard-driven queue for today (1–4 tick habits, C opens check-in, and a `capture ›` prompt); and a **Sources** panel showing the newest record per pipeline. That panel surfaces something no other screen does: SugarWOD's newest record is Oct 27, so "0 CrossFit this week" may be stale data rather than a missed week. The slate is a dense table with model gaps from our side, signed weekly units, and the watch list just under the bar.

| | |
|---|---|
| **Palette** | Ground `#161718`, cards `#111213` (darker than the ground), borders `#26272a`. Text `#f2f2f3`, muted `#9a9ca2`, dim `#8a8c92` (all at least 4.5:1). One accent, phosphor green `#4fbf86`, used for selection lines and as the positive sign. Negative `#ef6b81`, warning `#dcaa4a`. True neutrals: no navy, no slate. |
| **Type** | Public Sans 400–700 for words (24px title, 14px card titles, 13px body). JetBrains Mono for every figure, time and key hint, chosen so digits stack. |
| **Density** | High. 34px table rows, 16px gaps, a 56px icon rail instead of a sidebar, 6px corners. |
| **Motion** | None, deliberately. Every selection (rail item, tab, phone tab) is a static 1px green line. Nothing pulses or animates, and the live dot goes too: on a console, motion reads as an alert. |
| **Shell** | Icon rail with tooltips and accessible names, grouped by hairlines (today / track / edge / play). The phone gets a bottom tab bar with a 1px accent line over the active tab, and wide tables scroll inside their cards. |

**Signature element:** *Sources.* A freshness table for the life pipeline. It answers the question underneath every number on the site: can I trust this?

**How it fixes the top critique problems**

1. *Trust:* the Sources panel, plus explicit `not wired` and `out of reach` states. The backtest is greyed and labelled "reference only". Weekly units carry a note that they're rounded (+4.453 before rounding).
2. *Coaching:* the monitors' Need and Doing columns. The finding line names the one thing to check.
3. *Legibility:* the floor is 11px for key hints and 12–13px for data, and no text falls under 4.5:1 on the dark surfaces.
4. *States:* "no check-in", "–" for readiness, and the stale-data warning are all designed.
7. *Density:* the slate shows nine columns of model detail plus the watch list on one desktop screen.
9. *Colour:* green appears only for selection and positive signs; red and amber only on states.

**Trade-offs.** Dark-only. It's the hardest to read in daylight on a phone, and the icon rail costs recognition (tooltips stand in for labels). It's the most "engineer's tool" in feel, which is either its point or its problem. The taste gate warns there's no hue on the chart data (the style's rule is signs, not colour) and that much of the phone text sits under 13px.

Files: `home.html`, `cfb.html`, `style.css`; screenshots `*-1440.png`, `*-390.png`.
