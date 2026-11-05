# 6 · Logbook Color: the chosen direction

**Brief from the pick.** Keep Logbook's layout: the L-frame, the white sheet, the week strip, "Goals on the clock" and the kickoff strip. It read as drab, so it borrows Pocket's colours: each life area gets its own tint. It also borrows Ops' light/dark switch.

## What changed from 3 · Logbook

- **One colour per life area, used the same way everywhere.** Each area has three values: a *tint* (the fill for marks and tiles), an *ink* (the text on that tint, at least 7:1 contrast) and a *mark* (the solid used for bars, dots and the lane's edge line).

  | Area | Light: tint / ink / mark | Dark: tint / ink / mark |
  |---|---|---|
  | Running (blue) | `#dcefff` / `#0a3a80` / `#2a6fd6` | `#142a45` / `#b8d8ff` / `#5d9ff2` |
  | CrossFit (amber) | `#fdecc8` / `#663a00` / `#c27a12` | `#352508` / `#f7d394` / `#e39d36` |
  | Reading (teal) | `#d4f2ea` / `#0b4840` / `#17907c` | `#0e302a` / `#a2e6d6` / `#33b89f` |
  | Habits (green) | `#e0f3d5` / `#1f4a12` / `#3f8f2a` | `#182c12` / `#c2e8ae` / `#63b549` |
  | Check-in and Capture (violet: things you write) | `#ebe5fc` / `#37217a` / `#6d4fd1` | `#251c42` / `#d2c6ff` / `#9479f2` |
  | Plans (rose) | `#fbe3ea` / `#6b1631` / `#c2456b` | `#371722` / `#ffc2d2` / `#e66b91` |
  | CFB (tangerine) | `#fde3cf` / `#6a2b06` / `#d9661c` | `#3a1f0c` / `#ffcca4` / `#f08a45` |

- **Where the colour goes:**
  - Lane labels on the week strip are tinted chips with a 3px mark edge.
  - Every mark in a lane takes that lane's tint. Solid marks are reserved for the week's big events: Ma's birthday and Saturday's picks.
  - "Missing" and "due" are dashed outlines in the lane's colour.
  - Goal rows have a colour dot, and their progress bars use the area colour on its own tint.
  - Today's habits and Capture are full tinted cards, Pocket's tile move on Logbook's card shape.
  - Sidebar icons carry their area's colour.
  - On the CFB page:
    - Underdog picks are tangerine and favourites are violet, consistently across the kickoff strip, the Side column and the score bars.
    - Season is a tangerine tile with a big unit total and a covered/missed stack for each week.
- **Forest stays the system colour.** It marks today's column, selection, focus, the active nav and tabs, and the sync dot. Area colours never do those jobs, so "today" and "selected" read the same on every page.
- **Light/dark theme:**
  - A button sits in the top bar (moon in light mode, sun in dark mode), and T is a shortcut.
  - The choice is saved in `localStorage` (`ons-theme`). With nothing saved, the page follows the OS setting.
  - The switch is instant, with no transition. `theme.js` runs in `<head>`, so the page doesn't flash the wrong theme on load.
  - Dark mode uses true near-black greens (ground `#0f1210`, sheet `#171b18`). The tints become deep fills with pale inks, so lanes still read as colour rather than grey.
  - In real code this becomes a `data-theme` attribute on `<html>`, with tokens defined twice in `globals.css` and Tailwind colours mapped to CSS variables.
- **A page intro, so the page doesn't open straight onto dates.**
  - Each page opens with a 30px title ("This week", "College football picks"), then a muted line giving the span it covers, then one coach-voice paragraph saying what matters.
  - Home adds four **next steps** in their area colours: check in, log 4 habits, get a CrossFit class in, finish book 8 by Nov 22.
  - The slate is titled **Degenerates Corner — College Football** (the sidebar group and breadcrumb match, ready for NBA/NHL to join). The system details from README/ROADMAP now live in the tiles.
  - The slate opens with a short title block (one sentence), then **four summary tiles**:
    - **Season so far** (tangerine): +4.45 u, 17–11 · 60.7% · ROI +15.9%, and covered/missed for each week.
    - **Where we are:** Week 10, a 14-segment season bar, and the Saturdays left.
    - **This week's run:** the pipeline as a checklist (Week 9 graded, lines pulled, picks set, Thursday briefing, games, graded), "3 of 6 done".
    - **The model:** 7 signals, walk-forward tested, 3 cut in the July audit, live PPA ratings, and the 70+ / 4+ bar.
  - The old Season card moved into the first tile. On phones the tiles become a swipeable row so the slate stays near the top.
  - A rule separates the intro from the data.
- **Phone fixes along the way:**
  - The kickoff strip turns into a list of games on phones, where it used to be an empty card.
  - Score bars keep the side's colour, so the side reads without the hidden Side column.
  - Marks and status pills wrap instead of truncating.

## Unchanged from Logbook

IBM Plex Sans and Plex Mono, the medium density, the 228px sidebar, the 48px top bar with ⌘K, the 16px sheet corners, press/hover-only motion and the bottom tab bar on phones. Fixes for critique problems 1, 2, 4, 5, 6, 7 and 10 carry over as described in `../3-logbook/README.md`.

## Trade-offs

- **Seven area hues is a lot.** They work because each one is tied to a lane and appears in the same place on every page. Adding an eighth area should reuse a hue, not invent one.
- **Violet does two jobs.** On Home it means "things you write" (check-in, capture); on the slate it marks favourite picks. The two never share a page. If that ever changes, favourites should move to a different hue.
- **Every colour in both themes needs checking whenever a token changes.** The ink-on-tint pairs here are all at least 7:1, and muted text is at least 4.5:1.

Files: `home.html`, `cfb.html`, `style.css`, `theme.js`; screenshots `{home,cfb}-{light,dark}-{1440,390}.png`. Open a page with `?theme=dark` or `?theme=light` to force a theme.

**Sample values in the tiles to confirm:**
- "Three more regular-season weeks through Nov 28; championship week Dec 5" comes from the calendar, not the API.
- The pipeline step times ("Tue 09:01", "Thursday briefing Nov 5") follow the cadence in the README; the API doesn't expose step status yet. A real version needs a small `/api/cfb/run-status` built from the daily-sync step logs.

**Inspector note:** at 390px the inspector flags the second tile touching the right edge. That peek is deliberate, to show the row swipes. Everything else passes in both themes.
