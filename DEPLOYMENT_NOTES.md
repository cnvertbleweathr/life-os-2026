# Deployment notes — 2026-07-03 patch

Everything in this patch has been **tested against a synthetic DuckDB
warehouse and the actual repo checked out from `main`** — not just written
and hoped for. Specifics of what was tested are in each section below.
Nothing here has touched the real Mac mini; all of it needs the steps below
run there.

Bundle: `ons-patch-2026-07-03.tar.gz`

```bash
cd ~/life-os-2026
tar -xzf ~/Downloads/ons-patch-2026-07-03.tar.gz
```

This overwrites 8 existing files and adds 7 new ones. Full file list at the
bottom of this doc.

---

## 0. Before you start

Stop FastAPI (single-writer rule applies to the dbt run in step 3):

```bash
lsof -ti:8000 | xargs kill -9   # or however you normally stop uvicorn
```

---

## 1. Hardcode fixes (safe, no prerequisites)

Files: `scripts/fitness_metrics.py`, `scripts/calendar_metrics.py`,
`scripts/calendar_export.py`, `web/lib/api.ts`

- `fitness_metrics.py` no longer hardcodes `2026` — it now takes `--year`
  (defaults to current year) and writes `fitness_summary_{year}.csv`
  instead of the old fixed `fitness_summary_2026.csv`. **If anything reads
  that CSV by the old fixed filename, it needs updating too** — I grepped
  the whole repo and found nothing that does, but worth a second look since
  you know this codebase better than a grep does.
- `calendar_metrics.py` / `calendar_export.py`: `--year` now defaults to
  `datetime.now().year` instead of `2026`, and `calendar_metrics.py` now
  looks for `goals/{year}.yaml` instead of a hardcoded `goals/2026.yaml`
  (will raise a clear error if that file doesn't exist for the year
  requested — make sure `goals/2027.yaml` exists before New Year's).
- `web/lib/api.ts`: found and fixed a **real, pre-existing bug** unrelated
  to the year-hardcode sweep — the backend (`api/routers/cfb.py`) already
  returns `meets_publish_bar` on every pick, but the `CfbPick` TypeScript
  interface never declared it, so `app/cfb/page.tsx` was reading an
  untyped field. Added it to the interface. Confirmed `npx tsc --noEmit`
  goes from 3 errors to 0 with this change.

**Test performed:** ran `python -m compileall` on all four touched Python
files and `npx tsc --noEmit` in `web/` against the real repo checkout — all
clean.

No deploy steps beyond extracting the tarball.

---

## 2. `tz_utils.py` — new shared timezone module

File: `scripts/tz_utils.py` (new)

Pins "today," "this year," and "% of year elapsed" to `America/Denver` via
`ZoneInfo`, regardless of what timezone the process happens to be running
under. Import `today_denver()`, `denver_year()`, `year_progress_pct()`, or
`log_timestamp()` instead of calling `datetime.now()` / `date.today()`
directly for anything user-facing.

**I did not do a full sweep of every `datetime.now()` call in the repo** —
that's a bigger, riskier change than 5-days-away-from-the-machine calls for.
I wired it into the two spots that most directly match the bug you
described ("UTC habits showing as next day"):

- `api/routers/habits.py` — this is the actual `/api/habits/today` endpoint
  that decides what "today" is for the habit checklist. It was calling
  `date.today()` three times (checklist date, log lookup, and the
  fallback-quote-of-the-day index). All three now use `today_denver()`.
  **This is almost certainly the actual fix for the bug you flagged** —
  everything else in this patch is secondary.
- `scripts/daily_sync.py` — the log-directory date (`data/daily/{today}/`)
  now uses `today_denver()` instead of naive `datetime.now()`.

Everywhere else that touches dates (habits_pipeline.py, other API routers,
report generators) still uses the old pattern. If the habits fix doesn't
fully resolve what you were seeing, that's the next place to look — say the
word and I'll do a fuller sweep next session.

**Test performed:** imported and ran `tz_utils` standalone (confirmed
`today_denver()` / `year_progress_pct()` return correct values — 2026-07-03
→ 50.41% through the year, correct). Imported the patched
`api/routers/habits.py` with `fastapi` installed and called `_load_today()`
— works. Imported and ran `daily_sync.py` after the patch — `YEAR` resolves
correctly and the module loads without error.

No deploy steps beyond extracting the tarball and restarting FastAPI.

---

## 3. Four new dbt marts

Files: `dbt/models/marts/mart_goal_pacing.sql`,
`dbt/models/marts/core__life_events.sql`,
`dbt/models/marts/mart_weekly_scorecard.sql`,
`dbt/models/marts/mart_training_load.sql` (all new)

### mart_goal_pacing
Extends `mart_goal_progress` with `pace_status`
(`ahead` / `on_track` / `at_risk` / `behind` / `complete` / `binary`) by
comparing `progress_ratio` against how far through the year we are. Binary
(bool) goals get their own bucket since "% of target" doesn't apply to them.

### core__life_events
Universal event timeline — currently unions running activities (Strava),
habit completions, and books finished (Hardcover) into one table with
`event_date`, `domain`, `event_type`, `title`, `value`. This is the Phase 3
foundation piece from the roadmap. Add a new CTE + union branch per domain
as more sources come online — comments in the file point to the two most
obvious next additions (CrossFit sessions, calendar events).

### mart_weekly_scorecard
Weekly rollup of runs/miles, habit completions, and books finished, joined
against a **snapshot** (not historical point-in-time) of goal pacing
counts. Read the comment at the top of the file — the goal-pacing columns
repeat the *current* pacing standing across every week row, since ONS
doesn't persist historical goal-progress snapshots yet.

### mart_training_load — needs one extra step first
CTL/ATL/TSB (chronic/acute training load, training stress balance) plus a
green/yellow/red readiness signal, combining Strava + SugarWOD. **This one
has a real prerequisite**: SugarWOD data currently only exists as a CSV
(`data/sugarwod/processed/workouts_clean.csv`), not a DuckDB table, so
there's nothing for dbt to reference yet. I wrote a loader for this
(see section 4) — run it once before this mart will build.

The load model itself is intentionally simple: `running_minutes + (crossfit_sessions × 45)`,
i.e. duration-based, not heart-rate-based. It's a trend indicator, not a
physiological measurement — worth revisiting once/if heart-rate data is
consistently available.

**Test performed:** this is the part I was most careful about, since I
can't touch your real warehouse. I built a synthetic DuckDB file with the
*actual* table shapes from your pipelines (`strava.activities` per
`pipelines/strava_pipeline.py`, `raw.raw_goals` / `raw.raw_goal_progress`
per the real staging models, `hardcover.books_read` per
`pipelines/hardcover_pipeline.py`, and a `sugarwod.workouts` table matching
the loader in section 4), pointed a throwaway dbt profile at it, and ran
`dbt run --select mart_goal_pacing core__life_events mart_weekly_scorecard mart_training_load`
against the real, unmodified SQL files. All four built successfully, and I
queried the output to sanity-check the numbers (pacing math, event union,
weekly aggregation, and CTL/ATL decay all came out correct). This doesn't
guarantee your real data has no surprises — dbt run against your actual
warehouse is the real test — but it does mean the SQL is not broken and the
logic does what it's supposed to on realistic data.

### Deploy steps

```bash
lsof -ti:8000 | xargs kill -9   # stop FastAPI if not already stopped

cd ~/life-os-2026
python3 scripts/load_sugarwod_to_duckdb.py --dry-run   # sanity check first
python3 scripts/load_sugarwod_to_duckdb.py             # then for real

cd dbt
dbt run --select mart_goal_pacing core__life_events mart_weekly_scorecard mart_training_load

cd ..
uvicorn api.main:app --reload --port 8000 &   # restart FastAPI
```

If `mart_training_load` fails with something like `Table with name
"sugarwod.workouts" does not exist`, the loader step above didn't run or
didn't find the CSV — check `data/sugarwod/processed/workouts_clean.csv`
exists first.

---

## 4. `load_sugarwod_to_duckdb.py` — new prerequisite script

File: `scripts/load_sugarwod_to_duckdb.py` (new)

Stopgap loader that writes the cleaned SugarWOD CSV into DuckDB as a real
`sugarwod.workouts` table, the same way every other domain already lands
via DLT. Safe to re-run any time you re-import a fresh SugarWOD export.
`--dry-run` previews row count and schema without writing.

This should eventually become a proper DLT resource like the others — it's
a plain CSV-to-table write for now, which is fine as a bridge but not the
long-term pattern.

---

## 5. GitHub Actions — first real deploy of this track

Files: `.github/workflows/ci.yml`, `.github/workflows/picks-validation.yml`,
`.github/dependabot.yml` (all new — `.github/workflows/` didn't exist in the
repo at all before this patch, despite earlier sessions describing these as
"built")

### ci.yml — runs on every push/PR, GitHub-hosted runners
Four jobs: Python syntax (`compileall`), a hardcode-audit grep (fails if it
finds a literal comparison against last year's number — the same class of
bug that was in `fitness_metrics.py`), `dbt parse` (validates Jinja/SQL
without needing a live warehouse), and `npx tsc --noEmit` for the Next.js
app.

**Test performed:** ran all four checks by hand against the patched repo —
Python compiles clean, hardcode grep finds nothing, `dbt parse` succeeds,
`tsc --noEmit` passes (after the `api.ts` fix in section 1 — without that
fix, this job would have gone red on the very first push, for a reason
unrelated to anything else in this patch).

### picks-validation.yml — Thursday CFB picks report
Targets `runs-on: self-hosted` because it needs your real `ons.duckdb` and
`.env` credentials, which no GitHub-hosted runner has. **This will queue
and never run until the Mac mini is registered as a self-hosted runner**
(`python scripts/setup_runner.py` — still on the roadmap backlog, not part
of this patch). That's expected, not a bug — I didn't want to quietly build
something that looks live but isn't.

### dependabot.yml
Weekly (Monday) dependency PRs for pip, the `web/` npm project, and GitHub
Actions versions themselves.

### Deploy steps

```bash
cd ~/life-os-2026
git add .github/
git commit -m "Add CI, picks-validation, and dependabot workflows"
git push
```

Then check the **Actions** tab on GitHub — `ci.yml` should run
automatically on the push and go green. `picks-validation.yml` will show as
queued/waiting for a runner until the self-hosted runner is registered.

---

## Things I checked but did NOT change

- **`api/routers/fitness.py`** and other files matching `fitness_summary` —
  confirmed nothing else reads the old hardcoded filename.
- **A remaining `2026` reference** exists in `README.md` /
  `docs/` — left alone, since those are prose/docs, not logic, and the
  hardcode audit only checks `.py` files under `api/`, `pipelines/`,
  `scripts/`.
- **Full `tz_utils` adoption** across every `datetime.now()` call site in
  the repo — deliberately scoped down to the two highest-value spots (see
  section 2). A fuller sweep is a reasonable next task if you want it.
- **`generate_morning_brief.py`**, **`generate_weekly_review.py`**, and
  **`notify.py`**'s wiring into `daily_sync.py` — these came up in earlier
  session summaries as built, but I didn't find `generate_morning_brief.py`
  or `generate_weekly_review.py` anywhere in the current repo when I
  checked. If they exist somewhere outside the repo (a sandbox session that
  never got tarball'd over), that's worth tracking down — otherwise they
  need to be rebuilt.

---

## 6. ROADMAP.md update

File: `ROADMAP.md` (modified — full file included, overwrites the one in
the repo root)

Added a full "Mandarin Study System" section (data model, phased v1/v2/v3
build plan, open design questions) and slotted it into the Domain Backlog
Priority list at #4 — ahead of Career Impact Ledger and manual financial
tracking, per explicit request, since it's a daily-use habit tool rather
than a passive tracker. Nothing in this section has been built yet — it's
planning only, ⚪ Idea status throughout, ready for you to start on when
you're back or hand to me next session.

**No deploy steps beyond extracting the tarball** — it's a doc, not code.

---

## Full file list in this patch

```
.github/dependabot.yml                          (new)
.github/workflows/ci.yml                        (new)
.github/workflows/picks-validation.yml          (new)
api/routers/habits.py                           (modified)
dbt/models/marts/core__life_events.sql          (new)
dbt/models/marts/mart_goal_pacing.sql           (new)
dbt/models/marts/mart_training_load.sql         (new)
dbt/models/marts/mart_weekly_scorecard.sql      (new)
scripts/calendar_export.py                      (modified)
scripts/calendar_metrics.py                     (modified)
scripts/daily_sync.py                           (modified)
scripts/fitness_metrics.py                      (modified)
scripts/load_sugarwod_to_duckdb.py              (new)
scripts/tz_utils.py                             (new)
web/lib/api.ts                                  (modified)
ROADMAP.md                                      (modified — planning only)
```

## Suggested run order on the Mac mini

1. Extract tarball
2. Stop FastAPI
3. `python3 scripts/load_sugarwod_to_duckdb.py --dry-run`, then for real
4. `cd dbt && dbt run --select mart_goal_pacing core__life_events mart_weekly_scorecard mart_training_load`
5. Restart FastAPI, spot-check `/api/habits/today` returns the correct date
6. `git add .github/ && git commit && git push`, confirm `ci.yml` goes green in the Actions tab
7. `python tests/smoke_test.py` as a final overall sanity check
