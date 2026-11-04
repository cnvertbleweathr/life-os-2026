# ONS redesign: five directions

Open **`index.html`** in a browser to compare all five side by side (switch between Home and CFB slate, and between phone and desktop). Every mockup also opens on its own from its folder.

| # | Direction | In one line | Theme |
|---|---|---|---|
| 1 | [Almanac II](1-almanac-ii/README.md) | The current system, evolved: masthead coaching, inputs on Today, legible labels | Light, cream |
| 2 | [Ledger](2-ledger/README.md) | The year as a balance sheet: colourless chrome, one blue on "where the year lands" | Light, cool |
| 3 | [Logbook](3-logbook/README.md) | The week is the unit: a lanes-by-days strip; Saturday as a kickoff strip | Light, green-grey frame |
| 4 | [Pocket](4-pocket/README.md) | Phone-first: a toggle stack, then one pale tile per life area | Light, pastel |
| 5 | [Ops](5-ops/README.md) | The planned dark terminal: monitors, a keyboard queue, data freshness | Dark |

## How they were made

- **Critique first.** `../critique.md` scores all 12 routes and ranks 10 cross-app problems. Each direction's README maps its fixes to those numbers.
- **Directions dealt, not picked by habit.** Four are dealt from design-taste-frontend's app-style library (`achromatic-ledger`, `framed-sheet`, `pastel-consumer`, `data-terminal`). Almanac II uses the `editorial-greeting` move (the greeting as the h1, a 12-column centred grid) on the existing brand.
- **Shared rules in all five,** from the critique: text at 11–12px or larger and at least 4.5:1 contrast; no tracked micro-caps; backtest numbers labelled as backtest; unwired goals shown as "not wired", never "behind"; lines shown from the picked side; kickoff times on every pick; the phone bottom tab bar kept; motion limited to press and hover feedback (CLAUDE.md and Emil: nothing animates on daily-use data).
- **Checked.** Every page was screenshotted at 1440×900 and 390×844 (`*-1440.png`, `*-390.png` in each folder) and run through the taste inspector at 1440, 768 and 390. Final result: **0 FAIL on all 10 pages.** The remaining warnings are listed in each README under Trade-offs.

## Data

Real, from the live API on Nov 3, 2026 (or computed from it):
- **CFB:** week 10 picks, lines, totals, model scores, edges, PPA and SP+ gaps, coach-change flags, kickoff times (`/cfb/schedule`), week-by-week results (17–11, +4.453 u) and the backtest (`/cfb/model-info`).
- **Running:** 266.9 mi YTD and 10.2 mi over the last 7 days, plus recent runs.
- **CrossFit:** 84 classes, and SugarWOD's newest record (Oct 27).
- **Books:** 7 of 10 (4 fiction, 1 nonfiction, 2 unclassified).
- **Habits, goals and calendar:** the habit names, the goal targets, and the calendar entries.
- **Spotify:** 388 of 833 hours.

Derived: needed rates, Dec 31 projections at this year's rate, and the "out of reach" wording.

**Sample values to replace:**
- Sync times ("Synced 06:10"). The API exposes no sync timestamp yet.
- The Habits-log "newest record Oct 21" in Ops. It was read off the streak grid, which disagrees with the brief's "yesterday you completed 2 habits".
- "Avalanche v Predators Thu 7:30" on the calendar. It comes from the Sports page, not the calendar API.
- Goal labels are rewritten for display. For example, Logbook's "Squat 350 lb" is the `/goals` row "Squat Max Lbs · — / 350". The target values aren't changed.

## Build

`_sprite.svg` holds the shared icons, and `_build.py` inlines them into every page (idempotent), so the mockups work straight from disk over `file://`.
