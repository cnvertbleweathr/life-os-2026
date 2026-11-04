---
name: ONS — Operating Narcisystem
description: A personal operating dashboard for life tracking and CFB analytics, set like an almanac.
colors:
  forest: "#1d5536"
  forest-bright: "#2f6b43"
  forest-wash: "#e9efe7"
  forest-light: "#7ec8a0"
  canvas: "#f6f5f2"
  canvas-2: "#efebe1"
  surface: "#fbfaf5"
  surface-hi: "#ffffff"
  border: "#e6e3dc"
  border-2: "#ebe5d8"
  ink: "#232a22"
  muted: "#736e5f"
  faint: "#a39d8c"
  ochre: "#9a6a1e"
  brick: "#a8473a"
  slate-blue: "#3a5f7a"
typography:
  display:
    fontFamily: "Spectral, Georgia, serif"
    fontSize: "40px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.8px"
  headline:
    fontFamily: "Spectral, Georgia, serif"
    fontSize: "30px"
    fontWeight: 600
    lineHeight: 1
  title:
    fontFamily: "Spectral, Georgia, serif"
    fontSize: "22px"
    fontWeight: 400
    lineHeight: 1.2
  body:
    fontFamily: "Spline Sans, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
  body-sub:
    fontFamily: "Spline Sans, system-ui, sans-serif"
    fontSize: "13.5px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Spline Sans Mono, ui-monospace, monospace"
    fontSize: "9.5px"
    fontWeight: 400
    lineHeight: 1.2
    letterSpacing: "1.7px"
  numeric:
    fontFamily: "Spline Sans Mono, ui-monospace, monospace"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1.3
rounded:
  card: "3px"
  chip: "4px"
  input: "6px"
  nav: "7px"
  button: "8px"
  pill: "999px"
spacing:
  xs: "6px"
  sm: "10px"
  md: "18px"
  lg: "26px"
  page-x-phone: "16px"
components:
  button-primary:
    backgroundColor: "{colors.forest}"
    textColor: "{colors.surface-hi}"
    rounded: "{rounded.button}"
    padding: "12px 22px"
    typography: "{typography.body}"
  button-primary-disabled:
    backgroundColor: "{colors.border}"
    textColor: "{colors.faint}"
    rounded: "{rounded.button}"
    padding: "12px 22px"
  button-outline-pill:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.forest}"
    rounded: "{rounded.pill}"
    padding: "8px 18px"
    typography: "{typography.label}"
  pill-filter:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.muted}"
    rounded: "{rounded.pill}"
    padding: "6px 13px"
  pill-filter-active:
    backgroundColor: "{colors.forest}"
    textColor: "{colors.surface-hi}"
    rounded: "{rounded.pill}"
    padding: "6px 13px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.card}"
    padding: "18px"
  input:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    rounded: "{rounded.input}"
    padding: "9px 11px"
    typography: "{typography.numeric}"
  nav-item:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.nav}"
    padding: "8px 10px"
  nav-item-active:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.forest}"
    rounded: "{rounded.nav}"
    padding: "8px 10px"
  stat-cell:
    padding: "16px 18px"
    typography: "{typography.headline}"
---

# Design System: ONS (Almanac)

## Overview

**Creative North Star: "The Almanac"**

ONS should read like an almanac printed for one reader: dated, dense, factual, set on cream stock in forest ink. Every screen is a page of record. A serif headline names the page, a ruled stat band gives the numbers, and cards hold the tables beneath. Authority comes from typesetting rather than chrome. Mono caps label each fact, Spectral states it, and the green marks what matters.

Most ONS surfaces are **Operate** surfaces: dashboards, slates, trackers and forms used every day. Read-heavy pages such as briefs, reviews and postmortems are **Read**. Precision, density and scanability outrank expression. The brand shows in small details: the tracking on a label, the 1.5px ink rule over a stat band, the globe watermark in an accent card. It does not show in big gestures.

The system is flat, warm and quiet. Its moving parts are the scrolling top ticker and a short page rise, and nothing that updates often animates.

**Key Characteristics:**
- Cream canvas in three tonal layers, with no drop shadows
- Spectral serif for titles and big numbers, Spline Sans for running text, Spline Sans Mono for labels and figures
- Forest green as the single voice, with ochre, brick and slate-blue reserved for status and data
- Near-square cards (3px), hairline borders, and ink rules to divide sections
- High density: small type (9–13px) at careful tracking, with generous gutters between blocks

## Colors

A warm paper palette with one forest accent. Status colors are muted, like pigment, never neon.

### Primary
- **Forest Ink** (`forest`): The voice of the system. Used for the brand mark, kickers, the active nav state, primary buttons, filled filter pills, "on track" pace text, the focus ring and text selection. It marks what the reader should act on or trust.
- **Forest Bright** (`forest-bright`): Sparkline and chart strokes, where the deep ink would look heavy at 1.6px.
- **Forest Wash** (`forest-wash`): Tinted backgrounds for positive chips (ticker tags, win badges). Never used as a page or card fill.
- **Forest Light** (`forest-light`): A light green for data marks on darker or green grounds only.

### Secondary (status & data)
- **Almanac Ochre** (`ochre`): "At risk", pending and pre-game states. Appears as text or a thin outline, rarely as a fill.
- **Brick** (`brick`): "Behind", losses, live indicators and error text. The live dot pulses in brick.
- **Slate Blue** (`slate-blue`): A second data series (for example nonfiction vs fiction). It is not a status color.

### Neutral
- **Canvas** (`canvas`): The page ground and the fill for inputs and inactive pills.
- **Canvas Deep** (`canvas-2`): The sidebar and phone sheet. A recessed tone one step darker than the page.
- **Surface** (`surface`): Cards, the ticker bar, the phone tab bar and the active nav item. The raised paper.
- **Surface White** (`surface-hi`): Text on forest fills. Almost never used as a fill.
- **Hairline** (`border`): Card borders, input borders and structural dividers.
- **Hairline Warm** (`border-2`): Dividers inside a component (stat-band cells, ticker items).
- **Ink** (`ink`): Primary text, plus the 1.5px rule over a stat band.
- **Muted** (`muted`): Secondary text, kicker labels, inactive icons.
- **Faint** (`faint`): Tertiary metadata, units, section labels, disabled text.

### Named Rules
**The One Voice Rule.** Forest is the only accent. Ochre, brick and slate-blue carry meaning (status or series) and never decorate.

**The Paper Stack Rule.** Depth is three tones of paper: canvas-2 (recessed), canvas (ground), surface (raised). Do not add a fourth tone.

## Typography

**Display Font:** Spectral (with Georgia, serif)
**Body Font:** Spline Sans (with system-ui, sans-serif)
**Label/Mono Font:** Spline Sans Mono (with ui-monospace, monospace)

**Character:** A bookish serif names things and states the numbers. A neutral grotesk carries running text. A tracked mono in small caps does the clerical work of labels, units and timestamps. Together they read like a printed ledger with a modern instrument panel.

### Hierarchy
- **Display** (Spectral 700, 40px, line-height 1, −0.8px): Page titles in `PageHead`. 30px on phones, 34px for the Home masthead.
- **Headline** (Spectral 600, 30px, line-height 1): Stat-band figures. 24px on phones.
- **Title** (Spectral 400, 22px): Empty-state titles and card headings. Ticker headlines use Spectral at 13.5px.
- **Body** (Spline Sans 400, 13px): Running UI text, nav items and table rows. Page subtitles use 13.5px in Muted.
- **Label** (Spline Sans Mono 400, 9.5px, 1.7px tracking, uppercase): The `K` kicker. Section labels in the sidebar drop to 8.5px at 1.8px tracking. Units and metadata sit at 9–11px.
- **Numeric** (Spline Sans Mono 600, 11–13px): Inline figures, scores, counts and input values.

### Named Rules
**The Clerk's Caps Rule.** Uppercase text is always mono and always tracked (≥0.5px; 1.3–1.8px for kickers). Never uppercase Spectral or Spline Sans.

**The Serif States, Mono Counts Rule.** Big headline figures are Spectral. Small inline figures, units and timestamps are Spline Sans Mono.

## Layout

The shell is a fixed 232px sidebar (canvas-2), and to its right a scrolling main column. The top ticker (38px, 34px on phones) sits at the top of that column. Pages pad generously on desktop. Content stacks as a `PageHead` (26px bottom margin), then a full-width stat band, then one or more card grids.

The stat band is the signature layout device: an N-column grid with a 1.5px Ink rule above, a 1px Hairline rule below, and Hairline Warm dividers between cells. On phones it reflows to two columns ruled like a table.

**Phones (<768px):** the sidebar is hidden and a fixed bottom tab bar (surface) takes over, with a slide-up sheet for the full nav. Pages pad at 18px/16px with 104px at the bottom to clear the tab bar. Every multi-column grid (`ons-stack`) collapses to one column. Inputs go to 16px to stop iOS zoom. The shell uses `100dvh`.

Spacing is pixel-exact rather than scale-based. Common steps are 6, 10, 18 and 26px, and card padding defaults to 18px.

## Elevation & Depth

ONS is flat. Depth comes only from the paper stack (canvas-2 → canvas → surface) and from hairline borders and rules. There are no drop shadows on cards, buttons, menus or popovers.

### Shadow Vocabulary
- **Focus ring** (`box-shadow: 0 0 0 3px rgb(29 85 54 / 0.13)`): Inputs on focus. A ring, not elevation.
- **Active nav tick** (`box-shadow: inset 2px 0 0 #1d5536`): A 2px forest bar on the active sidebar item.
- **Tab bar lift** (`box-shadow: 0 -4px 16px rgba(35,42,34,0.06)`): The single allowed lift, which separates the fixed phone tab bar from scrolling content.

### Named Rules
**The Printed Page Rule.** If something needs to stand apart, give it a surface tone and a hairline border. Never a shadow. The phone tab bar is the only exception.

## Shapes

Shapes are near-square and typeset. Cards use a 3px radius, close enough to square to read as printed matter. Interactive elements round progressively by role: chips 4px, inputs 6px, nav items 7px, buttons 8px. Filter pills, tags and status dots are fully round (999px). Borders are always 1px, except for a 1.5px rule over the stat band and an optional 2.5px forest accent rule across the top of a card.

## Components

Printed, not pressed. Components read as typeset matter, and interactivity shows only in small tap and hover cues.

### Buttons
- **Shape:** Softly squared (8px) for primary actions; fully round for secondary pill actions.
- **Primary:** Forest fill, white Spline Sans 600 at 14px, padded 12px × 22px. When disabled it drops to a Hairline fill with Faint text and a `not-allowed` cursor. There is no separate disabled color.
- **Outline pill (secondary):** Canvas fill, forest mono caps at 11px, a 1px forest border at 33% alpha, padded 8px × 18px. Used for "edit" or "redo" actions.
- **Press:** `.ons-tap`, which scales to 0.97 on `:active` over 120ms and transitions background, border and color over 140ms. There is no hover lift.

### Chips / Filter Pills
- **Style:** Mono caps at 10px, 0.5px tracking, fully round, padded 6px × 13px.
- **State:** Inactive is a canvas fill, a Hairline border and Muted text. Active is a filled pill (forest by default, or a passed status color) with white text.
- **Tags & result badges:** Forest Wash or 10% brick backgrounds with 8.5–9px mono text. Tags use 999px radius, result badges 3px.

### Cards / Containers
- **Corner Style:** 3px.
- **Background:** Surface.
- **Shadow Strategy:** None (see Elevation & Depth).
- **Border:** 1px Hairline. Accent cards add a 2.5px top rule in forest (or a status color) and may carry the faint globe `Watermark` at 5% opacity in the top-right.
- **Internal Padding:** 18px by default.

### Inputs / Fields
- **Style:** Spline Sans Mono at 13px, canvas fill, 1px Hairline border, 6px radius, padded 9px × 11px.
- **Focus:** The border turns forest and a 3px forest ring at 13% alpha appears, over a 140ms transition.
- **Phones:** 16px font, enforced, to prevent iOS zoom.

### Navigation
- **Sidebar:** Canvas-2 ground. The brand mark (globe, "ONS" in Spectral 19px forest, a mono 7.5px subtitle) sits above grouped links. Section labels are mono caps at 8.5px in Faint. Links are Spline Sans at 13px with 17px line icons in Muted. The active link gets a Surface fill, forest text and icon, 600 weight, and the inset 2px forest tick.
- **Phone:** A fixed bottom tab bar on Surface, and a "more" sheet in canvas-2 with a drag handle that lists the full nav.

### Stat Band (signature)
A row of `Stat` cells under a 1.5px Ink rule. Each cell has a mono kicker, a 30px Spectral 600 figure (forest when accented), an optional mono unit in Faint, and an optional sparkline or a 32px spacer to keep the baselines aligned.

### Top Ticker (signature)
A 38px Surface bar. A mono "label" slot sits on the left, with a forest dot that pulses brick when something is live. Pinned live scores come next, then a masked marquee of items: tags, mono league and source metadata, and Spectral headlines. A CFB slot sits on the right. The marquee runs 90s linear, pauses on hover or focus, and becomes a static scroll under `prefers-reduced-motion`.

### Pace Text
Mono status words at 9px: forest for on track, ahead and complete; ochre for at risk; brick for behind; Faint for untracked.

### Empty / Loading / Error
Honest and quiet. Empty and loading states use a short Muted or Faint line centered in the card. `Stub` uses a 22px Spectral title for whole-page placeholders. Errors say "Couldn't load this." in brick, with the detail in Faint.

## Do's and Don'ts

### Do:
- **Do** take colors and fonts from `web/tailwind.config.js` and `web/app/globals.css`. Those are the token source; this file describes them.
- **Do** open every page with `PageHead` (mono kicker in forest, 40px Spectral title, 13.5px Muted subtitle) and put the key numbers in a `StatBand`.
- **Do** label facts with the `K` kicker: mono, uppercase, 9.5px, 1.7px tracking.
- **Do** separate things with hairlines and paper tones. Use the 1.5px Ink rule only over stat bands.
- **Do** keep motion quiet: enter and exit in ≤200ms ease-out, `.ons-tap` press feedback, and respect for `prefers-reduced-motion`.
- **Do** reach for the existing marker classes (`ons-stack`, `ons-band`, `ons-pagehead`) so phone layouts reflow without new CSS.

### Don't:
- **Don't** add drop shadows to cards, buttons, menus or popovers.
- **Don't** introduce a second accent color, or use ochre, brick or slate-blue decoratively.
- **Don't** round cards beyond 3px, or square off pills.
- **Don't** uppercase serif or sans text. Caps belong to mono.
- **Don't** animate data that updates, keyboard actions, or high-frequency surfaces such as the CFB slate and habit check-ins.
- **Don't** use pure white as a page or card background. White is for text on forest.
