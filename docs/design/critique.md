# ONS web app — page-by-page critique

Branch `design/rehaul-2026-11` · captured 2026-11-03 against live data (web :3000, API :8000).
Screens: `docs/design/screens/<route>-1440.png` and `<route>-390.png` (full-page captures).

**Method.** ⚠️ DEGRADED: single-context (12 routes × 2 isolated sub-agents was out of proportion for a batch run, so each page got a sequential review: design review A first, then detector + browser evidence B, then synthesis). The detector ran as URL scans at 1440×900 and 390×844, plus a source scan of each `page.tsx`. Per-page follow-up questions were skipped for this batch run (the cross-app summary at the end replaces them), and no snapshots were persisted to `.impeccable/critique/`.

**Capture note.** `<main>` is its own scroll container, so the captures override the shell to `height:auto` to get the full page. On the 390 captures the fixed bottom tab bar is drawn at the first viewport's bottom edge, partway down the image. That's a capture artifact, not a layout bug.

Scores use Nielsen's ten heuristics, 0–4 each. Bands: 36–40 Excellent, 28–35 Good, 20–27 Acceptable, 12–19 Poor.

---

## 1. Home — `/` (`web/app/page.tsx`)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | "Data as of" stamp and brief "updated" date are there; nothing says whether today's habit ticks have synced yet (nightly load) |
| 2 | Match system / real world | 2 | Brief prints raw markdown (`# ☀️ Good Morning!`, `**2 habits**`); "CFB Edge +34.5%" with no definition |
| 3 | User control and freedom | 3 | Habit checkboxes toggle; nothing to undo |
| 4 | Consistency and standards | 2 | Ticker "CFB '26 17–11 +15.9%" and stat band "CFB EDGE +34.5%" show two different CFB numbers with no explanation |
| 5 | Error prevention | 3 | Low-risk surface |
| 6 | Recognition over recall | 3 | ⌘K "Ask the system" is visible; the nav is labelled |
| 7 | Flexibility and efficiency | 2 | ⌘K exists, but habits can't be ticked by keyboard shortcut and there's no quick capture from Home |
| 8 | Aesthetic and minimalist design | 2 | The brief's generic pep talk fills the best real estate; "Char Dropoff" repeats 5× in This Week; Daily 10 shows an empty striped placeholder |
| 9 | Error recovery | 3 | The brief fails soft (never crashes Home) |
| 10 | Help and documentation | 2 | No inline explanation of edge, streak or Daily 10 |
| **Total** | | **25/40** | **Acceptable** |

**Design specificity.** The masthead is the most authored moment in the app: date and place kicker, "Good morning. You ran **10.2 miles** this week." with the figure in forest. A generic dashboard couldn't use it unchanged. Below the stat band the page turns into a familiar 2+3 card grid, and the brief card hands its largest type size to AI boilerplate.
**Detector.** 72 findings at 1440, 62 at 390. Breakdown:
- `undersized-ui-text` ×54: 8.5–9.5px mono labels, ticker metadata, "Final", "NOV 3".
- `low-contrast` ×12: Faint on cream measures 2.3–2.6:1.
- One each of `hero-eyebrow-chip`, `border-accent-on-rounded`, `straggler`, `marquee` and `repeating-stripes-gradient`.
- The source scan is clean.

The detector agrees with the review on small text and Faint contrast. `hero-eyebrow-chip` is a false positive here: the dated kicker is real content, not decoration. `marquee` is a true finding, but the ticker pauses on hover and respects reduced motion.

**Overall.** The masthead and stat band answer "what is happening". The page never answers "what should I do next" with any authority, because that job went to a pep-talk brief rendered as raw markdown.

**What's working**
- The masthead turns the week into a sentence with the key number highlighted. That's the best "glanceable first" moment in the app.
- The stat band gives six numbers in one ruled row and reads in about two seconds at desktop size.
- Today's habits are tickable right on Home, so the most frequent daily input takes no navigation.

**Priority issues**
- **[P1] The brief renders raw markdown and generic coaching.** `brief_content` goes in through `dangerouslySetInnerHTML` with only `\n` replaced by `<br/>` (page.tsx:176), so `#` and `**` show up literally. Injecting model output as HTML is also an injection risk. The copy ("Consistency is the foundation of lasting change… 💪") contradicts PRODUCT.md's honest coach voice.
  *Fix:* render markdown safely (a sanitized markdown renderer, or plain text with a tiny bold parser), cap the brief at 2–3 sentences, and let the three-column What's happening / Why it matters / Do next block lead, since it is the real answer to the three questions. *Command:* `/impeccable clarify`, then `/impeccable harden`.
- **[P1] Two different CFB numbers with no labels.** Ticker: "17–11 +15.9%". Stat band: "CFB EDGE +34.5%". Without a unit or definition (ROI? cover rate? model edge?) one or both read as wrong.
  *Fix:* name the metric in both places ("ROI", "ATS"), or show the same one. *Command:* `/impeccable clarify`.
- **[P2] The phone order buries the daily action.** At 390 the order is masthead → 6 stats → 15 lines of brief → calendar → habits. The habit check-in, the thing a phone visit is usually for, sits about 2,000px down.
  *Fix:* on phones put Today's habits right after the stat band and collapse the brief to its "Do next" line. *Command:* `/impeccable adapt`.
- **[P2] Calendar noise.** "Char Dropoff" fills 5 of 9 This Week rows, and the list runs past this week (Nov 24, Dec 1).
  *Fix:* collapse recurring events into one row ("Char Dropoff · weekly"), limit the list to 7 days, and mark today. *Command:* `/impeccable distill`.
- **[P2] Labels below legibility.** Mono kickers at 8.5–9.5px in Faint (#a39d8c) measure 2.3–2.6:1 on cream, failing WCAG AA. They're on every card. *Command:* `/impeccable typeset`.

**Persona red flags**
- **Alex (power user):** no keyboard path to tick habits or jump to Capture; ⌘K is the only accelerator. Stat-band cells look like links but aren't clickable through to their pages.
- **Sam (accessibility):** Faint labels fail contrast. The habit checkboxes are custom boxes, so check their accessible name and state. The brief's injected HTML has no heading semantics.
- **Owner on a phone at 7am:** has to scroll past the whole brief to reach the habit ticks; the ticker is cut to about 1.5 items.

**Minor observations**
- "STREAK —" is a permanent dash. The code says real streak data is "not fetched here", so the cell promises data it never shows.
- The Daily 10 cover is an empty striped box with a date in it, which looks like a broken image.
- The "Useful / Not useful" feedback pills sit in the same row as the "Built from today's data" provenance line and compete with it.
- The 404 for `/favicon.ico` shows in the console on every page.

**Questions to consider**
- What if the masthead sentence *were* the brief: one generated line that names the single most important thing today?
- Does Home need six stats, or the three that change daily (habits, miles this week, today's CFB card)?

---

## 2. Capture — `/capture` (`web/app/capture/page.tsx`)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 1 | Without a write key the inbox fetch 401s, gets swallowed (`.catch(() => setItems([]))`), and shows "Nothing captured yet". A locked inbox reads as an empty one |
| 2 | Match system / real world | 3 | "Get it out of your head · sort it later" names the job exactly |
| 3 | User control and freedom | 2 | No edit or delete on inbox items. Kind and area chips can't be cleared without re-tapping |
| 4 | Consistency and standards | 3 | Same pill system as the rest of the app |
| 5 | Error prevention | 3 | Save is disabled until there's text; a pasted link is auto-classified as a link |
| 6 | Recognition over recall | 3 | Kinds and areas are visible chips. "⌘↵ to save" is shown as a tiny label |
| 7 | Flexibility and efficiency | 3 | Autofocus, ⌘↵ to save, link detection: the best accelerator story in the app |
| 8 | Aesthetic and minimalist design | 3 | Focused single column. 13 chips is the only weight |
| 9 | Error recovery | 1 | Auth failure surfaces as a native `window.prompt()` on page load (api.ts:31). Cancelling it leaves a silent empty state |
| 10 | Help and documentation | 2 | Nothing explains what "Area" does downstream or when captures reach the warehouse (the nightly load) |
| **Total** | | **24/40** | **Acceptable** |

**Design specificity.** The kicker voice is specific and good. The form itself is a generic textarea with chip rows that any notes app could ship. The forest top-rule card is the only Almanac signal.
**Detector.** The URL scans returned 0 findings at both sizes. Treat that as unreliable rather than clean: the detector's headless page meets the same native write-key prompt. The source scan is clean. From the screenshots, the review finds the same pattern as Home: mono chip text at 10px, the "0 in inbox / ⌘↵ to save" meta at 9px, and the Faint empty-state subline.

**Overall.** The fastest input surface in ONS, and nearly right. Its two failures are both in auth and state: a browser-native prompt for a secret, and a locked inbox that pretends to be empty.

**What's working**
- Autofocused textarea plus ⌘↵ to save means it opens ready to type. That's the PRODUCT.md "low-friction input" principle done well.
- Link auto-detection (`looksLikeLink`) saves a tap on the most common capture type.
- The phone layout is right: the textarea is high on the page and the tab bar has Capture as a primary tab.

**Priority issues**
- **[P1] A native `window.prompt` for the write key.** It's unstyled, it blocks the page, it shows the key in plain text, it fires on page *load* rather than on save, and it can't be styled or explained. It also blocks automated checks (the detector stalled here).
  *Fix:* an inline "This device isn't unlocked" banner in the inbox card with a password field. Ask only when the user saves or opens the inbox, and confirm with "Unlocked on this device". *Command:* `/impeccable harden`.
- **[P1] Auth failure looks like an empty inbox.** "Nothing captured yet. Whatever you add shows up here." is false when the request 401'd.
  *Fix:* show three distinct states: locked, error ("Couldn't load the inbox: retry"), and truly empty. *Command:* `/impeccable harden`.
- **[P2] 13 chips in two unlabeled-looking rows.** Kind (5) plus Area (8) is over the working-memory limit, and on the phone the rows wrap into 4 lines. The area chips also mirror the nav without saying why.
  *Fix:* default kind to Note and fold Kind into a single segmented control. Make Area optional and collapsed, or infer it from text ("#cfb"). *Command:* `/impeccable distill`.
- **[P2] The primary button is visually dead until you type.** The disabled "Capture" uses the Hairline fill, close to the card colour, so on first look there's no visible action. That's acceptable, but pair it with the ⌘↵ hint at readable size. *Command:* `/impeccable polish`.

**Persona red flags**
- **Owner on a phone, capturing an idea mid-errand:** the first visit on a new device throws a system prompt asking for a "write key". If they cancel, the page looks broken-empty and gives no way back except reloading.
- **Alex:** ⌘↵ works, but there's no shortcut to pick a kind (1–5) and no global capture hotkey from other pages.
- **Sam:** the chip groups need `role="radiogroup"` semantics. The 9px meta hint fails legibility.

**Minor observations**
- "0 IN INBOX" sits top-right in 9px mono and duplicates the inbox card.
- On the 1440 capture the right half of the page is empty. A 760px column is right for a form, but the inbox could sit beside it at desktop size.

**Questions to consider**
- Should Capture be a global ⌘⇧K sheet available from every page rather than a destination?
- Does Area need to be chosen at capture time, given "sort it later" is the promise?

---

## 3. CFB Betting — `/cfb` (`web/app/cfb/page.tsx`, This Week tab)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 2 | No kickoff times, no "lines as of", no live or graded state on the current week. The season record (17–11, +15.9%) appears only in the ticker |
| 2 | Match system / real world | 2 | Raw signal keys leak (`underdog_edge`). The line column shows the *home* spread under an away pick ("Rutgers +17.5" over "-17.5 (DraftKings)") |
| 3 | User control and freedom | 3 | Week picker, three tabs, drill-in is reversible |
| 4 | Consistency and standards | 2 | ⭐ emoji stars (off-palette yellow) duplicate "Model: 97". Home labels backtest ROI as "CFB EDGE +34.5%" while this area tracks live ROI +15.9% |
| 5 | Error prevention | 3 | Publish bar enforced by data (`meets_publish_bar`); coach-change warnings shown |
| 6 | Recognition over recall | 2 | The reader has to remember what "STRONG tier", "Talent parity + PPA (71% hist)" and the score scale mean. Model-info notes ("score is ordinal, not a probability") never reach the UI |
| 7 | Flexibility and efficiency | 2 | Six picks take ~1,150px of scrolling at desktop. No table view, sort, or copy-slate |
| 8 | Aesthetic and minimalist design | 2 | Each card repeats an 8.5px "▸ CLICK TO SEE SEASON-TO-DATE STRENGTH COMPARISON" in near-invisible #c4bfb5 |
| 9 | Error recovery | 3 | Errors use the shared ErrorState |
| 10 | Help and documentation | 1 | No path to SYSTEM_EXPLAINER, no inline glossary for the signals |
| **Total** | | **22/40** | **Acceptable** |

**Design specificity.** The kicker ("The Degenerates' Corner · Walk-forward validated"), the team crests and the serif matchups give it character. Structurally it's a generic card feed: the same card six times, a 760px column centred in a 1,200px canvas. This is the one place ONS should feel like an instrument, and it reads like a blog.
**Detector.** 38 findings at 1440, 30 at 390. Breakdown:
- `undersized-ui-text` ×23: the line/O-U meta at 10.5px and the tab-bar labels.
- `low-contrast` ×6.
- `border-accent-on-rounded` ×6: the forest top rule on every pick card. The review agrees: when every card is accented, the accent stops meaning anything.

The detector missed the #c4bfb5 drill hint, which is about 1.7:1. That's the worst contrast on the page.

**Overall.** The data is good (scores, edges, coach H2H, warnings), but the slate doesn't answer the bettor's three questions fast: *what are the bets, when do they kick, how is the season going.* It needs the density of a ledger, not a feed.

**What's working**
- Pick line first in bold sans ("Texas Tech -16.5 (home fav)"), with the matchup above it in serif. The order is right.
- Coach-change warnings in ochre with ⚠ are the one honest risk signal.
- Separating Official picks from the Watch list (below the publish bar) encodes the system's discipline.

**Priority issues**
- **[P1] Backtest presented as current performance.** Home's "CFB EDGE +34.5%" is `model-info.roi_pct` (2022–25 backtest); live 2026 ROI is +15.9% on 17–11. That breaks PRODUCT.md's "never restate backtest numbers more strongly".
  *Fix:* show the live season record and ROI as the headline on this page and Home, and label the backtest as a backtest wherever it appears.
  *Note:* `SYSTEM_EXPLAINER.md` (68.5% / +30.8%) and `/cfb/model-info` (70.4% / +34.5%) disagree. Pick one source. *Command:* `/impeccable clarify`.
- **[P1] Phone truncates the matchup.** At 390 the crest, the team name and the ⭐⭐⭐⭐ + "Model: 97" share one line, so names become "West V…", "Oklaho…".
  *Fix:* move the score to its own column or row and drop the stars. *Command:* `/impeccable adapt`.
- **[P1] Line display contradicts the pick.** The pick "Rutgers +17.5" sits over "-17.5 (DraftKings)", the home team's number.
  *Fix:* always show the line from the picked side ("+17.5 DK") and add a kickoff time and network. *Command:* `/impeccable clarify`.
- **[P2] The card feed is too sparse for a slate.** Six picks need about 1.3 screens.
  *Fix:* use a ruled table at desktop (kick · matchup · pick · line · score · edges · flags) with a drawer for the strength comparison, and stacked rows at phone width. *Command:* `/impeccable layout`.
- **[P2] Jargon without a glossary.** "STRONG tier", "underdog_edge", "Talent parity + PPA (71% hist)".
  *Fix:* human labels, a tooltip or legend per signal, and a "How the model works" link. *Command:* `/impeccable clarify`.

**Persona red flags**
- **Owner on a phone on a Saturday morning:** wants the six bets with kick times to place them. Gets truncated names, no times, and an 1,880px scroll.
- **Alex:** no compact view, sort by score, or "copy slate"; the week select is the only control.
- **Sam:** emoji stars announce as "star star star star". The drill-down cards are `div` onClick handlers (check keyboard access). The drill hint fails contrast.
- **The friend shown the site:** sees "+34.5%" on Home and assumes that's this season.

**Minor observations**
- The week select at phone width renders in 18px mono and dominates the header.
- The "Watch list · below publish bar (0 of 8)" label and the "Show all 8 scored games" button contradict each other.
- The model version is shown three times: sidebar footer, kicker and the "MODEL V3 WALK-FORWARD" meta.

**Questions to consider**
- What if the slate were a betting-ticket ledger: one line per bet, the season P&L running down the margin?
- Should the Watch list exist on the default view at all, or only when asked?

---

## 4. Check-in — `/checkin` (`web/app/checkin/page.tsx`)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | The live readiness ring updates as you rate; "0/6 rated" counter; "saved to ONS · synced nightly" is honest |
| 2 | Match system / real world | 3 | Endpoint labels (Drained…Energized) and "(lower = better)" on soreness and stress |
| 3 | User control and freedom | 3 | Saving again replaces today's entry; "Edit today's check-in" after save |
| 4 | Consistency and standards | 2 | Reversed scales (soreness and stress, lower = better) use the same neutral 1–5 buttons as the others; only a 9px note signals the flip |
| 5 | Error prevention | 3 | Save disabled until all six are rated |
| 6 | Recognition over recall | 3 | All options visible |
| 7 | Flexibility and efficiency | 2 | 30 buttons, no keyboard path (no 1–5 keys per row), no "same as yesterday" |
| 8 | Aesthetic and minimalist design | 3 | Clear form. The empty readiness ring at rest is dead weight |
| 9 | Error recovery | 2 | Without a write key, `checkin/today` 401s (×2 in the console) and the page silently acts as if nothing is logged today |
| 10 | Help and documentation | 3 | "Where this goes" explains why the data matters. Good |
| **Total** | | **27/40** | **Acceptable (upper)** |

**Design specificity.** Above average. The kicker ("30 seconds · feeds training readiness + morning brief") and the "Where this goes" card tie the form to ONS's own pipeline. The 6×5 button grid itself is a stock survey pattern.
**Detector.** The URL scans returned 0 findings at both sizes, for the same reason as Capture: the 401 triggers the write-key prompt in the detector's page. The source scan is clean. The console shows **React hydration errors #418/#423/#425** on every load. `today` is computed with `new Date().toLocaleDateString()` during render (page.tsx:79), so the server and client text differ. From the screenshots, the review flags 8–9px Faint endpoint labels ("Drained", "Energized") and the "(lower = better)" note, under both the size and contrast floors.

**Overall.** The best-structured form in the app, and its purpose is explained. It needs keyboard and thumb speed, and an honest locked state.

**What's working**
- The "Where this goes" card is a model for every ONS input: it says what the data feeds.
- Live readiness feedback rewards completion while the form is being filled in.
- A single disabled CTA, "Rate all six to save", states its own rule.

**Priority issues**
- **[P1] Silent auth failure plus hydration errors.** Same pattern as Capture: a 401 means an unexplained empty state or a native prompt. The hydration mismatch makes React re-render the tree on every load.
  *Fix:* an inline unlock state, and compute the date client-side after mount, or pass it from the server. *Command:* `/impeccable harden`.
- **[P2] Reversed scales look identical.** For soreness and stress, 5 is bad, but the buttons are the same neutral chips. Mis-rating flips the readiness score.
  *Fix:* show endpoint labels at a readable size inside the end buttons, or put a subtle good→bad tint ramp on the row; consider flipping the scale so 5 is always good. *Command:* `/impeccable clarify`.
- **[P2] 30 taps, no shortcuts.** It's a daily ritual, so speed compounds.
  *Fix:* keys 1–5 set the focused row and advance; a "Same as yesterday" prefill; a sticky save in the thumb zone on phones (currently it's below the fold at 390). *Command:* `/impeccable adapt`.
- **[P3] The empty readiness ring at rest.** "Fill to score" in a grey donut takes the prime right column for nothing until you rate.
  *Fix:* show yesterday's readiness and trend there until today's is complete. *Command:* `/impeccable distill`.

**Persona red flags**
- **Owner on a phone:** after rating stress, the save button is under the tab bar fold, so they have to scroll and hunt.
- **Sam:** each row should be a `radiogroup` with a labelled legend. Endpoint labels at 8.5px fail legibility.
- **Alex:** no keyboard rating.

**Minor observations**
- On a phone the date sits under the title and above the form, which pushes the first row down. At 390 the kicker wraps to two lines.

**Questions to consider**
- Could check-in live on Home as a 6-row strip in the morning, and disappear once done?

---

## 5. Fitness — `/fitness` (`web/app/fitness/page.tsx`)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | YTD totals, source labels (Strava, SugarWOD), "most recent logged" |
| 2 | Match system / real world | 2 | WOD sublines are bare numbers ("73", "2468", "22") with no unit or meaning |
| 3 | User control and freedom | 3 | Read-only page; hover detail on the heatmap |
| 4 | Consistency and standards | 2 | CrossFit is coded in ochre (DESIGN.md reserves ochre for at-risk status); the run/CrossFit colour split doesn't appear anywhere else |
| 5 | Error prevention | n/a | Read-only page |
| 6 | Recognition over recall | 2 | Charts have no axes or values; "Hover a day for detail" is the only way into the heatmap (no touch equivalent) |
| 7 | Flexibility and efficiency | 2 | No range control, no link from a run to Strava |
| 8 | Aesthetic and minimalist design | 2 | Seven blocks of similar weight; the pace-trend chart is a flat filled area over 5 near-identical runs |
| 9 | Error recovery | 3 | Data fails soft |
| 10 | Help and documentation | 3 | The heatmap subline explains its counting rule |
| **Total** | | **22/36** | **Acceptable (61%)** |

**Design specificity.** The consistency heatmap is a real ONS idea: runs and CrossFit counted by exact day, "3.1 / 7 days avg". Below it the page splits into two mirrored columns of stock cards (stat trio, chart, chart, list) that could belong to any fitness app.
**Detector.** 118 findings at 1440, 110 at 390, the highest count so far:
- `undersized-ui-text` ×77: "lb" units, dates, axis labels at 8px.
- `low-contrast` ×31.
- `tiny-text` ×8.

The review agrees: this page uses the most 8–9px Faint text in the app. The source scan is clean.

**Overall.** Rich data, but it doesn't answer "am I training enough, and what should today be?". The check-in's "training readiness" never shows up here, and the strength section's numbers contradict their own labels.

**What's working**
- The heatmap: a year of training at a glance, with an honest averaging rule.
- Running and CrossFit get separate columns with their own source labels. That's provenance done right.
- "0 this week" is shown plainly rather than hidden.

**Priority issues**
- **[P1] "Current maxes" aren't maxes.** Deadlift 198 lb is labelled "−66 lb since first log", power clean "−55 lb". These are the most recently logged *working* weights (a 4×5 deadlift), compared with earlier heavier sets. The header says "Current maxes", so it reads as losing strength. That breaks "honest over flattering" in the other direction: honest data, false framing.
  *Fix:* show the true best (1RM or estimated 1RM) with the date, and the last working set as secondary context; rename the section. *Command:* `/impeccable clarify`.
- **[P1] Readiness is missing.** The check-in claims it "gates today's WOD intensity", but Fitness never shows readiness or a recommendation.
  *Fix:* a top strip answering "Today: readiness 72 · easy run or skill day". *Command:* `/impeccable shape`.
- **[P2] Charts without scales.** Pace trend (5 points, no axis), weekly volume (no labels or units) and lift sparklines can't be read for values.
  *Fix:* direct labels on the last value and min/max, a week axis, units. On phones the pace chart overflows its card on the right. *Command:* `/impeccable polish`.
- **[P2] Meaningless WOD sublines.** "Gym WOD 10/27 · 73".
  *Fix:* label the score type (reps, time, load) or drop it. *Command:* `/impeccable clarify`.
- **[P3] The heatmap uses about 60% of its card,** with the right third empty at desktop and month labels at 8px.
  *Fix:* fit it to the width, or add a weekly-total column. *Command:* `/impeccable layout`.

**Persona red flags**
- **Owner on a phone:** can't hover the heatmap; the pace chart bleeds out of its card; the CrossFit section starts about 1,000px down.
- **Sam:** the heatmap cells and charts have no text alternative or summary, and the colour legend is the only key (green vs ochre).

**Minor observations**
- The "Both" legend swatch (green with an ochre border) is unreadable at 9px.
- "Laurens Birthday Workout · 2468" has no context.

**Questions to consider**
- What's the single number that says "training is on track this week"? Lead with it.
- Should running and CrossFit be interleaved in one timeline, since the heatmap already merges them?

---

## 6. Goals — `/goals` (`web/app/goals/page.tsx`)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 2 | 12 of 20 goals show "— / target · 0% · Behind". Missing data is reported as failure |
| 2 | Match system / real world | 1 | Titles are title-cased YAML keys: "Hsa", "Ps Revenue Usd", "Bodyweight Lbs Max", "Fiction Pages 10", "Spotify Minutes Goal" |
| 3 | User control and freedom | 3 | Read-only |
| 4 | Consistency and standards | 2 | "On/ahead 1/17" in the band disagrees with the 20 tracked goals. "What-if projections live on Scenarios →" points at a page that doesn't exist (no `/scenarios` route; the text isn't even a link) |
| 5 | Error prevention | n/a | Read-only |
| 6 | Recognition over recall | 2 | No required pace ("83 mi left · 10 mi/wk to hit 350") |
| 7 | Flexibility and efficiency | 2 | No sort by risk, no filter to "needs attention" |
| 8 | Aesthetic and minimalist design | 1 | A wall of red "Behind 0%" rows. The urgent (Running miles, at risk, 58 days left) looks the same as the unwired (Github commits, —) |
| 9 | Error recovery | 2 | Untracked goals say "Not numerically tracked", which is honest, but nothing says how to wire the "—" ones |
| 10 | Help and documentation | 2 | No link to `goals/2026.yaml` or an explanation of how pace is computed |
| **Total** | | **17/36** | **Poor (47%)** |

**Design specificity.** Low. Domain cards with progress bars are the most generic pattern in the category. The YAML-key titles make it read as a debug view of `goals/2026.yaml` rather than a page of commitments.
**Detector.** 57 findings at 1440, 47 at 390:
- `undersized-ui-text` ×43: every "Behind" and "Untracked" pace word is 9px.
- `low-contrast` ×9.

The review adds a problem the detector can't see: red is spent on 15 rows, so it signals nothing. The source scan is clean.

**Overall.** This is the page PRODUCT.md is about ("whether you're on pace with what you said you'd do"), and it's the weakest in the app. It can't tell *behind* from *not wired*, and it never says what to do next.

**What's working**
- The domain grouping matches how the goals file is organised.
- "Not numerically tracked" in italics is an honest null state, and it should be the model for the "—" goals.
- The colours on Running miles (ochre, at risk, 76%) and Fiction books (forest, on track, 80%) mean something.

**Priority issues**
- **[P0] Missing data is shown as "Behind".** Bodyweight, Squat, Monthly savings, Github commits, Migrations, PS revenue, Spotify minutes and Date night have no current value, yet get red "Behind 0%". The page reports fake failure, which is the opposite of honest coaching, and it buries the 3 real risks.
  *Fix:* give "Not wired" its own state (grey, a "connect source" hint), exclude those goals from the band's maths, and sort the real risks to the top. *Command:* `/impeccable harden`.
- **[P1] No required pace or next action.** "266.9 / 350 · 76%" with 58 days left needs "83.1 mi to go · 10.0 mi/wk needed · you're averaging 5.1". That's the coach voice PRODUCT.md asks for.
  *Fix:* add a needed-vs-actual pace line per numeric goal. *Command:* `/impeccable shape`.
- **[P1] Machine names as titles.** Rewrite labels in the YAML (`label:`) or a display map: "HSA contributions", "Read 10 fiction pages a day", "Squat 1RM". *Command:* `/impeccable clarify`.
- **[P2] Daily-habit goals expressed as 366-day totals.** "Pushups 100 · 2 / 366 · 1%" punishes a habit that started this week.
  *Fix:* show these as a streak or adherence rate since tracking began, linked to Habits. *Command:* `/impeccable clarify`.
- **[P2] Masonry gaps.** Family (1 goal) and Finance (3 goals) leave large holes at desktop, and Professional sits orphaned.
  *Fix:* use a single ranked list grouped by status (At risk / Behind / On track / Not wired), with the domain as a tag. *Command:* `/impeccable layout`.

**Persona red flags**
- **Owner, Sunday review:** wants "what slipped this week, what needs a push". Gets 15 red rows of equal weight.
- **The friend shown the site:** sees "Ps Revenue Usd — / 1000000 · Behind" and "1/17 on track", which reads as a failure report.
- **Sam:** status is conveyed by colour and 9px text only.

**Minor observations**
- The band's "Avg progress 14%" averages across unwired goals, so it's meaningless.
- "1 GOALS" is a pluralisation bug.

**Questions to consider**
- What if Goals opened with three sentences ("You're ahead on fiction. Running needs 10 mi/wk. CrossFit is 16 classes behind pace.") and the table came second?

---

## 7. Habits — `/habits` (`web/app/habits/page.tsx`)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | Dashed "today" cell updates live on toggle; "resets at midnight" |
| 2 | Match system / real world | 3 | Plain habit names, "tap to log" |
| 3 | User control and freedom | 3 | A tap toggles on and off |
| 4 | Consistency and standards | 2 | The same checklist as Home's "Today's habits" with a different row design. Home's brief says "yesterday you completed 2 habits" while the streak grid shows nothing yesterday |
| 5 | Error prevention | 3 | Low-stakes toggles |
| 6 | Recognition over recall | 2 | The 21-day grid has no dates or weekday marks, so you can't tell which day was the 1-day streak |
| 7 | Flexibility and efficiency | 2 | No backfill for yesterday (a common need when you forget at night) and no keyboard toggles |
| 8 | Aesthetic and minimalist design | 2 | The stat band is four ways of saying "nothing yet": 0/4 · 1d · 0 · 4, repeated again in the header meta "0/4 done today" |
| 9 | Error recovery | 2 | Write failures depend on the same write-key flow as Capture |
| 10 | Help and documentation | 3 | Self-explanatory |
| **Total** | | **25/40** | **Acceptable** |

**Design specificity.** Generic: a checklist plus GitHub-style streak cells. The cells are fine, but nothing ties the habits to the goals they serve (Goals tracks "Pushups 100 · 2/366").
**Detector.** 39 findings at 1440, 30 at 390:
- `undersized-ui-text` ×29: "best 1d", "cur · best 1d" at 9.5–10px.
- `low-contrast` ×8.

The source scan is clean.

**Overall.** Functional and quick. It's the highest-frequency input in the app, yet it's split across two places, and the history can't be read.

**What's working**
- One tap to log, with immediate feedback in the streak row.
- "Resets at midnight" sets an honest expectation.

**Priority issues**
- **[P1] The history can't be read.** 21 unlabelled cells. Add weekday initials and a date on the first cell of each week, mark today clearly, and allow tap-to-backfill yesterday. *Command:* `/impeccable clarify`.
- **[P2] Redundant stats.** Done today, Logged today and the header meta all say the same thing.
  *Fix:* replace them with "This week 9/28 · 32%", "Best current streak" and "Linked goal pace". *Command:* `/impeccable distill`.
- **[P2] Habits and Goals are disconnected.** "100 Pushups" here and "Pushups 100 · 2 / 366 · Behind" on Goals describe the same thing in two vocabularies.
  *Fix:* show the goal link on each habit row ("feeds: Pushups goal"). *Command:* `/impeccable shape`.
- **[P2] Wasted desktop space.** The page ends at 680px on a 900px screen, with the checklist and grid side by side at the same weight.
  *Fix:* merge them into one table, one row per habit with today's checkbox, the 21-day strip, current and best. *Command:* `/impeccable layout`.

**Persona red flags**
- **Owner at 11:50pm on a phone:** remembers yesterday's pushups but can't backfill.
- **Sam:** the custom checkboxes need `role="checkbox"` and `aria-checked`, and the streak cells need text equivalents ("Done Oct 21").

**Questions to consider**
- Should the habit checklist exist in one place only, with the other a link?

---

## 8. King Gizzard — `/kglw` (`web/app/kglw/page.tsx`, Shows tab)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | Counts shown ("1233 shows · 64 videos"); "Soon" and "Recording" badges |
| 2 | Match system / real world | 2 | Raw HTML entity in the featured title: "Anita&#039;s Theater" |
| 3 | User control and freedom | 3 | Filters and search are easy to reset |
| 4 | Consistency and standards | 3 | Shows/Songs segmented control matches CFB's tabs |
| 5 | Error prevention | n/a | Read-only browse |
| 6 | Recognition over recall | 3 | Search placeholder suggests real queries ("Red Rocks", "France", "2017") |
| 7 | Flexibility and efficiency | 2 | Search is good. There's no "my shows" or "attended" filter, though `/shows` exists separately |
| 8 | Aesthetic and minimalist design | 3 | Clean list and player split; the YouTube embed brings in a loud third-party image |
| 9 | Error recovery | 3 | Fails soft |
| 10 | Help and documentation | 3 | Source footnote (kglw.net, YouTube) |
| **Total** | | **25/36** | **Good (69%)** |

**Design specificity.** Moderate. A list-and-detail browser fits a catalogue. The featured player is a YouTube embed whose neon artwork overwhelms the page; the most "on-brand" thing on screen belongs to the band, which is fine for a fan page.
**Detector.** **2,703 findings at 1440.** Almost all are per-row repeats:
- `undersized-ui-text` ×1,395: 8px "SOON" and "MV" badges, 10px dates.
- `low-contrast` ×1,304.

The count is high because **all 1,233 shows render into the DOM at once** (`kglwApi.shows({ limit: 5000 })`, no windowing). The phone-size scan finished later with 2,695 findings in the same pattern. The source scan is clean.

**Overall.** A pleasant fan catalogue that mostly works. Its problems are engineering-shaped: an unwindowed list, unescaped entities, and a phone filter row that overflows.

**What's working**
- Search with concrete example queries.
- Upcoming shows flagged "Soon", with the city and country in muted mono.
- Clear source attribution.

**Priority issues**
- **[P1] 1,233 rows rendered at once.** It slows the first paint on a phone and makes the list hard to scan.
  *Fix:* window the list, or paginate by year with a sticky year header ("2027 · 12 shows"). *Command:* `/impeccable optimize`.
- **[P2] HTML entities in titles** ("Anita&#039;s").
  *Fix:* decode on ingest (`kglw_pipeline.py`) or at render. *Command:* `/impeccable harden`.
- **[P2] The phone filter row overflows.** The chips wrap ("Music / Videos" on two lines), the count is cut off at the edge, and the search placeholder is clipped.
  *Fix:* make the chips a horizontal scroller and move the count under the search box. *Command:* `/impeccable adapt`.
- **[P3] The featured player is a past show** (Oct 13) while the list opens on 2027 dates.
  *Fix:* say why it's featured ("Latest recording"). *Command:* `/impeccable clarify`.

**Persona red flags**
- **Owner on a phone:** the player sits below 1,200px of list, so tapping a show gives no visible feedback above the fold.
- **Sam:** 8px badges, and a placeholder at 2.3:1.

**Questions to consider**
- Should `/kglw` and `/shows` (attended shows) be one page, "Gizz", with *Catalog / My shows* tabs?

---

## 9. Music — `/music` (`web/app/music/page.tsx`)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | Daily 10 dated, "Next for you" meta, show counts |
| 2 | Match system / real world | 3 | "Artist of the day · from Tewnidge" is clear in context |
| 3 | User control and freedom | 3 | Shuffle, filters (All / My artists ★ 100) |
| 4 | Consistency and standards | 1 | "388 / 833 hrs · YTD progress 47%" here, while Goals shows the same Spotify-minutes goal as "— / 50000 · Behind · 0%". The 📅 calendar emoji per show row is off-system |
| 5 | Error prevention | n/a | Browse page |
| 6 | Recognition over recall | 3 | ★ marks artists you follow; the Bucket A/B explainer for Daily 10 |
| 7 | Flexibility and efficiency | 3 | Add-to-calendar per show, ticket links |
| 8 | Aesthetic and minimalist design | 2 | Three unrelated modules (bio, stats, player and shows) with no hierarchy between them. On the phone the Spotify embed renders as an empty 500px card |
| 9 | Error recovery | 2 | The embed fails blank, with no fallback list |
| 10 | Help and documentation | 3 | "Artist matching is approximate (substring search)" is an admirably honest footnote |
| **Total** | | **26/36** | **Good (72%)** |

**Design specificity.** The most personal page: Daily 10 with its own bucket logic, Tewnidge artist of the day, Denver shows matched to your artists. The composition, though, is three unrelated widgets stacked up, and the Spotify embed's brown player clashes with the cream canvas.
**Detector.** 349 findings at 1440, 336 at 390:
- `undersized-ui-text` ×228: the 10.5px show dates and venue lines.
- `low-contrast` ×112.
- `line-length` ×1: the bio runs ~109 characters per line.

The source scan is clean. The review adds: the per-row 📅 emoji renders a red-and-grey "17" glyph that ignores the palette.

**Overall.** Good content, good honesty. It's a dashboard of three different jobs (discover, listen, go out) with no lead.

**What's working**
- The Denver shows list, with ★ for followed artists and time, venue and seller on one line, is genuinely useful.
- The Daily 10 explainer (Bucket A / Bucket B) makes the algorithm legible.
- The approximate-matching footnote.

**Priority issues**
- **[P1] Cross-page data contradiction.** Music knows YTD listening (388 h of 833, 47%), but Goals reports that goal as unwired, "Behind · 0%".
  *Fix:* compute Goals from the same mart. This is a pipeline bug that surfaces as a design trust problem. *Command:* `/impeccable harden`.
- **[P2] The Spotify embed fails blank on phones.** An empty 500px card.
  *Fix:* render the track list natively from the API (it's already shown as data on Home) and use the embed only for playback. *Command:* `/impeccable harden`.
- **[P2] No lead.** Bio, stats, player and shows all have equal weight.
  *Fix:* pick a job per visit. Mornings: Daily 10 first. Evenings and weekends: "Tonight in Denver". *Command:* `/impeccable layout`.
- **[P3] Emoji calendar icons** on 13+ rows add visual noise.
  *Fix:* a single line icon in Muted, or a text "＋ Cal". *Command:* `/impeccable quieter`.

**Persona red flags**
- **Owner on a phone in the evening:** has to scroll past the bio, the stats and an empty player to reach "who's playing tonight".
- **Sam:** the calendar emoji has no label, and the show links open new tabs without saying so.

**Questions to consider**
- Is "Artist of the day" a Music page feature or a Home feature?

---

## 10. Reading — `/reading` (`web/app/reading/page.tsx`)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | "7 of 10 books · ~1 behind pace" is the best one-line status in the app |
| 2 | Match system / real world | 1 | Finish dates print as raw ISO fragments ("09-05T00:00:00") |
| 3 | User control and freedom | 3 | Read-only |
| 4 | Consistency and standards | 2 | The donut says 7 books, but its legend lists Fiction 4 + Nonfiction 1. The 2 "unclassified" books are missing from the chart key |
| 5 | Error prevention | n/a | Read-only |
| 6 | Recognition over recall | 3 | Everything visible |
| 7 | Flexibility and efficiency | 2 | No link from a book to Hardcover, no previous-years view |
| 8 | Aesthetic and minimalist design | 3 | Calm and readable. Placeholder "covers" are flat colour blocks |
| 9 | Error recovery | 3 | Honest note about in-progress books |
| 10 | Help and documentation | 3 | The note explains a data limitation |
| **Total** | | **23/36** | **Acceptable (64%)** |

**Design specificity.** Above average for ONS. The shelf metaphor with spine-coloured blocks and serif titles suits a reading log. The pace chart is the right idea, but it's drawn wrong.
**Detector.** 63 findings at 1440, 55 at 390:
- `undersized-ui-text` ×51: 9px genre pills, 10px dates.
- `low-contrast` ×9.
- `tight-leading` ×1 (phone).

The source scan is clean. The review adds two data-rendering bugs the detector can't see: the timestamps, and a flat "actual" line.

**Overall.** Nearly a model page: a status sentence, a shelf, pace against the goal. It's let down by two rendering bugs and a developer-voiced footnote.

**What's working**
- The header meta "7 of 10 books · ~1 behind pace" answers *what is happening* and *does it matter* in one line.
- The on-pace target ("8 by now") in the stat band makes the goal concrete.
- The honest data note about in-progress books.

**Priority issues**
- **[P1] Raw timestamps.** `T00:00:00` leaks on every row.
  *Fix:* format as "Sep 5". *Command:* `/impeccable polish`.
- **[P1] The pace chart's "actual" line is flat.** It's drawn as a horizontal line at 7 from January, as if all 7 books were finished on Jan 1, instead of a cumulative step line by finish date. That undermines the one chart that answers "am I on pace".
  *Fix:* a cumulative step series using finish dates. *Command:* `/impeccable polish`.
- **[P2] Donut and legend disagree.** 7 total against 4 + 1 in the legend.
  *Fix:* add "Unclassified 2", or classify them via Hardcover genres. *Command:* `/impeccable clarify`.
- **[P2] The "what next" is missing.** "Next up" or "3 books in 58 days: one every 19 days".
  *Fix:* add a needed-pace line under the chart. *Command:* `/impeccable clarify`.

**Persona red flags**
- **The friend shown the site:** sees "09-05T00:00:00" and a broken-looking chart.
- **Sam:** the donut has no text alternative, and the 9px genre pills fail legibility.

**Minor observations**
- The in-progress note speaks in developer voice ("would need a pipeline change"). Rewrite it for the owner: "Currently reading isn't tracked yet."

**Questions to consider**
- Should this page show actual covers? Hardcover has cover URLs; the blocks read as missing images.

---

## 11. Shows — `/shows` (`web/app/shows/page.tsx`)

**Not critiqued separately.** `/shows` is a server-side redirect (307) to `/music`: "Shows merged into the Music page (right column, All / My artists filter)". The Denver shows list is covered under §9 Music. No screenshots were kept; they would duplicate `music-*.png`.

One IA note: KGLW live shows live under `/kglw` and Denver shows under `/music`, and the old `/shows` path points only at the latter. "Shows" means two different things in this app. See the summary.

---

## 12. Sports — `/sports` (`web/app/sports/page.tsx`)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | "Updated 9:39 PM · auto-refresh · 1 of your teams today · 2 live"; live games marked in brick |
| 2 | Match system / real world | 3 | ESPN conventions, records next to teams |
| 3 | User control and freedom | 3 | Team filter chips on news |
| 4 | Consistency and standards | 2 | Card top rules in three arbitrary colours (forest, slate-blue, ochre) with no meaning. "My teams today" has no W/L marker though the ticker shows "L" |
| 5 | Error prevention | n/a | Read-only |
| 6 | Recognition over recall | 3 | Logos plus names |
| 7 | Flexibility and efficiency | 2 | No league filter on games; news filters but games don't |
| 8 | Aesthetic and minimalist design | 1 | "Top games today" and "All games today" repeat the same 5 games back to back; the ticker repeats "My teams today" a third time; 15 news items at equal weight |
| 9 | Error recovery | 3 | Fails soft |
| 10 | Help and documentation | n/a | Self-evident domain |
| **Total** | | **20/32** | **Acceptable (63%)** |

**Design specificity.** Low. It's an ESPN scoreboard reskinned in Almanac. The only personal elements are the "my teams" filter and the team chips on news.
**Detector.** 177 findings at 1440, 167 at 390:
- `undersized-ui-text` ×127: 10.5px "Final", 9.5px news meta.
- `low-contrast` ×48, including **1.6:1** (#cbc7bb on surface) for the losing-team records at phone size.

The source scan is clean. The review adds: the "All games" card clips its last row ("Blues 1 Final" cut off at the card edge).

**Overall.** A competent scoreboard that triplicates itself. It answers "what's the score" but not "what do I care about": your teams are a small card at the top, and the rest is the national slate.

**What's working**
- "Coming up · next game per team" gives one line per followed team with a day and time. That's exactly the right density.
- Live state in brick with clock and period ("3:57 · 3rd").
- News filtered to your teams with team chips.

**Priority issues**
- **[P1] Triple duplication.** Ticker, then Top games, then All games show the same games.
  *Fix:* drop "Top games"; make "All games" one ruled table filterable by league, with your teams pinned first. *Command:* `/impeccable distill`.
- **[P2] Your teams are under-weighted.** A single result card with no W/L or recap link.
  *Fix:* a "Your teams" block with result (W/L chip), next game, and the latest headline for each team, then everything else. *Command:* `/impeccable layout`.
- **[P2] Arbitrary accent rules.** Three colours on three cards with no meaning. This breaks DESIGN.md's One Voice rule and confuses the brick = live semantics. *Command:* `/impeccable quieter`.
- **[P2] Clipped card, low-contrast loser rows.** At 1.6:1 the losing team becomes unreadable. Grey them less, or bold the winner instead. *Command:* `/impeccable polish`.

**Persona red flags**
- **Owner on a phone at a bar:** wants the Avs score and next game. It's there, but the page then runs 3,600px.
- **Sam:** losing teams at 1.6:1 contrast; the live state is shown by colour plus a dot.

**Questions to consider**
- Does Sports need to be a page, or is it the ticker plus a "Your teams" card on Home?

---

## Not covered

- **CFB → Matchup Lab and Teams tabs** are client-side tabs inside `/cfb`; only the default *This Week* tab was captured.
- **Logged-in write flows** (saving a capture, check-in or habit with a valid key) weren't exercised: no write key was entered. Every screenshot shows the unauthenticated state a new device sees.

---

# Summary — what hurts across the whole app

| Route | Score | Band |
|---|---|---|
| Home | 25/40 | Acceptable |
| Capture | 24/40 | Acceptable |
| CFB | 22/40 | Acceptable |
| Check-in | 27/40 | Acceptable |
| Fitness | 22/36 | Acceptable (61%) |
| Goals | **17/36** | **Poor (47%)** |
| Habits | 25/40 | Acceptable |
| KGLW | 25/36 | Good (69%) |
| Music | 26/36 | Good (72%) |
| Reading | 23/36 | Acceptable (64%) |
| Sports | 20/32 | Acceptable (63%) |

Every page lands between 47% and 72%. No page is broken, and none is excellent. The visual system is coherent; the problems are trust, hierarchy and legibility.

### Ranked by how much they hurt daily use

**1. The numbers can't be trusted across pages.** *Honesty · consistency.* Several findings below aren't cosmetic: they break the product's first principle, "honest over flattering".
- Home's "CFB Edge +34.5%" is the 2022–25 *backtest* ROI; the live season is +15.9%.
- Goals reports the Spotify goal as "— / 50000 · Behind 0%" while Music shows 388 of 833 hrs (47%).
- Goals marks 8 unwired goals as red "Behind".
- Fitness labels working sets as "Current maxes" (−66 lb).
- Reading's pace line is flat from January.
- The brief says "yesterday you completed 2 habits" while the Habits grid shows none.
- `SYSTEM_EXPLAINER.md` and `/cfb/model-info` disagree on the backtest.

Once one number is wrong, the owner stops trusting every number. *Fix:* a single metrics source per figure; separate states for "not wired" and "behind"; backtest always labelled as backtest.

**2. Pages report; they don't coach.** *Hierarchy · product fit.* PRODUCT.md's three questions get answered only to the first ("what is happening").
- There's no needed pace ("10 mi/wk to hit 350") on Goals, Reading or Fitness.
- There's no readiness-to-WOD recommendation, though Check-in promises one.
- The brief, the one place written to say "what next", is generic pep talk ("Make today count! 💪") rendered as raw markdown.

*Fix:* every Operate page leads with one sentence of status plus one next action, and the data follows.

**3. Legibility floor broken system-wide.** *Type · colour · a11y.* On the pages with a working URL scan (Capture and Check-in were blocked by the write-key prompt), 76–99% of detector findings are two things:
- 8–9.5px tracked mono labels.
- Faint `#a39d8c` text at 2.3–2.6:1 on the cream surfaces, with 1.6:1 losing-team records on Sports.

The labels carry real data (dates, units, status words such as "Behind", line and O/U, kickoff), so this isn't decoration being small. It hurts most on a phone and at 7am. *Fix:* an 11px floor for anything functional, Muted (#736e5f, ~4.6:1) as the lowest text colour for data, and Faint reserved for true decoration.

**4. Auth and failure states are invisible.** *System status · error recovery.*
- A native `window.prompt()` asks for the write key on page *load* (Capture, Check-in).
- Cancelling it leaves a 401 that renders as "Nothing captured yet" or an untouched form.
- React hydration errors (#418/#423/#425) fire on Check-in from a client-only date.
- The phone Spotify embed fails as a blank 500px card.

A new device, or a cleared localStorage, makes the input half of the app look empty rather than locked. *Fix:* designed locked, error and empty states, plus an inline unlock.

**5. The phone order buries the daily actions.** *Mobile.* The phone is where the high-frequency inputs happen, but:
- Home puts the brief (15 lines) above the habit ticks.
- CFB truncates every matchup ("West V…", "Oklaho…") and has no kick times.
- Check-in's save button sits under the tab bar.
- Fitness's pace chart overflows its card; KGLW's filter chips and count overflow.

The bottom tab bar is right (Home, Habits, Check-in, Capture, More); the pages behind it weren't re-ordered for thumbs. *Fix:* per-page phone order (action first, then status, then detail), plus truncation-proof row layouts.

**6. Duplication and muddled IA.** *Navigation.*
- Habits are tickable on Home *and* Habits, with different row designs.
- Sports shows the same games three times (ticker, Top, All).
- "Shows" means KGLW live shows under `/kglw` and Denver gigs under `/music`, while `/shows` redirects to Music.
- Goals points to a "Scenarios" page that doesn't exist.
- The sidebar mixes inputs (Check-in, Capture), dashboards and catalogues in one 11-item list with three headings, and "Entertainment" holds three pages that are each half-catalogue, half-dashboard.

*Fix:* restructure the nav around jobs: **Today** (Home with inline habits and check-in), **Track** (Goals, Fitness, Reading), **Edge** (CFB), **Play** (Music + Gizz + Sports), with Capture global (⌘⇧K and a tab).

**7. Density is inverted: tiny text, loose layout.** *Density · layout.* Labels are crammed to 8–9px while layouts are generous card feeds:
- The CFB slate is 6 picks over ~1,150px.
- Goals is a masonry grid with gaps.
- Habits ends at 680px, with the checklist and grid side by side at equal weight.
- Capture is a 760px column in a 1,200px canvas.

The data wants ruled tables (slate, goals, games, habits) with readable type. The current design shrinks the type and leaves the space empty. *Fix:* tables for comparison data, cards only for genuinely different objects.

**8. Machine voice leaks into the UI.** *Copy.* There's an engineering seam on every page:
- YAML keys as titles ("Ps Revenue Usd", "Hsa").
- `underdog_edge`.
- `09-05T00:00:00`.
- `Anita&#039;s`.
- Literal `#` and `**`.
- "1 GOALS".
- "Would need a pipeline change".

The friend shown the site sees an unfinished app. *Fix:* a display-label map, a date formatter and an entity decode, plus a copy pass in the coach voice.

**9. Colour semantics drift.** *Colour · consistency.* DESIGN.md's One Voice rule isn't being followed:
- Ochre is used as the CrossFit category colour.
- Sports puts forest, slate-blue and ochre top rules on cards with no meaning.
- Every CFB card carries the "accent" rule, so the accent signals nothing.
- Emoji ⭐ and 📅 bring in off-palette yellow and red.
- Red "Behind" is spent on 15 rows.

When colour is used everywhere it stops signalling anything. *Fix:* reserve status colours for status, use one categorical pair for data series, and add no new accents.

**10. Charts without scales.** *Data viz.* Pace trend, weekly volume, lift sparklines and Reading's pace chart have no axes, no direct labels, and in two cases misleading series. *Fix:* direct-label the last value and the min/max, use real axes, and use cumulative series where the question is pace.

### What any redesign must keep
- The masthead sentence ("You ran **10.2 miles** this week").
- The ruled stat band as a scanning device.
- Capture's autofocus plus ⌘↵.
- Check-in's "Where this goes" card.
- Reading's one-line pace status.
- The honest footnotes (Music's approximate matching, the in-progress books note).
- The bottom tab bar on phones.
