# ONS — notes for Claude

## Design work (web/)

ONS's UI is the **Almanac** design system: Spectral serif for display and reading, Spline Sans (tracked caps for labels), Spline Sans Mono for numbers, forest green `#1d5536` on cream canvas (`#f6f5f2` / `#efebe1`). Tokens live in `web/tailwind.config.js` and `web/app/globals.css`; those files are the source of truth. Almanac is the brief. No skill may replace it on its own initiative.

Most ONS screens are **Operate** surfaces (dashboards, slates, trackers, forms). Read-heavy pages (briefs, reviews, postmortems) are **Read**. Precision, density, and scanability outrank expression.

### Which tool does what

| Tool | Role in ONS | When |
|---|---|---|
| **impeccable** (`/impeccable …`) | Lead design skill. Owns DESIGN.md / PRODUCT.md, critique, audit, polish, layout, typeset. Its hooks check UI edits automatically. | Any change to how a page looks or reads. |
| **Emil Kowalski skills** (`emil-design-eng`, `animate`, `review-animations`, `improve-animations`, `find-animation-opportunities`, `remove-animations`, `animation-performance`, `animation-vocabulary`, `break-ui`, `prototype`) | Motion and interaction feel. Also edge-case stress testing (`break-ui`) and side-by-side variants (`prototype`). | Adding or tuning motion, hover/press states, transitions; stress-testing a component with worst-case data. |
| **design-taste-frontend** (Taste Skill v2) | Art direction for **new visual worlds only**. | A brand-new public-facing page, or exploring the planned dark terminal "ops" theme. Do **not** use it to re-deal directions for existing Almanac screens. |
| **Playwright MCP** | Eyes. Screenshot `http://localhost:3000` routes at 1440×900 and 390×844 to verify. | After every UI change, before calling it done. |
| **Figma MCP** | Read frames/tokens from Figma when a design starts there; can write back to the canvas. | Only when a Figma link is provided. |

### Precedence when skills disagree
1. Almanac tokens and existing component conventions in `web/components/ui/`.
2. impeccable (layout, type, color, hierarchy, a11y).
3. Emil skills for motion: they win on easing, duration, and whether something should animate at all.
4. Taste Skill only inside a new world the user has explicitly asked for.

Don't stack impeccable and Taste on the same task. If Taste is in play, impeccable critiques the result afterwards.

### Motion defaults for ONS
Dashboards are used daily, so motion stays quiet: no animation on data that updates, on keyboard actions, or on high-frequency surfaces (the CFB slate, habit check-ins). Enter/exit ≤ 200ms ease-out; respect `prefers-reduced-motion`. No motion library is installed (`web/package.json`); prefer CSS transitions before adding one.

### Verification loop
1. `cd web && npm run dev` (API on :8000 must be up for real data).
2. Make the change.
3. Playwright: screenshot the affected route(s) at desktop and phone sizes; fix what one look shows, then look again.
4. `/impeccable audit <route>` before calling a page finished.
