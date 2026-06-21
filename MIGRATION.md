
---

# Operating Narcisystem — Migration Notes (2026-06-20)

## Summary of changes

### Streamlit → FastAPI + Next.js

The dashboard moved off Streamlit entirely. `app/Home.py` and `app/pages/*`
are retired. The replacement is a standard two-process split:

- **FastAPI** (`api/`) — thin, read-only query layer over DuckDB/dbt marts.
  Opens its DuckDB connection with `read_only=True`, shared across requests
  via `app.state.db`, lifespan-managed in `api/main.py`.
- **Next.js** (`web/`) — the actual UI. Fetches from FastAPI via a typed
  client (`web/lib/api.ts`).

**Why:** Streamlit's per-page-reload model and limited layout control were
becoming a real constraint as the number of pages and the density of data
on each page grew. A real frontend framework with a typed API boundary
scales better and matches the rigor the rest of the platform already has.

**Run it:**
```bash
# Terminal 1
uvicorn api.main:app --reload --port 8000

# Terminal 2
cd web && npm run dev
```

Old Streamlit invocation (`streamlit run app/Home.py`) no longer applies —
`app/` can be removed once parity is confirmed.

---

### FastAPI backend — 9 routers, debugged against live data

The backend was built and had been running on the Mac mini for some time,
but had never actually been committed to git, and had never been exercised
against real data end-to-end. A full debugging pass found and fixed 8
distinct bugs across 7 commits, all discovered by hitting live endpoints
with `curl` and reading actual responses rather than trusting the original
code:

| Commit | Fix |
|---|---|
| `1823644` | Commit the backend itself; fix `parents[3]`→`parents[2]` path bug in 7 router files |
| `ed5e5c5` | `cfb.py` `/teams` — real column names didn't match the response aliases |
| `e15b876` | Shared `query()` helper in `deps.py` — NaN→null serialization was broken for numeric columns on this pandas version (3.0.2), affecting every router |
| `ac5a72d` | `fitness.py`/`home.py` — timestamp-vs-string comparison error against `strava.activities.start_date` |
| `b3d4499` | `home.py` calendar logic — wrong CSV column names, plus a pandas 3.0 mixed-timezone parsing bug that silently returned `NaT` for every row |
| `2ea81d3` | Same two bugs again in `shows.py` |
| `955dbe4` | `_load_my_artists()` — iterated a dict's keys instead of its `artists` list, producing near-zero artist matches despite 4,000+ real artists in the file |

**Deliberately deferred, not fixed:** `shows.py` artist matching uses plain
substring search, producing false positives for short/common-word artist
names. Flagged, not urgent.

Full confirmed response shapes, nullable fields, and known low-confidence
endpoints are documented in `API_STATE_REFERENCE.md`.

---

### Next.js frontend — full rebuild, 11 pages

The first frontend tarball built for this migration shipped with only 2
of 10 intended pages — a packaging gap, not a real deployment issue. The
frontend was rebuilt from scratch against the confirmed real API shapes
in `API_STATE_REFERENCE.md`, then stress-tested by actually clicking
through every page and fixing what broke:

- **Goals page** — `/api/goals/by-domain` returns an array of
  `{domain, goals}` objects, not a dictionary keyed by domain name as
  originally assumed. Fixed the type and the component to match.
- **CFB page** — `win_rate` and `roi_pct` are already percentages
  (e.g. `68.2`), not `0–1` fractions. A `* 100` was silently producing
  `6820%` instead of `68%`.
- **Fitness page** — the weekly-miles bar chart wasn't rendering bar
  height correctly; a flex child needs an explicit `h-full` for a
  percentage-based height to resolve against, not just `flex-1`.
- **Tailwind config** — colors were defined as raw CSS custom properties
  consumed by hand-written flat classes (`.bg-green { ... }`), which meant
  Tailwind had no idea `green`/`amber`/`red` were real colors. Every
  opacity-modifier usage across the app (`bg-green/70`, `text-amber/60`,
  etc. — 17 occurrences) was silently compiling to nothing. Fixed by
  registering the palette properly in `tailwind.config.js theme.colors`.

**New pages this migration:** `kglw` (King Gizzard show/song explorer),
`checkin` (daily subjective check-in).

**New shared pieces:** `web/lib/api.ts` (typed client, one interface per
confirmed response shape), `web/components/ui/TeamLogo.tsx` (260/263 real
CFB logos with initial-letter fallback for the 3 the CDN lacks).

---

### KGLW pipeline + router — King Gizzard show catalog

New: `pipelines/kglw_pipeline.py`, `api/routers/kglw.py`, `web/app/kglw/page.tsx`.

No auth required — `kglw.net/api/v2`. Four real bugs found by checking
live responses against assumptions, the same discipline as the FastAPI
work above:

- **`venues`** — real field names are `venue_id`/`venuename`, not
  `id`/`name`; `country` is a flat string, not a nested object.
- **`jamchart`** — primary key is `uniqueid` (string), not `id`. Nearly
  every field name was wrong (`songname`, `jamchartnote`,
  `isrecommended`, not `song_title`/`description`/`rating`).
- **`shows`** — most field names wrong (`showdate`/`venuename`/`tourname`,
  not `date`/`venue`/`tour_name`).
- **No working pagination** — `/shows` ignores `page`/`per_page` entirely
  and returns the full dataset (1104 shows) in one response, sorted
  oldest-first. The original pipeline looped 20 "pages," each an
  identical full re-fetch, silently deduplicated by the merge key into
  the correct count but burning 20x the API calls for nothing.

**Confirmed real data as of 2026-06-20:** 1104 shows, 1001 songs, 671
venues, 247 jam chart entries.

**Known limitation, not a bug:** no latitude/longitude exists anywhere in
KGLW's API. There is no literal globe visualization — the KGLW page is a
searchable list/explorer. A real globe would need a separate geocoding
pass (city/state/country → lat/lng) layered on top.

---

### CFB logos

`scripts/download_cfb_logos.py` + `web/lib/cfb_team_ids.json` (263-team
name → CFBD numeric ID map, built by cross-referencing your actual
`cfbd.team_profiles` team list against CFBD's `/teams` endpoint, not
hand-typed). 260/263 logos downloaded successfully; 3 genuine 404s from
CFBD's CDN for smaller programs.

---

### Infrastructure hardening

- `daily_sync.py` — `ops.pipeline_runs` tracking per step, `notify.py`
  wired for sync-ok/sync-fail.
- `track_lines.py` / `track_news_signals.py` — both had an off-season bug
  where `ensure_table()` was never called before the early off-season
  exit, so the destination tables (`cfbd.line_history`,
  `cfbd.news_signals`) never got created, which blocked `dbt run` for two
  months a year. Fixed to always create the table first, even off-season.
- `goals/2026.yaml` — found deleted from the working tree with an
  uncommitted deletion sitting in git status; recovered via
  `git restore`.
- launchd plists — fixed a wrong `uv` binary path
  (`/Users/kg/.local/bin/uv` → `/usr/local/bin/uv`) that was causing
  `EX_CONFIG` (78) silent failures with zero log output.
- `tests/smoke_test.py` — fixed 5 false-positive failures: a missing
  `sys.modules` registration that broke dataclass resolution under
  `importlib.util.module_from_spec()`, and one check expecting a
  function name (`build_report`) that was never the real one
  (`generate_report`).
- `.gitignore` — the bare `lib/` rule (meant for Python build artifacts)
  was matching `web/lib/` too, which holds real Next.js source. Scoped to
  `/lib/` (repo-root only) so it no longer collides with unrelated
  directories of the same name elsewhere in the tree.

---

## First-run checklist

```bash
# 1. Install deps
uv sync
cd web && npm install && cd ..

# 2. Confirm DuckDB and backups
python scripts/backup_duckdb.py --dry-run

# 3. Run the daily sync once manually
python scripts/daily_sync.py

# 4. CFB logos (one-time)
python scripts/download_cfb_logos.py

# 5. KGLW catalog (one-time, or whenever you want fresh show data)
python pipelines/kglw_pipeline.py --shows-only

# 6. Run the app
uvicorn api.main:app --reload --port 8000 &
cd web && npm run dev
```
