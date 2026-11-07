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

## Pixel scenes beside the title

Each page has a pixel-art loop in a right-hand column under the action buttons. It's up to 460px wide on desktop and a full-width banner on phones. The code is in `px.js`, built to the **pixel-art-sprites** skill (`.claude/skills/pixel-art-sprites`, a reviewed copy of omer-metin/skills-for-antigravity).

- **Characters.** 20×18 frames with a **6-frame run cycle**, as the skill recommends for runs: contact, down, float, then the same three mirrored.
  - Legs are hip → knee → foot, so knees bend: the front leg reaches, the back heel kicks, the knee drives through. Arms swing opposite the legs, and the body bobs 1px.
  - Frame times are 100ms for the run and 140ms for the jog.
- **No sliding.** The ground scrolls one foot-travel per frame: 4px on the field, 3px on the trail.
- **One outline rule.** Every character gets a generated 1px outer outline; scenery gets none. Light comes from the top-left.
- **Closed palette.** 56 `--px-*` colours per theme, within the skill's "expanded" range.
  - The silhouette test sent three characters to navy: the ball carrier's jersey, the referee's pants and the jogger's shorts all matched the outline colour and merged into it.
- **Integer scaling in device pixels.** Each art pixel lands on 3, 4 or 6 device pixels at 1×/1.25×, 1.5× and 2×.

**Degenerates Corner:**
- The stands have a bouncing crowd, a scoreboard showing the season record (17–11), and light towers at night.
- Coaches in headsets walk the sideline.
- The field has mown stripes, yard lines, hash marks and yard numbers.
- A referee trails a violet defender, who chases the tangerine ball carrier with the ball tucked.
- Every so often an end zone, pylons and a goalpost scroll in; crossing the goal line sets off confetti and "TD!".

**Weather (This week page):**
- **Weather lane.** The first lane of the week strip shows each day's icon, high/low and conditions. Clicking a day shows its conditions in the title scene; today is selected on load.
- **Coach line.** The intro paragraph uses the forecast: snow Friday, so run before Thursday's rain; Saturday sunny but cold.
- **Sample forecast for Denver (to replace):**

  | Day | Conditions | High/low |
  |---|---|---|
  | Mon | Sunny | 63/36 |
  | Tue | Partly cloudy | 58/33 |
  | Wed | Windy, gusts 35 | 55/30 |
  | Thu | Rain, then a mix | 44/29 |
  | Fri | Snow, 2–4 in. | 34/22 |
  | Sat | Sunny, cold | 41/20 |
  | Sun | Sunny | 50/27 |

- **Real version.** ONS has no weather source yet. Open-Meteo (free, no key) can serve the daily forecast and current conditions for Denver; `MIGRATION.md` notes there's no stored lat/long, so add one. The scene reads `data-wx` (`sun`, `partly`, `cloudy`, `wind`, `rain`, `snow`) and `data-temp`.

**This week:**
- A jogger in running blue on a trail with the pack:
  - the black dog (red collar), the chihuahua-beagle (tiny, tri-colour, tall ears) and the puggle (stocky, dark pug muzzle) run alongside;
  - the brown tabby and the gray striped cat trot behind.
- **The scene follows the weather:**
  - clear and partly cloudy: sun and clouds;
  - windy: fast clouds, blowing leaves, swaying trees;
  - rain: overcast sky, falling drops, puddles on the trail;
  - snow: overcast sky, falling snow, snow on the peaks, hills, trees, trail and mile markers.
  - The temperature sits in the top-left corner. At night the dark theme adds the moon, and stars when the sky is clear.
- Behind them: the Rockies with snowcaps, rolling hills, trees, drifting clouds and birds.
- The trail has wildflowers on the verge and numbered mile markers.
- There's a sun by day and a moon with stars at night.

**Motion rules.** These break CLAUDE.md's "quiet on daily screens" default because the owner asked for them. To keep them quiet anyway:
- They draw only when the frame changes.
- They stop when scrolled offscreen or when the tab is hidden.
- Clicking a scene pauses every scene. The choice is saved as `ons-px-paused`.
- With `prefers-reduced-motion` on, each scene shows a still frame and the button is disabled.

**Ideas for the other pages** (Fitness, Reading, Music, King Gizzard and Sports are built in `web/lib/pixelScenes.js`, with real data: see DESIGN.md → Pixel Scenes):

| Page | Loop |
|---|---|
| Habits | A little gardener waters a row of four sprouts, one per habit; a sprout blooms when it's ticked |
| Check-in | A figure at a desk writes in a journal by lamplight |
| Capture | A figure with a butterfly net catches falling notes |
| Goals | A climber works up a switchback toward a flag |
| Fitness | A lifter does a barbell squat, with chalk dust on the rep |
| Reading | A reader in an armchair turns pages, with a cat on the armrest |
| Music | A record spins while a listener in headphones nods along |
| King Gizzard | An original pixel lizard in a wizard hat plays a tiny flute |
| Sports | A hockey player skates past and taps a puck into the net |
