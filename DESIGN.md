---
name: ONS — Operating Narcisystem
description: A personal operating dashboard for life tracking and CFB analytics, organised around the week, coloured by life area, in light and dark.
colors:
  frame: "#edf1ee"
  sheet: "#ffffff"
  raised: "#f4f6f4"
  active: "#dfe7e1"
  border: "#e1e6e2"
  rule: "#edf0ed"
  control: "#c6cdc7"
  ink: "#141714"
  ink-2: "#2c312c"
  muted: "#596059"
  forest: "#1f6b46"
  forest-soft: "#e1efe6"
  neg: "#b3262b"
  run: "#dcefff"
  run-ink: "#0a3a80"
  run-mark: "#2a6fd6"
  lift: "#fdecc8"
  lift-ink: "#663a00"
  lift-mark: "#c27a12"
  read: "#d4f2ea"
  read-ink: "#0b4840"
  read-mark: "#17907c"
  habit: "#e0f3d5"
  habit-ink: "#1f4a12"
  habit-mark: "#3f8f2a"
  check: "#ebe5fc"
  check-ink: "#37217a"
  check-mark: "#6d4fd1"
  plan: "#fbe3ea"
  plan-ink: "#6b1631"
  plan-mark: "#c2456b"
  edge: "#fde3cf"
  edge-ink: "#6a2b06"
  edge-mark: "#d9661c"
  wx: "#e6ebf2"
  wx-ink: "#263247"
  wx-mark: "#5b6f8f"
typography:
  page-title:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "30px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  lede:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.56
  card-title:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.375
  body:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.43
  label:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.33
  tile-figure:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "26px"
    fontWeight: 600
    lineHeight: 1.23
  numeric:
    fontFamily: "IBM Plex Mono, ui-monospace, monospace"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  sheet: "16px"
  card: "8px"
  control: "6px"
  mark: "5px"
  pill: "4px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  gap: "24px"
  page-x-phone: "16px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.sheet}"
    rounded: "{rounded.control}"
    padding: "0 12px"
    height: "32px"
    typography: "{typography.body}"
  button-secondary:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 12px"
    height: "32px"
  card:
    backgroundColor: "{colors.sheet}"
    rounded: "{rounded.card}"
    padding: "20px"
  card-tinted-habit:
    backgroundColor: "{colors.habit}"
    textColor: "{colors.habit-ink}"
    rounded: "{rounded.card}"
    padding: "20px"
  sheet:
    backgroundColor: "{colors.sheet}"
    rounded: "{rounded.sheet}"
    padding: "24px"
  nav-item:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.control}"
    padding: "0 10px"
    height: "32px"
  nav-item-active:
    backgroundColor: "{colors.active}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 10px"
    height: "32px"
  lane-label-run:
    backgroundColor: "{colors.run}"
    textColor: "{colors.run-ink}"
    rounded: "{rounded.control}"
    padding: "0 10px"
  mark-run:
    backgroundColor: "{colors.run}"
    textColor: "{colors.run-ink}"
    rounded: "{rounded.mark}"
    padding: "4px 7px"
  pill-status:
    rounded: "{rounded.pill}"
    padding: "0 8px"
    height: "20px"
    typography: "{typography.label}"
  input:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 10px"
    typography: "{typography.body}"
---

# Design System: ONS (Logbook Color)

## Overview

**Creative North Star: "The Logbook"**

ONS is a logbook for one person's year, and the week is the unit. Days are noisy and years are abstract; a week is the span you can steer. Home is the week itself, a strip of days across with the owner's lanes down the side (weather, running, CrossFit, habits, check-in, plans, CFB), so "what's left this week" is visible as empty cells. Every page opens with a plain title, the span it covers and one coach-voice paragraph, then the data.

Each life area owns a colour and keeps it everywhere: running is blue, CrossFit amber, reading teal, habits green, things you write violet, plans rose, CFB tangerine, weather slate. Forest is the system's own voice: today, selection, focus. The colour is there to find things fast, not to decorate. The UI comes in light and dark, following the device until the owner picks.

Most ONS surfaces are **Operate** surfaces: dashboards, slates, trackers and forms used every day. Read-heavy pages such as briefs, reviews and postmortems are **Read**. Precision, density and scanability outrank expression. The one deliberate indulgence is a small pixel-art scene beside each page title, which the owner asked for. It is the only thing on a page that moves, and it follows strict rules (see Pixel Scenes).

Tokens live in `web/app/globals.css` (CSS variables for both themes) and `web/tailwind.config.js` (Tailwind names mapped to those variables). The visual reference for pages not yet rebuilt is the static mockup in `docs/design/directions/6-logbook-color/`. The pixel scene engine is `web/lib/pixelScenes.js`, wrapped by `web/components/ui/PixelScene.tsx`.

**Key Characteristics:**
- A tinted L-frame (sidebar and 48px top bar) holding the work on a white sheet with 16px corners
- The week strip: lanes by days, today marked by forest lines, missing items as dashed outlines
- One colour per life area, as a tint, an ink and a mark, used the same way on every page
- Forest for the system's own states only: today, selection, focus, active nav
- Light and dark themes from one token set, switched instantly
- IBM Plex Sans for words, IBM Plex Mono for figures in tables and marks
- Flat: borders and tints, no shadows
- A pixel-art title scene per page, the one moving thing

## Colors

Neutrals are a faintly green grey taken from the forest. Area colours come in threes. The tables give light values; dark values follow.

### System
- **Frame** (`frame`): the L-frame (sidebar and top bar) ground. Dark `#0f1210`.
- **Sheet** (`sheet`): the work surface and cards. Dark `#171b18`.
- **Raised** (`raised`): hover fills and neutral marks. Dark `#1f2420`.
- **Active** (`active`): the active nav item. Dark `#253029`.
- **Border / Rule / Control** (`border`, `rule`, `control`): card borders, rows inside a card, and input or button outlines. Dark `#2a312c`, `#222823`, `#3b443d`.
- **Ink / Ink 2 / Muted** (`ink`, `ink-2`, `muted`): primary text, secondary text, metadata. Dark `#edf1ee`, `#d3d9d4`, `#9ea7a0`. Muted stays at 4.5:1 or better on the sheet in both themes.
- **Forest** (`forest`): today's column and header, the selected tab underline, the focus ring, selection, the active nav icon, the sync dot, links in tiles. Dark `#5cc290`. **Forest Soft** (`forest-soft`) washes today's column. Dark `#17301f`.
- **Primary button:** ink on light (`#141714` with white text), inverted on dark (`#edf1ee` with `#111411` text).
- **Negative** (`neg`): signed losses only. Dark `#ff8a8f`.

### Life areas (tint / ink / mark)
The *tint* fills lane labels, marks and tinted cards. The *ink* is text on that tint, at 7:1 or better. The *mark* is the solid used for bars, dots, lane edges and icons.

| Area | Light tint / ink / mark | Dark tint / ink / mark |
|---|---|---|
| Running (`run`) | `#dcefff` / `#0a3a80` / `#2a6fd6` | `#142a45` / `#b8d8ff` / `#5d9ff2` |
| CrossFit (`lift`) | `#fdecc8` / `#663a00` / `#c27a12` | `#352508` / `#f7d394` / `#e39d36` |
| Reading (`read`) | `#d4f2ea` / `#0b4840` / `#17907c` | `#0e302a` / `#a2e6d6` / `#33b89f` |
| Habits (`habit`) | `#e0f3d5` / `#1f4a12` / `#3f8f2a` | `#182c12` / `#c2e8ae` / `#63b549` |
| Things you write: check-in, capture (`check`) | `#ebe5fc` / `#37217a` / `#6d4fd1` | `#251c42` / `#d2c6ff` / `#9479f2` |
| Plans (`plan`) | `#fbe3ea` / `#6b1631` / `#c2456b` | `#371722` / `#ffc2d2` / `#e66b91` |
| CFB / Degenerates Corner (`edge`) | `#fde3cf` / `#6a2b06` / `#d9661c` | `#3a1f0c` / `#ffcca4` / `#f08a45` |
| Weather (`wx`) | `#e6ebf2` / `#263247` / `#5b6f8f` | `#1d2433` / `#c5d0e3` / `#7f95ba` |

### Status pills
On track `#d9f2e2`/`#0d3a22`, at risk `#fff0d6`/`#7a430a`, out of reach `#fde6e6`/`#7d1c20`, not wired `#eef0ee`/`#3e443e`. Dark: `#143222`/`#a9e9c4`, `#382810`/`#f6cf8b`, `#3d191c`/`#ffb8bb`, `#232924`/`#c3cac4`.

### Named Rules
**The One Lane, One Colour Rule.** An area's colour means that area, everywhere: lane label, marks, goal bar, tinted card, nav icon. Don't reuse an area hue for something unrelated. The one sanctioned overlap is violet: "things you write" on Home and "favourite picks" on the slate, which never share a page. Adding a ninth area reuses a hue or gets an explicit decision; it never gets a new hue invented on the spot.

**The Forest Is The System Rule.** Forest marks what the system knows about you right now: today, selected, focused. Area colours never do those jobs.

**The Two Themes, One Token Rule.** Every colour exists as a token in both themes. Never hard-code a hex in a component; a colour that only works in one theme is a bug.

## Typography

**Sans:** IBM Plex Sans 400/500/600 (system-ui fallback)
**Mono:** IBM Plex Mono 400/500 (ui-monospace fallback)

**Character:** an engineer's notebook. Plex is plain and legible at small sizes, and its mono stacks figures cleanly in tables.

### Hierarchy
- **Page title** (Sans 600, 30px/36px, −0.01em; 26px on phones). An optional lighter second part ("Degenerates Corner — College Football") is Sans 400 in Muted, and drops to its own line at 20px on phones.
- **Span line** (14px, Muted): the dates or week the page covers, directly under the title.
- **Lede** (16px/25px, Ink 2, max 68ch): one coach-voice paragraph. **Bold** marks the two or three facts that matter.
- **Card title** (Sans 600, 16px/22px), with an aside in 13px Muted on the right.
- **Body** (14px/20px). Table rows, nav and controls.
- **Label** (12px, Muted): table headers, legends, tile labels (13px). Sentence case. No tracked caps anywhere.
- **Tile figure** (Sans 600, 26px/32px; Mono when it's a signed number such as `+4.45 u`).
- **Numeric** (Mono 12–14px, tabular): figures in tables, marks, kick times, lines.

### Named Rules
**The No Micro-Caps Rule.** Nothing is uppercase and tracked. Labels are sentence case at 12px or more.

**The Mono Counts Rule.** Figures that line up in columns or marks are Plex Mono. Words are Plex Sans.

## Layout

**The L-frame.** A 228px sidebar and a 48px top bar share the Frame ground. The work sits on a white Sheet inset 8px from the right and bottom, with 16px corners and a 1px border. The top bar holds the breadcrumb, a centred "Ask the system ⌘K" field, the sync status and the theme switch.

**Sidebar groups:** Today (This week, Habits, Check-in, Capture), Track (Goals, Fitness, Reading), Degenerates Corner (College Football; NBA and NHL join later), Play (Music, King Gizzard, Sports). Area pages show their area's mark on the nav icon.

**Page anatomy:**
1. **Intro:** a title, span line and lede on the left; on the right, the page actions above the pixel scene (up to 460px wide). Home adds a row of up to four **next steps** in area colours. A 1px rule closes the intro unless summary tiles follow.
2. **Summary tiles** (where a page has them, as on Degenerates Corner): four tiles in a row (`1fr 1fr 1.25fr 1fr`).
3. **Tabs**, if the page has sub-views (2px forest underline).
4. **A 12-column grid** with a 24px gap: a full-width signature block (the week strip, the kickoff strip), then an 8/4 split.

**Phones (<768px):**
- The frame drops away and the sheet goes edge to edge with 16px padding.
- The pixel scene becomes a 64px banner above the title, and the actions follow the lede.
- Grids go to one column. Summary tiles become a swipeable row (84% wide, with the next one peeking in).
- The week strip scrolls sideways inside its card.
- A bottom tab bar (Week, Habits, Check-in, Capture, More) with a 2px forest line over the active tab. 92px of bottom padding clears it.

**Tablet (768–1100px):** blocks go full width, the intro stacks, and the week strip scrolls sideways.

## Elevation & Depth

Flat. Depth comes from the Frame → Sheet step, 1px borders and area tints. There are no drop shadows anywhere, including menus and popovers, which take a border.

- **Focus:** 2px forest outline, 2px offset. Inputs add a 3px ring in their tint or forest at 14–22% alpha.
- **Today:** 1px forest lines on both sides of today's column, a 3px forest cap on its header, and a Forest Soft wash.
- **Selected weather day:** a 1px outline in the weather mark, not a shadow.

**The Flat Sheet Rule.** If something needs to stand apart, give it a tint or a border. Never a shadow.

## Shapes

- **Radii:** sheet 16px; cards and tiles 8px; buttons, inputs, nav items and lane labels 6px; marks 5px; status pills and chips 4px.
- **Borders:** always 1px. Area edges are 3px inset bars in the mark colour (lane labels, kickoff bars, next-step cards).

## Components

### Buttons
32px high, 6px radius, Sans 500 at 13px. **Primary** is ink-filled (inverted in dark). **Secondary** is a sheet fill with a Control border. Inside a tinted card, primary takes that card's ink. Press is `scale(.97)` over 120ms and hover is a background change over 150ms. Nothing else moves.

### Cards
Sheet fill, 1px border, 8px radius, 20px padding (16px on phones). **Tinted cards** (Today's habits in green, Capture in violet, the Season tile in tangerine) drop the border and take the area tint, with the area ink for all text and a darker wash of the ink for rules.

### The week strip (signature)
- A grid of a 128px lane column plus seven day columns.
- **Lane labels** are tinted chips with a 3px mark edge.
- **Cells hold marks:** tint fill with the area ink; *solid* (mark fill) for the week's big events only; *outlined* for planned; *dashed* for missing or due ("Not logged", "Due").
- **Habit dots:** 12px squares outlined in the habit mark, filled when done.
- **Weekend columns** take a faint wash.
- **The Weather lane** comes first. Each day is a button showing icon, high/low and conditions; pressing it previews that day in the title scene.

### Goals on the clock
A table of goal, progress bar, "Needs" (the rate required) and state pill. Each goal has a colour dot, and its bar is the area mark on the area tint, with a 2px ink tick for "today". "Not wired" is a state of its own, never "behind". "Out of reach" always comes with an explanation.

### Summary tiles
A 13px label, a 26px figure, a short line, then one visual: a per-week chart, a season bar, a pipeline checklist (green check circles for done, dashed circles for to-do, with right-aligned mono detail) or a link.

### Kickoff strip (CFB signature)
Games on a 9 am–midnight axis. Each bar is a tint with a 3px mark edge: tangerine for underdog picks, violet for favourites. Labels on the left give pick and line. On phones it becomes a list. The picks table repeats the side colour in its Side chip and score bar.

### Status pills
20px high, 4px radius, 12px Sans 500. They wrap to two lines on phones rather than truncating.

### Inputs
A sheet fill with a 1px border (Control, or a wash of the tint inside tinted cards), 6px radius, 14px text (16px on phones). Focus adds a ring in the card's mark.

### Navigation
Sidebar items are 32px with a 16px icon. The active item gets the Active fill, Ink text at 500 weight and a forest icon. The phone tab bar is described under Layout.

### Theme switch
A 32px square button in the top bar: a moon in light mode, a sun in dark. T toggles it. The choice is saved (`ons-theme`); with nothing saved, the page follows `prefers-color-scheme`. A head script sets the theme before paint, so there's no flash, and the switch is instant with no transition.

## Pixel Scenes

One small looping pixel-art scene sits beside each page title. Scenes are built to the **pixel-art-sprites** skill (`.claude/skills/pixel-art-sprites`). The reference implementation is `px.js`.

- **Size:** a canvas 32 art-pixels tall, as wide as its box. Up to 460px wide on desktop; a 64px banner on phones.
- **Integer scaling in device pixels**, with `image-rendering: pixelated`. Never a fractional scale.
- **Characters:** 20×18 frames. Runs use 6 frames (contact, down, float, mirrored), with hip → knee → foot legs, arms opposite the legs and a 1px bob. Animals and small props use 2-frame gaits.
- **No sliding:** the ground scrolls exactly one foot-travel per frame.
- **One outline rule:** every character gets a generated 1px outer outline; scenery gets none. Light comes from the top-left.
- **Closed palette:** `--px-*` tokens in both themes, separate from UI tokens. A character's fill never matches the outline colour (the silhouette test).
- **Content:** the scene is about the page and uses its real data where it can:
  - the season record on the CFB scoreboard;
  - today's weather and temperature on This Week;
  - the owner's own pets (a black dog, a chihuahua-beagle, a puggle, a brown tabby, a gray striped cat).
- **Motion rules:**
  - Draw only when the frame changes.
  - Stop when scrolled offscreen or when the tab is hidden.
  - Clicking a scene pauses all scenes, and the choice is saved (`ons-px-paused`).
  - Under `prefers-reduced-motion`, show a still frame and disable the button.
  - Nothing else on the page animates.

## Do's and Don'ts

### Do:
- **Do** open every page with a title, a span line and one coach-voice paragraph before any data.
- **Do** colour by life area, using the tint, ink and mark the same way on every page.
- **Do** reserve forest for today, selection, focus and the active nav.
- **Do** define every colour in both themes, and check both themes at 1440 and 390 before calling a page done.
- **Do** show missing, due, stale and "not wired" as designed states (dashed outlines, explicit pills), never as blanks.
- **Do** label backtest figures as backtest and keep them apart from live results.
- **Do** keep scenes to the Pixel Scenes rules, and grow a scene with things from the page's own world.

### Don't:
- **Don't** add drop shadows to anything.
- **Don't** invent a new hue for an area, or use an area colour for something unrelated.
- **Don't** use uppercase tracked labels or text under 12px.
- **Don't** animate data, keyboard actions, the slate or habit check-ins. The pixel scene is the only motion besides 120–150ms press and hover feedback.
- **Don't** scale pixel art by fractions, smooth it, or give a character a fill that matches its outline.
- **Don't** hard-code a colour that only works in one theme.
