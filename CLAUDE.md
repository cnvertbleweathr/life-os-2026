# ONS — notes for Claude

## Design work (web/)

ONS's UI is the **Logbook Color** design system, chosen by the owner in November 2026 to replace Almanac. It has five parts:
- the week is the unit;
- a tinted L-frame around a white sheet;
- one colour per life area (tint / ink / mark), with forest `#1f6b46` reserved for today, selection and focus;
- IBM Plex Sans and Plex Mono;
- light and dark themes, plus a pixel-art scene beside each page title.

`DESIGN.md` describes it in full. Logbook Color is the brief. No skill may replace it on its own initiative.

**Token source.** Until the app migrates, the reference build is the mockup in `docs/design/directions/6-logbook-color/`, and its `style.css` is the token source. The live app (`web/`) still runs Almanac (Spectral, Spline Sans, cream). After migration, `web/app/globals.css` and `web/tailwind.config.js` become the source of truth. Update this paragraph when that happens.

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
