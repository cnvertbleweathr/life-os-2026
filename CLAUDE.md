# ONS — notes for Claude

## Git: branches and PRs only

**Never commit to `main` or merge into `main` directly**, not even a fast-forward, and not even when asked to "merge and deploy". Work on a branch, push it, and open a PR; the owner merges. If `gh` isn't installed, push the branch and give the owner the compare URL (`https://github.com/cnvertbleweathr/life-os-2026/compare/main...<branch>?expand=1`). Deploy only from `main` after the owner has merged, following docs/MACMINI_RUNBOOK.md → "Deploy and roll back".

## Dev and test servers never touch production

- Start dev servers with `scripts/dev.sh`: the API on :8001 with `ONS_DEV=1`, so write logs (habits, check-ins, inbox) go to `.dev-data/`, seeded from `data/`; and `next dev` on :3001 building into `web/.next-dev`.
- Production runs from launchd: `next start` on :3000 serving `web/.next`, and uvicorn on :8000 writing to `data/`.
- **Never** run `next dev` or `next build` in `web/` with the default dist dir unless you are deliberately deploying. It overwrites the build narcisystem.com is serving.
- Never run a second API without `ONS_DEV=1` or an explicit `ONS_DATA_DIR`. The API trusts local requests without a write key, so a test click would write to the real logs.
- Tests set `ONS_DATA_DIR` to a temporary directory; keep it that way for any new test that writes.

## Design work (web/)

ONS's UI is the **Logbook Color** design system, chosen by the owner in November 2026 to replace Almanac. It has five parts:
- the week is the unit;
- a tinted L-frame around a white sheet;
- one colour per life area (tint / ink / mark), with forest `#1f6b46` reserved for today, selection and focus;
- IBM Plex Sans and Plex Mono;
- light and dark themes, plus a pixel-art scene beside each page title.

`DESIGN.md` describes it in full. Logbook Color is the brief. No skill may replace it on its own initiative.

**Token source.** `web/app/globals.css` defines every colour as a CSS variable for both themes (`html[data-theme]`); `web/tailwind.config.js` maps Tailwind colour names to those variables, including the old Almanac names (`canvas`, `surface`, `faint`, `green`…), so pages that still use them follow the theme. Never hard-code a hex in a page: use `var(--token)` or a Tailwind colour. The shell, nav, theme switch and primitives are migrated. Individual pages still carry Almanac habits (tracked caps, stat bands, the Home masthead) until each is rebuilt. The mockup in `docs/design/directions/6-logbook-color/` remains the visual reference.

Most ONS screens are **Operate** surfaces (dashboards, slates, trackers, forms). Read-heavy pages (briefs, reviews, postmortems) are **Read**. Precision, density, and scanability outrank expression.

### Which tool does what

| Tool | Role in ONS | When |
|---|---|---|
| **impeccable** (`/impeccable …`) | Lead design skill. Owns DESIGN.md / PRODUCT.md, critique, audit, polish, layout, typeset. Its hooks check UI edits automatically. | Any change to how a page looks or reads. |
| **Emil Kowalski skills** (`emil-design-eng`, `animate`, `review-animations`, `improve-animations`, `find-animation-opportunities`, `remove-animations`, `animation-performance`, `animation-vocabulary`, `break-ui`, `prototype`) | Motion and interaction feel. Also edge-case stress testing (`break-ui`) and side-by-side variants (`prototype`). | Adding or tuning motion, hover/press states, transitions; stress-testing a component with worst-case data. |
| **pixel-art-sprites** | The pixel-art title scenes: sprite sizes, run cycles, palette discipline, integer scaling. A reviewed copy lives in `.claude/skills/pixel-art-sprites`. | Adding or changing a page's pixel scene (`px.js`). |
| **design-taste-frontend** (Taste Skill v2) | Art direction for **new visual worlds only**. | A brand-new public-facing page. Do **not** use it to re-deal directions for ONS screens; the direction is chosen, and the planned "ops" dark look is now Logbook Color's dark theme. |
| **Playwright MCP** | Eyes. Screenshot routes at 1440×900 and 390×844, **in both light and dark**. | After every UI change, before calling it done. |
| **Figma MCP** | Read frames/tokens from Figma when a design starts there; can write back to the canvas. | Only when a Figma link is provided. |

### Precedence when skills disagree
1. Logbook Color as described in `DESIGN.md`, its tokens (see Token source), and component conventions in `web/components/ui/` once migrated.
2. impeccable (layout, type, color, hierarchy, a11y).
3. Emil skills for motion: they win on easing, duration, and whether something should animate at all, except for the owner-approved pixel scenes (below).
4. pixel-art-sprites inside a pixel scene.
5. Taste Skill only inside a new world the user has explicitly asked for.

Don't stack impeccable and Taste on the same task. If Taste is in play, impeccable critiques the result afterwards.

### Motion defaults for ONS
Dashboards are used daily, so motion stays quiet:
- No animation on data that updates, on keyboard actions, or on high-frequency surfaces (the CFB slate, habit check-ins).
- Press and hover feedback runs 120–150ms. Enter and exit stay under 200ms ease-out.
- Theme switches are instant.
- Respect `prefers-reduced-motion`.
- No motion library is installed (`web/package.json`); prefer CSS transitions before adding one.

**The one exception: pixel title scenes.** The owner asked for a looping pixel-art scene beside each page title. They follow DESIGN.md → Pixel Scenes:
- draw only when the frame changes;
- stop offscreen and in hidden tabs;
- click to pause, with the choice remembered;
- show a still frame under reduced motion.

Don't remove them for being decorative, and don't add any other looping motion.

### Verification loop
1. `cd web && npm run dev` (API on :8000 must be up for real data). For mockups, open the files in `docs/design/directions/6-logbook-color/` over `file://`.
2. Make the change.
3. Playwright: screenshot the affected route(s) at desktop and phone sizes, in light and dark; fix what one look shows, then look again.
4. `/impeccable audit <route>` before calling a page finished.

## Betting models (NBA / NHL)

Use the `nba-nhl-ats` skill for any NBA or NHL pipeline, dbt model, backtest, picks or slate work. The phased build plan with ready-to-run prompts is `docs/NBA_NHL_PROMPTS.md`. No betting rule ships until the `ats-edge-validator` agent has reviewed its validation.
