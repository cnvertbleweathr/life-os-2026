# ONS Product Roadmap

Last updated: 2026-06-17

---

## What ONS Is

ONS is a local-first personal data platform, automation layer, and intelligence system.

It began as a personal operating system for tracking goals but has evolved into a modular analytics platform that ingests real-world data, models progress, generates artifacts, and uses AI to reduce manual overhead.

The platform is intentionally designed around the same principles used in modern analytics stacks:

- Declarative goals
- Scripted ingestion
- Explicit raw / processed / metrics layers
- Idempotent daily syncs
- Append-oriented historical tracking
- Automated artifact generation
- Agent-assisted enrichment
- Local-first development with future cloud portability

---

## The Three Questions ONS Must Answer

> **What is happening?**
> **Why does it matter?**
> **What should I do next?**

The platform has matured past "collect more data." The next phase focuses on helping ONS notice patterns, explain what matters, surface risks, recommend useful next actions, and reduce cognitive overhead — without making life feel overly quantified.

---

## Status Legend

- 🟢 **Done** — shipped and working
- 🟡 **In Progress** — partially built or needs wiring
- 🔵 **Planned** — scoped, not started
- ⚪ **Idea** — not yet scoped

---

## Platform Milestones

| # | Milestone | Goal |
|---|-----------|------|
| 1 | **Stabilize Daily Operations** | Daily sync runs unattended with clear logs, health summaries, backups, non-interactive failure handling |
| 2 | **Productize the Dashboard** | FastAPI + Next.js replacing Streamlit — accessible from anywhere via Tailscale |
| 3 | **Activate OpenClaw** | AI layer answers all three questions — morning brief, goal pacing, weekly review, recommendations |
| 4 | **Expand Warehouse Discipline** | dbt tests, mart documentation, source freshness checks, data contracts |
| 5 | **Snowflake / MotherDuck Experimentation** | Mirror selected marts to cloud; evaluate managed warehouse patterns |

---

## OpenClaw — AI Intelligence Layer

OpenClaw is the AI layer that sits above the data and talks to you. It is the answer to "what should I do next." It is only possible because ONS has been building the data foundation to support it.

### What OpenClaw does

- Writes the daily morning brief
- Detects goal pacing risk before it becomes a problem
- Generates the weekly review every Sunday
- Cross-references HRV + soreness + meeting load → training recommendation
- Surfaces KGLW gap tracker and setlist probability before a show
- Tells you which CFB signals are performing this season vs backtest
- Generates career accomplishment summaries quarterly
- Tracks which recommendations were accepted and which led to action

### Foundation required before OpenClaw can work

- Universal Event Table — one normalized timeline AI can reason over
- Goal Pacing mart — required pace, risk status, variance from expected
- Data Freshness tracking — know when data is stale before surfacing it
- Daily subjective check-in — energy/mood/soreness/stress baseline

### Roadmap

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Universal Event Table (`core.life_events`) | Normalize events across all domains — the foundation for everything |
| 🔵 | Goal Pacing mart (`mart_goal_pacing`) | Required weekly pace, variance, risk status: ahead/on_track/at_risk/behind/complete |
| 🔵 | Data freshness tracking (`ops.pipeline_runs`) | Per-source: last_attempted, last_success, rows_loaded, status, error |
| 🔵 | Morning brief generator | Claude API + goal pacing + calendar + weather + open actions |
| 🔵 | Weekly AI review | Sunday generation: what improved, what slipped, 3 priorities, 1 thing to stop, 1 to celebrate |
| 🔵 | Daily check-in form | 30 seconds: energy/mood/focus/sleep/soreness/stress 1-5 + optional note |
| 🔵 | AI Audit Trail (`ai.generations`) | Track every AI artifact: prompt version, model, source marts, latency, user rating, acted_on |
| 🔵 | Recommendation tracking (`ai.recommendations`) | Which recs were followed, which helped, which were ignored |
| 🔵 | Morning context mart (`mart_morning_context`) | Pre-aggregated daily inputs for brief generation |
| 🔵 | Weekly scorecard mart (`mart_weekly_scorecard`) | Input to weekly review generation |
| 🔵 | Store generated artifacts | Don't regenerate on load — store in `ai.weekly_reviews`, `reports/daily/`, `reports/weekly/` |
| ⚪ | Natural-language querying | "How many miles did I run in April?" over DuckDB/dbt marts |

---

## P0 — Platform Stabilization

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | `run_if_exists` enforced in `daily_sync.py` | Missing path → skipped, not crash |
| 🟢 | Required step failure aborts run | `aborted_at` set, remaining steps skipped |
| 🟢 | Daily sync health summary artifact | `health.txt` per run — ok/skipped/failed counts, stderr tail |
| 🟢 | DuckDB backup script | `backup_duckdb.py` — timestamped copies, 7-day retention |
| 🟢 | DuckDB backup launchd plist | `com.ons.backup-duckdb.plist` — 2am nightly |
| 🟢 | Daily sync launchd plist | `com.ons.daily-sync.plist` — 9am daily |
| 🟢 | Timezone hardening | `tz_utils.py` — `today_denver()`, `denver_year()`, `year_progress_pct()` |
| 🟢 | Remove hardcoded 2026 (11 files) | All replaced with `datetime.now().year` |
| 🟢 | Smoke tests | `tests/smoke_test.py` — 18 checks, 4 groups |
| 🟢 | GitHub Actions CI | 5 jobs: syntax, CFB model integrity, hardcode audit, schema, TypeScript |
| 🔵 | Wire `tz_utils.py` across codebase | Replace `datetime.now()` with `today_denver()` in habit/calendar scripts |
| 🔵 | Wire `notify.py` into `daily_sync.py` | `sync-fail` alert on required step failure |
| 🔵 | ntfy topic configured | Set `NTFY_TOPIC` in `.env` |
| 🔵 | Token health checks | Detect expired auth before sync fails |
| 🔵 | Spotify OAuth non-interactive | Token refresh without browser |
| 🔵 | Mac Mini health dashboard | Disk space, DuckDB size, dbt last run, backup status, Tailscale, failed jobs |
| 🔵 | Data freshness and quality center | Per-source freshness, dbt tests, expected row counts |

---

## UI Rebuild — Next.js + FastAPI

### Architecture
```
Mac mini
├── FastAPI   api/              Python — DuckDB query layer (port 8000)
└── Next.js   web/              TypeScript — UI layer (port 3000)
Remote access: Tailscale or Cloudflare Tunnel
Domain: capuchin.cyou
```

### Status

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | Design concept approved | Bento grid, dark sidebar, forest green accent |
| 🟢 | FastAPI layer — all 9 routers | `ons-api.tar.gz` — ready to deploy |
| 🟢 | All 9 Next.js pages built | `ons-web.tar.gz` — Home, CFB, Habits, Fitness, Music, Reading, Goals, Shows, Sports |
| 🟢 | CFB team logos | `TeamLogo` component, 124-team ID map, `download_cfb_logos.py` |
| 🟢 | `ARCHITECTURE.md` | Full data flow diagram |
| 🟢 | `REMOTE_ACCESS.md` | Tailscale + Cloudflare Tunnel setup guide |
| 🔵 | Deploy on Mac mini | Extract archives, `uv add`, `npm install` |
| 🔵 | Download logos locally | `python scripts/download_cfb_logos.py` |
| 🔵 | Tailscale setup | 15 min — see `REMOTE_ACCESS.md` |
| 🔵 | capuchin.cyou DNS | Point to production app |
| 🔵 | Decommission Streamlit | Remove `app/` after parity confirmed |
| 🔵 | OpenClaw morning brief page | Daily AI brief surfaced on Home page |
| 🔵 | OpenClaw weekly review page | Sunday review with domain breakdown |
| 🔵 | KGLW page | Setlists, YouTube recordings, gap tracker, pre-show playlist |

---

## CFB Betting — Sports Modeling Lab

### Validated Model Results
```
318 bets · 224-94 · 70.4% win rate · +34.5% ROI · 4/4 seasons profitable
Walk-forward 2022–2025 · prior-season PPA · no lookahead bias
Weeks 1-4: +39.5% ROI (strongest window)
```

### Signal Stack
| Signal | ΔROI removed | Per-season | Status |
|--------|-------------|------------|--------|
| Success rate | -16.0% | 4/4 | ✅ Active |
| Team tier | -7.2% | 4/4 | ✅ Active |
| Spread range | -5.1% | 3/4 | ✅ Active |
| Coach change | -3.5% | 4/4 | ✅ Active |
| Conference | -1.7% | 3/4 | ✅ Active |
| Returning production | -1.4% | 4/4 | ✅ Active |
| Recruiting/talent | -14.4% aggregate | 4/4 | ✅ Active |
| SP+ alignment | 0.0% | 0/4 | ❌ Disabled |
| Defensive havoc | 0.0% | 0/4 | ❌ Disabled |

### Roadmap

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | Walk-forward backtester v3 | Canonical `score_game()` |
| 🟢 | Per-season ablation | Identifies consistent vs era-specific signals |
| 🟢 | Unified scorer | `generate_picks.py` imports `score_game()` directly |
| 🟢 | Weekly picks report | `generate_picks_report.py` — full Thursday briefing |
| 🟢 | CFB postmortem report | `generate_postmortem.py` — P&L, signal win rates, season log |
| 🟢 | Push notifications | `notify.py` — ntfy.sh picks alert + sync alerts |
| 🟢 | CFB team logos | 124-team ID map, CDN + local download path |
| 🔵 | Wire `notify.py` → picks + sync | Thursday picks alert, sync failure alert |
| 🔵 | Model score calibration audit | 70-79 outperforms 90-99 — investigate signal stacking |
| 🔵 | Re-run ablation at 2026 Week 4 | Recalibrate weights against real data |
| 🔵 | Line movement signal | `track_lines.py` → `score_game()` adjustment |
| 🔵 | 2026 live performance tracker | Weekly P&L vs model_score, rolling ROI, season log dashboard |
| 🔵 | NFL betting pipeline | The Odds API — same dbt mart pattern |
| ⚪ | MLB betting pipeline | The Odds API + Statcast |
| ⚪ | CLV dataset | Build from `track_lines.py` snapshots over a season |

---

## Goals Page — Fixed

| Status | Item |
|--------|------|
| 🟢 | NameError: YEAR defined before `st.title()` |
| 🟢 | SQL f-string interpolation fixed |
| 🟢 | Habit % recalculated from `days_done / DAYS_IN_YEAR` |
| 🟢 | Binary done check handles `"max"` / `"director"` |
| 🟢 | Leap year logic corrected |
| 🔵 | Goal pacing mart — move beyond current vs target |
| 🔵 | Plaid integration for Finance goals actuals |

---

## Music — KGLW Integration

### API
KGLW.net API v2 — no auth, JSON, setlists/songs/venues/jamcharts/links/metadata/embeds

### Roadmap

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | `kglw_pipeline.py` | Ingest shows attended, setlists, jam chart entries, links via DLT |
| 🔵 | Shows page integration | Pull venue history when Gizz show appears in Denver feed |
| 🔵 | KGLW Next.js page | Attended shows with embedded setlists, YouTube player |
| 🔵 | Song gap tracker | Songs overdue for return — personal pre-show wishlist |
| 🔵 | Jam chart cross-reference | Which legendary versions did you personally witness? |
| 🔵 | Pre-show playlist generator | Likely setlist songs → Spotify playlist via venue history |
| 🔵 | Personal song stats | Most-heard live, album representation across attended shows |
| 🔵 | Setlist.fm integration | Concert history across all artists (not just Gizz) |
| 🔵 | YouTube Data API | Search recordings by date, embed player, pull view counts |
| ⚪ | Tour set probability engine | Frequency model from current tour setlists |

---

## Shows

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | Denver concerts — AEG + Ticketmaster | Daily, artist matching |
| 🟢 | Shows Next.js page | Artist match highlighting, upcoming list |
| 🔵 | Venue map | Denver map with show pins |
| 🔵 | Personal attendance log | Mark attended, rate shows |
| 🔵 | KGLW show cross-reference | Link Denver shows to KGLW setlist data |
| ⚪ | Pre-show playlist | Auto-generate Spotify playlist before a show |
| ⚪ | Setlist.fm attendance history | Full concert history, not just Gizz |

---

## Fitness & Health

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | Strava (running) | Daily, OAuth, YTD summary |
| 🟢 | SugarWOD (CrossFit) | CSV import, attendance + performance |
| 🟢 | WOD scraper | Park Hill CrossFit via Playwright |
| 🔵 | Apple Health | Sleep, HRV, resting HR, VO2 max, steps, body weight |
| 🔵 | Training readiness mart | 7-day + 28-day load, consecutive days, recovery signals |
| 🔵 | Training load mart (`mart_training_load`) | CTL/ATL/TSB model across Strava + CrossFit |
| 🔵 | Daily subjective check-in | energy/mood/focus/sleep/soreness/stress → `raw.daily_checkin` |
| 🔵 | Readiness signal | green/yellow/red based on HRV + load + check-in |
| 🔵 | Strava webhooks | Event-driven ingestion vs scheduled polling |
| 🔵 | Whoop or Garmin Connect | Recovery %, strain, sleep stages |
| 🔵 | OpenWeatherMap | Denver forecast — correlate weather vs running pace and attendance |
| ⚪ | Injury risk signals | Pain notes + load spikes → `mart_injury_risk_signals` |

---

## Spotify & Music Analytics

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | Extended streaming history | Daily ingestion |
| 🟢 | Daily 10 playlist | Generated daily with AI art + description |
| 🔵 | Fix 5 + 15 bucket logic | Bucket B sometimes produces fewer than 15 tracks |
| 🔵 | Move Daily 10 rules to config | `config/daily10.yaml` |
| 🔵 | Music discovery analytics | New artists, exploration ratio, familiarity ratio |
| 🔵 | Listening pattern mart | By time of day, weekday, workout vs focus vs passive |
| 🔵 | Monthly soundtrack | Top artists/tracks per month → personal music story |
| 🔵 | Artist loyalty mart | Repeat vs one-time vs rediscovered artists |
| 🔵 | Daily 10 history mart | Track playlist ID, event, image status, performance |

---

## Reading

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | Hardcover (reading) | Daily, GraphQL |
| 🟢 | Reading Next.js page | In-progress, books read, fiction/nonfiction split |
| 🔵 | Letterboxd pipeline | RSS, no auth — `letterboxd_pipeline.py` built, needs wiring |
| 🔵 | Reading velocity mart | Pages per day, avg days to finish by genre |
| 🔵 | Plex viewing analytics | Watch history, completion rate, genre distribution |
| ⚪ | Goodreads alternative | Letterboxd for books — if Hardcover insufficient |

---

## Family & Personal Life

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | Google Calendar (date nights, events) | Mon/Thu |
| 🔵 | Family ritual tracking | Date nights, family outings, no-work evenings, one-on-one time |
| 🔵 | Family presence mart | `mart_family_rituals`, `mart_couple_time` |
| 🔵 | Family memory timeline | Private: occurred_at, title, one-sentence memory, photo, quote, tags |
| 🔵 | Calendar time allocation | Work vs family vs fitness vs personal — planned vs actual |
| 🔵 | Focus time mart | Meeting load vs deep work blocks |
| ⚪ | Monthly family recap | AI-generated from memory timeline |
| ⚪ | "On this day" memories | Surfaces family memories from previous years |

---

## Career

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Career Impact Ledger | `raw.career_events` — projects, wins, feedback, GitHub, stories |
| 🔵 | Career impact mart | `mart_career_impact`, `mart_leadership_signals` |
| 🔵 | AI resume bullets | `ai.resume_bullets` — generated from career events |
| 🔵 | AI STAR stories | `ai.interview_stories` — generated from career events |
| 🔵 | Monthly accomplishment summary | AI-generated from career events mart |
| 🔵 | Promotion case draft | AI-generated when triggered |
| ⚪ | Director/VP readiness signals | Leadership scope analysis over time |
| ⚪ | Performance review draft | Auto-generated from career events + goal progress |

---

## Finance

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Manual tracking phase | Monthly CSV: Roth IRA, HSA, brokerage, savings rate, net worth |
| 🔵 | Financial contributions mart | `mart_financial_contributions`, `mart_savings_rate` |
| 🔵 | Net worth snapshot mart | `mart_net_worth_snapshot` |
| 🔵 | Financial goal progress | Link to goals page — Roth IRA, HSA actuals |
| 🔵 | Finance dashboard | Private — never enters public publishing path |
| ⚪ | Plaid integration | Phase 4 — transaction data, spending by category |

---

## Data Ingestion

| Status | Source | Current State | Next Step |
|--------|--------|--------------|-----------|
| 🟢 | Spotify | Extended history, Daily 10 | Fix 5+15 bucket |
| 🟢 | Google Calendar | Calendar metrics | Time allocation mart |
| 🟢 | Hardcover | Reading metrics | Velocity mart |
| 🟢 | SugarWOD | CrossFit attendance | — |
| 🟢 | Strava | Running metrics | Webhooks, extended efforts |
| 🟢 | Pixela | Habit metrics | — |
| 🟢 | AEG/Ticketmaster | Denver shows | KGLW cross-reference |
| 🟢 | CFBD | CFB historical 2021-2025 | Weekly during season |
| 🟢 | WOD scraper | Park Hill CrossFit | — |
| 🟡 | Letterboxd | Pipeline built | Wire into daily_sync |
| 🟡 | Insights pipeline | Built but dormant | Wire into weekly sync |
| 🔵 | KGLW.net API | Not started | Setlists, jams, links, embeds |
| 🔵 | Setlist.fm | Not started | Full concert history all artists |
| 🔵 | YouTube Data API | Not started | KGLW recordings search + embed |
| 🔵 | Apple Health | Not started | Sleep, HRV, steps, weight |
| 🔵 | OpenWeatherMap | Not started | Denver daily forecast |
| 🔵 | Whoop or Garmin | Not started | Recovery %, strain, sleep |
| 🔵 | Plaid | Not started | Finance actuals |
| 🔵 | The Odds API | Not started | NFL/MLB lines |
| 🔵 | Discogs | Not started | Vinyl collection if applicable |
| 🔵 | Untappd | Not started | Beer check-ins |
| ⚪ | Home Assistant | Not started | Temperature, energy, presence |
| ⚪ | Aviationstack | Not started | Flight tracking for travel context |

---

## Infrastructure & Operations

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | Mac mini daily sync via launchd | `com.ons.daily-sync.plist` — 9am |
| 🟢 | DuckDB nightly backup via launchd | `com.ons.backup-duckdb.plist` — 2am |
| 🟢 | GitHub repo | `cnvertbleweathr/life-os-2026` |
| 🟢 | Smoke tests | `tests/smoke_test.py` — 18 checks |
| 🟢 | GitHub Actions CI | ci.yml, picks-validation.yml, motherduck-sync.yml |
| 🔵 | Install launchd plists on Mac mini | Both need `launchctl load` |
| 🔵 | Tailscale remote access | 15 min setup |
| 🔵 | MotherDuck free tier | Mirror selected marts; cloud path for FastAPI + Vercel |
| 🔵 | Mac Mini health monitoring | Disk, CPU, DuckDB size, Plex, Tailscale, failed jobs |
| 🔵 | Token health checks | Spotify, Strava, Google, OpenAI |
| 🔵 | Restore test for DuckDB backup | Prove backups are usable |
| 🔵 | `LETTERBOXD_USERNAME` in `.env` | Required for Letterboxd pipeline |
| 🔵 | Public/private publishing controls | `privacy_level`: private / household / public |

---

## Foundational Data Models

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | `core.life_events` | Universal event table — one timeline AI reasons over |
| 🔵 | `ops.pipeline_runs` | Per-source freshness: attempted, success, rows, error |
| 🔵 | `raw.daily_checkin` | Daily subjective: energy/mood/focus/sleep/soreness/stress |
| 🔵 | `ai.weekly_reviews` | Stored weekly review artifacts |
| 🔵 | `ai.recommendations` | Which recs accepted, completed, led to action |
| 🔵 | `ai.generations` | Audit trail: model, prompt version, latency, token usage, rating |
| 🔵 | `raw.career_events` | Career impact log |
| 🔵 | `main_marts.mart_goal_pacing` | Required pace, variance, risk status per goal |
| 🔵 | `core.actions` | Canonical actions from recommendations, events, alerts, and capture |
| 🔵 | `raw.capture_inbox` | Universal holding area for manual and conversational input |
| 🔵 | `core.entities` | Shared entity registry across domains |
| 🔵 | `core.entity_relationships` | Relationships among people, projects, events, goals, and decisions |
| 🔵 | `core.decisions` | Decision, rationale, alternatives, and eventual outcome |
| 🔵 | `core.lessons` | Reusable lessons from projects, experiments, and incidents |
| 🔵 | `core.experiments` | Personal intervention hypotheses, periods, metrics, and outcomes |
| 🔵 | `metadata.metrics` | Canonical metric definitions, ownership, grain, privacy, freshness |
| 🔵 | `ops.notification_rules` | Central notification policy, severity, quiet hours, and cooldowns |
| 🔵 | `ops.notifications` | Notification delivery, acknowledgement, and resolution history |
| 🔵 | `ops.api_usage` | API calls, model tokens, provider usage, and estimated cost |
| 🔵 | `ai.evaluations` | Accuracy, usefulness, groundedness, freshness, and actionability |
| 🔵 | `ai.claims` | Evidence and provenance for factual AI claims |
| 🔵 | `ai.feedback` | User feedback on recommendations, briefs, reviews, and claims |
| 🔵 | `ai.model_routes` | Model selection by task type, cost, quality, and privacy class |
| 🔵 | `main_marts.mart_daily_features` | One-row-per-day cross-domain analytical feature set |
| 🔵 | `main_marts.mart_goal_scenarios` | Projected goal outcomes under alternate assumptions |
| 🔵 | `main_marts.mart_changes_daily` | Material changes compared with the previous day |
| 🔵 | `main_marts.mart_changes_weekly` | Material changes compared with the previous week |
| 🔵 | `main_marts.mart_platform_cost` | Daily and monthly ONS cost by provider, feature, and domain |
| 🔵 | `main_marts.mart_morning_context` | Pre-aggregated daily inputs for brief generation |
| 🔵 | `main_marts.mart_training_load` | CTL/ATL/TSB across Strava + CrossFit |
| 🔵 | `main_marts.mart_time_allocation` | Calendar time by category: work/family/fitness/personal |
| 🔵 | `main_marts.mart_data_freshness` | Per-source health: healthy/stale/failed/never_run |

---

## Technical Debt

| Priority | Issue | Status | Resolution |
|----------|-------|--------|------------|
| P0 | DuckDB backup | 🟢 Built | Deploy and test on Mac mini |
| P0 | Daily sync reliability | 🟢 Fixed | Deploy hardened version |
| P0 | Spotify OAuth browser auth | 🔵 Open | Token health check + graceful fail |
| P1 | 2026 hardcodes | 🟢 Fixed | 11 files updated |
| P1 | Daily 10 bucket rules hardcoded | 🔵 Open | Move to `config/daily10.yaml` |
| P1 | Streamlit UX limits | 🟢 Replaced | Next.js rebuild built, pending deploy |
| P1 | CFB model score not monotonic | 🔵 Open | Investigate after 2026 Week 4 |
| P1 | `tz_utils.py` not yet wired | 🟡 Built | Import in habit/calendar scripts |
| P2 | Mixed old/new pipeline patterns | 🔵 Open | Consolidate after insights wired |
| P2 | Limited test coverage | 🟡 Partial | Smoke tests done, unit tests pending |

---

## Documentation

| Status | Document | Notes |
|--------|----------|-------|
| 🟢 | `README.md` | Project overview |
| 🟢 | `ROADMAP.md` | This file |
| 🟢 | `ARCHITECTURE.md` | Full data flow diagram |
| 🟢 | `REMOTE_ACCESS.md` | Tailscale + Cloudflare Tunnel guide |
| 🔵 | `RUNBOOK.md` | Operational recovery steps |
| 🔵 | `DATA_DICTIONARY.md` | Metric and table documentation |
| 🔵 | `DECISIONS.md` | ADR-style technical decisions |

---

## Canonical Build Sequence

The authoritative implementation order for the next phase. Domain work is subordinate to this sequence.

### Phase 1 — Deploy What Is Already Built
1. Deploy FastAPI on the Mac mini
2. Deploy Next.js on the Mac mini
3. Download and validate local CFB assets
4. Confirm page and API parity with Streamlit
5. Configure Tailscale access
6. Register the Mac mini GitHub Actions runner
7. Install and activate launchd services
8. Confirm scheduled sync and backup jobs
9. Decommission Streamlit after parity is verified

### Phase 2 — Reliability and Trust
1. Implement `ops.pipeline_runs`
2. Add per-source freshness status
3. Complete DuckDB restore testing
4. Add backup checksum verification
5. Add encrypted off-machine backup
6. Add FastAPI Pydantic response contracts
7. Generate the OpenAPI schema
8. Generate the TypeScript API client
9. Add API compatibility checks in CI
10. Deploy application observability

### Phase 3 — Capture and Context
1. Build `core.life_events`
2. Build `raw.capture_inbox`
3. Add the mobile quick-capture form
4. Add capture classification and review
5. Build `core.actions`
6. Add action status and outcome tracking
7. Add the personal knowledge layer
8. Add approved Gmail structured extractors

### Phase 4 — Intelligence
1. Build `main_marts.mart_goal_pacing`
2. Build `main_marts.mart_daily_features`
3. Build `main_marts.mart_morning_context`
4. Generate and store the morning brief
5. Generate and store the weekly review
6. Add `ai.claims`
7. Add `ai.evaluations`
8. Add `ai.feedback`
9. Add recommendation-to-action linking
10. Enforce human approval boundaries

### Phase 5 — Action and Learning
1. Add scenario planning
2. Add personal experiment tracking
3. Add the notification policy engine
4. Add action outcome analysis
5. Add recommendation effectiveness reporting
6. Add the What Changed view
7. Add the personal changelog

### Phase 6 — Usability and Scale
1. Add Search Everything
2. Add the command palette
3. Add semantic search
4. Add model routing
5. Add platform cost accounting
6. Add public-site publishing
7. Add preview and production deployment environments

### Domain Backlog Priority

Domain work proceeds when the required platform foundation exists. Priority candidates:

1. KGLW pipeline
2. Apple Health
3. Open-Meteo or OpenWeatherMap
4. Career Impact Ledger
5. Manual financial tracking
6. Letterboxd wiring
7. Plex viewing analytics
8. Strava webhooks
9. Family memory timeline
10. Home Assistant


## Roadmap Scope Rule

The roadmap is now broad enough to support several years of development.

New items should only be added when they satisfy at least one of the following:

- Close a clear gap in the three core questions (what is happening / why does it matter / what should I do)
- Reduce manual effort
- Improve trust, reliability, privacy, or recovery
- Enable an existing planned capability
- Provide a meaningful learning opportunity
- Produce a concrete user-facing outcome

New APIs should not be added solely because they are available. The next phase should prioritize complete vertical slices over additional conceptual expansion.

---

## Guiding Principle

ONS should make the right action easier than the default action.

The platform should quietly collect reliable data, preserve meaningful context, surface important changes, explain why they matter, recommend practical actions, and measure whether those actions helped.

The goal is not to track everything. The goal is to create a trusted system where the most important things become visible, understandable, and easier to act on.

Life OS should not become another obligation. It should quietly collect reliable data, surface useful patterns, and help identify the most valuable next action — without making life feel like another job.

### What ONS should be able to tell you

- What is happening
- What is changing
- What needs attention
- What can be ignored
- What one action would create the most leverage
- Whether the last recommended action actually helped

---

## GitHub Actions — Learning Roadmap

Using ONS as a real-world environment to learn CI/CD, analytics engineering quality gates, secrets management, deployment automation, and platform engineering. 18 phases structured from fundamentals to advanced orchestration.

### Phase Status

| Phase | Name | Status | Notes |
|-------|------|--------|-------|
| 1 | CI Fundamentals | 🟢 Built | `ci.yml` — syntax, CFB model integrity, hardcode audit, schema, TypeScript |
| 2 | Reproducible Analytics Testing | 🟢 Built | `ci-analytics.yml` — fixture DuckDB, dbt run+test, Python matrix, security |
| 3 | dbt Quality Gates | 🟡 Partial | dbt runs in CI; not_null/unique/accepted_values tests need adding to models |
| 4 | Dependency Automation | 🟢 Built | `dependabot.yml` — Python, Actions, npm weekly on Monday |
| 5 | Security Automation | 🟡 Partial | pip-audit, bandit, ruff, secret scanning in ci-analytics; CodeQL pending |
| 6 | Python Compatibility Matrix | 🟢 Built | 3.12 + 3.13 matrix in ci-analytics.yml |
| 7 | Workflow Artifacts | 🟢 Built | dbt run_results.json, manifest.json, dbt docs uploaded on main |
| 8 | Mac Mini Self-Hosted Runner | 🔵 Planned | `mac-mini-refresh.yml` built — needs runner registration on Mac mini |
| 9 | Scheduled Life OS Workflows | 🟡 Partial | Daily schedule in mac-mini-refresh.yml — needs runner first |
| 10 | Manual Workflow Inputs | 🟢 Built | `workflow_dispatch` with domain + mode inputs in mac-mini-refresh.yml |
| 11 | Public Website CI/CD | 🔵 Planned | Privacy validation → static site → GitHub Pages or Vercel |
| 12 | Preview + Production Environments | 🔵 Planned | Environment-scoped secrets, manual approval for production |
| 13 | Privacy Validation Pipeline | 🔵 Planned | `privacy_level` field, block non-public data from deployment |
| 14 | Reusable Workflows | 🔵 Planned | Extract Python setup, dbt validation, fixture load into shared workflows |
| 15 | Workflow Caching | 🔵 Planned | Cache pip/uv/dbt packages — reduce CI time |
| 16 | Release Automation | 🔵 Planned | Semantic versioning, tagged releases, changelog, dbt docs publish |
| 17 | OpenClaw Integration | 🔵 Planned | Trigger brief + review generation from Actions after dbt completes |
| 18 | Notifications + Observability | 🔵 Planned | `mart_automation_health`, ntfy alerts, workflow duration tracking |

### Deploy sequence for next week

```bash
# 1. Deploy all four workflow files
mkdir -p .github/workflows
cp ci.yml picks-validation.yml motherduck-sync.yml \
   ci-analytics.yml mac-mini-refresh.yml \
   .github/workflows/

# 2. Deploy Dependabot
cp dependabot.yml .github/dependabot.yml

# 3. Deploy fixture loader
mkdir -p tests/fixtures
cp load_fixtures.py tests/fixtures/

# 4. Commit and push — watch first CI run
git add .github/ tests/
git commit -m "ci: full GitHub Actions suite — CI, analytics, runner, Dependabot"
git push origin main

# 5. Register Mac mini as self-hosted runner
python scripts/setup_runner.py    # prints the guide
# Then follow the guide in your browser
```

### Skills developed per phase

**Phases 1-3:** workflow triggers, jobs/steps, GitHub-hosted runners, dependency installation, exit codes, logs, branch protection, ephemeral environments, dbt lifecycle automation, data contracts

**Phases 4-7:** automated dependency maintenance, version pinning, supply-chain awareness, secrets management, static analysis, artifact retention, debugging failed workflows

**Phases 8-10:** self-hosted infrastructure, runner labels, machine permissions, job isolation, cron syntax, workflow concurrency, operational alerting

**Phases 11-13:** CI/CD, build pipelines, deployment jobs, hosting, DNS, rollback, policy-as-code, privacy engineering

**Phases 14-18:** workflow reuse, platform engineering, semantic versioning, release management, AI pipeline integration, service-level thinking, workflow analytics

### Suggested release milestones

| Version | Description |
|---------|-------------|
| v0.1.0 | DuckDB and dbt foundation |
| v0.2.0 | Goal progress dashboard |
| v0.3.0 | AI morning brief |
| v0.4.0 | Weekly review |
| v0.5.0 | Self-hosted automation |
| v1.0.0 | Integrated Life OS platform |

---

## dbt Wizard CLI

AI agent purpose-built for dbt development. Understands your project through a native metadata engine — lineage, compiled state, tests, contracts, run results. Works with dbt Core, no dbt Cloud account required. Bring your own Anthropic API key.

**Install (on Mac mini, after dbt is verified working):**
```bash
curl -fsSL https://public.cdn.getdbt.com/dbt-wizard/install/install-wizard.sh | sh
wizard providers configure anthropic   # uses ANTHROPIC_API_KEY from .env
cd ~/life-os-2026 && dbt parse         # builds target/ directory Wizard needs
wizard                                  # start a session
/overview                               # project summary
```

**Note:** Raw ANTHROPIC_API_KEY BYOK works. Claude.ai subscription does not (Anthropic ToS).

| Status | Use case | Notes |
|--------|----------|-------|
| 🔵 | Add dbt tests to key marts | `not_null`, `unique`, `accepted_values` on mart_goal_pacing, mart_cfbd_* |
| 🔵 | Generate mart documentation | Grain, sources, refresh cadence — auto-generated YAML |
| 🔵 | Refactor model naming | Rename fields consistently across all refs without manual find/replace |
| 🔵 | Investigate test failures | Trace lineage, propose fix, validate before surfacing |
| 🔵 | Add marts for new sources | Describe what you need, Wizard generates model + tests + docs |
| ⚪ | CI dbt quality gate | Wire Wizard validation into GitHub Actions ci-analytics.yml |

---

## Sports Betting Lab — NHL, NFL, NBA

Extend the CFB betting model architecture to hockey, football, and basketball.
Same methodology: walk-forward backtesting, per-season ablation, unified scorer,
no lookahead bias. Full 5-season historical download, factor analysis for ATS
and O/U, then signal validation before live picks.

### Data Sources

| Sport | API | Notes |
|-------|-----|-------|
| NFL | The Odds API + nfl_data_py | Historical odds, scores, advanced stats |
| NHL | The Odds API + hockey-reference scraper or NHL API | Lines, scores, Corsi/Fenwick |
| NBA | The Odds API + nba_api | Lines, scores, advanced box scores |

The Odds API covers historical odds for all three going back 5+ seasons.
Sport-specific stat APIs provide the advanced metrics needed for signal engineering.

---

### NFL Betting Research Agenda

**ATS factors to investigate (5 seasons 2020-2024):**
- Rest advantage (bye week, short week, Thursday game)
- Home/away efficiency gap (EPA per play, DVOA proxy)
- QB performance differential (passer rating, air yards)
- Offensive/defensive line strength (pressure rate, run blocking)
- Red zone efficiency differential
- Turnover margin and luck normalization
- Division game dynamics (familiarity, variance compression)
- Dome vs outdoor in bad weather
- Travel distance and time zone change
- Coaching staff change (new OC/DC)
- Injury-adjusted roster value
- Spread range buckets (3-7 field goal range has structural inefficiency)

**O/U factors to investigate:**
- Pace of play (plays per game, time of possession)
- Weather (temperature, wind, precipitation — strong O/U signal)
- Defensive line havoc (pressure without blitz)
- Dome games
- Primetime scoring inflation
- Starting QB O/U history

**Hypothesis to test:** The same PPA-gap + success-rate-parity pattern that works in CFB may have an NFL analog in EPA + DVOA parity situations.

---

### NHL Betting Research Agenda

**ATS / Puck line factors:**
- Corsi For % (possession proxy — strongest ATS signal in hockey)
- Fenwick % (unblocked shot attempts — less goalie noise than Corsi)
- PDO (save% + shooting% — regression signal, teams above 1.010 regress)
- Power play and penalty kill efficiency differential
- Back-to-back game fatigue (second game of B2B is exploitable)
- Goalie save percentage vs expected (goalie quality signal)
- Home ice advantage by arena (some buildings show stronger home effects)
- Rest differential (3+ days vs 1 day rest)
- Divisional rivalry variance

**O/U factors:**
- Team pace (shots per 60, scoring chances per 60)
- Both goaltenders' recent form
- Altitude (Denver home games — ball movement equivalent)
- Back-to-back on the road (tired teams play fewer possessions)

**Structural note:** NHL has the highest variance of the three sports due to goaltending randomness. Puck line (-1.5) betting often more efficient than moneyline for strong favorites.

---

### NBA Betting Research Agenda

**ATS factors:**
- Net rating differential (points per 100 possessions — strongest NBA signal)
- Rest advantage (back-to-back, 3-in-4, road trip length)
- Pace differential (fast vs slow team matchups create spread inefficiency)
- Offensive/defensive rating split (teams that win with defense vs offense)
- Home court advantage by arena (specific arenas show above-average home effects)
- Load management / rest for stars (injury-adjusted rotation depth)
- Schedule spot (end of long road trip, late game of homestand)
- Referee crew tendencies (foul rate, pace influence)
- Situational motivation (playoff positioning, nothing-to-play-for situations)
- Starting lineup stability vs rotation volatility

**O/U factors:**
- Combined pace (both teams' pace scores — most predictive O/U signal in NBA)
- Defensive rating of both teams
- Referee crew foul tendency (high-foul refs → more FTs → higher totals)
- Back-to-back game scoring depression
- Altitude (Denver Nuggets home games — documented scoring impact)

**Structural note:** NBA has the least variance of the three — stars dominate outcomes. Injury news the day of game is the most predictive single signal and requires a same-day data pipeline.

---

### Implementation Roadmap

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | NFL historical download | The Odds API + nfl_data_py, 2020-2024, ATS + O/U results |
| 🔵 | NHL historical download | The Odds API + NHL stats API, 2019-2024 |
| 🔵 | NBA historical download | The Odds API + nba_api, 2020-2024 |
| 🔵 | NFL dbt marts | mart_nfl_game_context, mart_nfl_line_accuracy (mirror CFB pattern) |
| 🔵 | NHL dbt marts | mart_nhl_game_context, mart_nhl_line_accuracy |
| 🔵 | NBA dbt marts | mart_nba_game_context, mart_nba_line_accuracy |
| 🔵 | NFL factor validation | ATS + O/U cover rates by factor bucket, 5-season consistency check |
| 🔵 | NHL factor validation | Corsi/Fenwick/PDO vs ATS, B2B fatigue, goalie signal |
| 🔵 | NBA factor validation | Net rating, pace, rest, B2B — per-season ablation |
| 🔵 | Walk-forward backtester (per sport) | Same pattern as backtest_walk_forward.py — no lookahead |
| 🔵 | Per-season ablation (per sport) | Consistency verdict per signal before activating |
| 🔵 | NFL scorer + picks | generate_nfl_picks.py importing score_game_nfl() |
| 🔵 | NHL scorer + picks | generate_nhl_picks.py importing score_game_nhl() |
| 🔵 | NBA scorer + picks | generate_nba_picks.py importing score_game_nba() |
| 🔵 | In-season pipeline wiring | Daily line tracking, weekly picks generation per sport |
| 🔵 | Same-day injury pipeline (NBA) | Injury news → roster adjustment → model score update |
| 🔵 | Sports Betting Lab page (Next.js) | Unified picks + model stats across all 4 sports |
| ⚪ | Closing line value tracking | CLV dataset per sport, model efficiency measurement |
| ⚪ | Cross-sport signal comparison | Does PPA-gap pattern generalize? EPA/Corsi/NetRtg comparison |
| ⚪ | Parlay/correlation analysis | Which same-game factors correlate — O/U and ATS independence |

### Key Principles (learned from CFB)

- **Walk-forward only.** No lookahead. Tiers and baselines built from prior seasons only.
- **Per-season ablation before activation.** A signal needs 3/5 profitable seasons minimum.
- **One canonical scorer per sport.** `score_game_nfl()`, `score_game_nhl()`, `score_game_nba()` — each in its own backtest file, each imported directly by the picks generator.
- **O/U gets its own model.** ATS and O/U have different signal stacks. Don't combine.
- **Validate before live.** Run full 5-season backtest before any live picks.
- **Disabled signals documented.** Same pattern as CFB — if ablation shows 0% ΔROI, disabled and documented.

### Season calendars

| Sport | Season | Line availability |
|-------|--------|-----------------|
| NFL | Sep–Feb | Lines posted Tuesday, sharpen Thu–Sat |
| NHL | Oct–Jun (playoffs) | Lines daily |
| NBA | Oct–Jun (playoffs) | Lines daily, same-day injury impact |

---

## Cross-Cutting Platform Capabilities

ONS has reached the point where the next major opportunity is to strengthen capabilities that connect domains together.

The platform should evolve from:

```
collect → model → display
```

into:

```
collect → model → understand → recommend → act → measure outcome
```

The final step — measuring whether a recommendation led to a useful outcome — is what distinguishes ONS from a dashboard, journal, or generic AI assistant.

---

### Recommended Build Order

**Phase 1 — Trust and Reliability**
`ops.pipeline_runs` · Semantic metrics registry · FastAPI response contracts · TypeScript client generation · Backup restore test · Application observability

**Phase 2 — Capture and Context**
`core.life_events` · `raw.capture_inbox` · Mobile quick-capture form · `core.actions` · Personal knowledge layer · Gmail structured extractors

**Phase 3 — Intelligence**
`mart_goal_pacing` · `mart_daily_features` · `mart_morning_context` · Morning brief · AI claim evidence · AI evaluation harness · Recommendation tracking

**Phase 4 — Action and Learning**
Action completion tracking · Outcome measurement · Scenario planning · Experiment registry · Notification policy engine · Feedback everywhere

**Phase 5 — Usability and Scale**
Search everything · Command palette · What Changed view · Personal changelog · Model routing · Cost accounting · Semantic search

---

### Unified Action System

Create `core.actions` — canonical place to manage what should happen next.

Schema: `action_id`, `created_at`, `due_at`, `domain`, `title`, `description`, `source`, `source_event_id`, `source_recommendation_id`, `priority`, `status`, `estimated_minutes`, `accepted_at`, `completed_at`, `outcome`, `privacy_level`

`source_event_id` and `source_recommendation_id` allow ONS to distinguish: action from AI recommendation · action from failed pipeline · action from goal-risk event · action created manually.

Statuses: `proposed` / `accepted` / `in_progress` / `completed` / `dismissed` / `expired`

Actions originate from: OpenClaw recommendations, goal pacing risk, calendar gaps, failed pipelines, stale data, career notes, family reminders, manual capture, system health checks.

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Create `core.actions` | Canonical action model across all domains |
| 🔵 | Link recommendations to actions | Accepted AI recommendations become trackable |
| 🔵 | Add action status workflow | Proposed → accepted → in progress → completed |
| 🔵 | Add Actions page (Next.js) | Filter by domain, priority, due date, source |
| 🔵 | Add action outcome tracking | Record whether the action helped |
| ⚪ | Todoist or Reminders integration | Optional external task sync |
| ⚪ | OpenClaw action creation | AI proposes actions but never silently executes |

---

### Capture Inbox

Many of the most meaningful life events are not available through APIs: career wins, feedback, family memories, injury notes, ideas, decisions, concert attendance.

Create `raw.capture_inbox` — universal holding area for manual input.

Schema: `capture_id`, `captured_at`, `raw_text`, `capture_source`, `suggested_domain`, `suggested_event_type`, `processed`, `linked_event_id`, `privacy_level`, `metadata_json`

Capture channels: mobile web form, iPhone Shortcut, email, Telegram bot, ntfy action, OpenClaw conversation, command palette, Home page quick-add.

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Create `raw.capture_inbox` | Universal holding area for manual input |
| 🔵 | Build mobile quick-capture form | Under 15 seconds to complete |
| 🔵 | Add AI classification | Suggest domain, event type, tags, privacy level |
| 🔵 | Add review queue | Confirm or edit before promotion to domain tables |
| 🔵 | Promote captures into domain tables | Career, family, health, finance, ideas |
| ⚪ | iPhone Shortcut | Dictated or typed notes directly to ONS |
| ⚪ | Email capture | Forward structured messages into inbox |
| ⚪ | Voice capture | Transcribe short voice notes |

---

### Gmail as a Structured Input Source

Narrow, sender-specific extractors only — not full email ingestion.

| Flow | Source | Destination |
|------|--------|-------------|
| Career praise email | Gmail | `raw.career_events` |
| Concert ticket confirmation | Gmail | Upcoming show + attendance candidate |
| Flight confirmation | Gmail | Travel event + calendar context |
| Investment confirmation | Gmail | Financial contribution record |
| Subscription receipt | Gmail | Recurring cost record |

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Define Gmail extraction allowlist | Approved senders, subjects, query patterns only |
| 🔵 | Concert ticket extractor | Show and attendance candidates |
| 🔵 | Travel confirmation extractor | Flight, hotel, dates, confirmation metadata |
| 🔵 | Career praise extractor | Positive feedback and impact evidence |
| 🔵 | Financial confirmation extractor | Contribution and recurring expense records |
| 🔵 | Subscription receipt extractor | Identify recurring services and costs |
| 🔵 | Store structured fields only | Never retain unnecessary email body content |
| ⚪ | OpenClaw email triage | Summarize only approved categories |

---

### Personal Knowledge Layer

ONS is strong at numerical analytics but needs structure for personal knowledge.

Tables: `core.entities`, `core.entity_relationships`, `core.notes`, `core.decisions`, `core.lessons`

Entity types: person, project, company, place, goal, event, book, artist, team, system, decision

Questions this enables: What did I decide about this last time? Which project problems keep recurring? Which interview stories best demonstrate leadership? Which recommendations have I repeatedly ignored?

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Create `core.entities` | Shared entity registry across domains |
| 🔵 | Create relationship model | Connect people, projects, events, decisions |
| 🔵 | Create decisions log | Decision, rationale, alternatives, outcome |
| 🔵 | Create lessons log | Reusable lessons from projects and experiments |
| 🔵 | Link notes to events and entities | Context persists beyond a single report |
| ⚪ | Knowledge graph visualization | Explore relationships between entities |
| ⚪ | Semantic retrieval | Search notes and decisions in natural language |

---

### Semantic Metrics Registry

Prevent metric-definition drift as API, UI, AI, and public site expand.

Create `metadata.metrics`: `metric_name`, `display_name`, `description`, `owner`, `source_model`, `calculation`, `grain`, `unit`, `privacy_level`, `freshness_requirement`, `status`

Ownership examples: `running_miles_ytd` → fitness · `weekly_meeting_hours` → calendar · `recommendation_acceptance_rate` → openclaw · `platform_cost_monthly` → operations

Example metrics: `running_miles_ytd`, `crossfit_classes_ytd`, `date_nights_ytd`, `goal_progress_pct`, `training_load`, `savings_rate`, `recommendation_acceptance_rate`

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Create `metadata.metrics` | Canonical metric definitions |
| 🔵 | Document grain and unit | Prevent ambiguous calculations |
| 🔵 | Assign privacy level | Private, household, or public |
| 🔵 | Assign freshness requirement | How stale a metric may become |
| 🔵 | Expose metric metadata through FastAPI | UI and AI can inspect definitions |
| 🔵 | Add metric validation tests | Confirm model outputs match registry |
| ⚪ | Metric lineage page | Show sources, models, and consumers |

---

### FastAPI and Next.js Data Contracts

```
FastAPI Pydantic models → OpenAPI schema → generated TypeScript client → Next.js
```

Benefits: fewer duplicated types, compile-time frontend validation, safer API changes, automatic client generation, breaking-change detection in CI.

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Add Pydantic response models | Explicit schema for every route |
| 🔵 | Generate OpenAPI schema artifact | Store or upload during CI |
| 🔵 | Generate TypeScript API client | Frontend uses generated types |
| 🔵 | Add schema snapshot testing | Detect unexpected API changes |
| 🔵 | Add breaking-change CI check | Fail when incompatible changes introduced |
**Breaking changes** (require version bump): removing a field · renaming a field · changing a field type · changing nullability · changing response grain · changing enum values without backward compatibility · removing an endpoint.

**Non-breaking changes**: adding an optional field · adding a new endpoint · adding a new enum value when clients tolerate unknown values · improving documentation · adding metadata that does not alter existing behavior.

| 🔵 | Version all API routes | Use `/api/v1/` |
| 🔵 | Add compatibility policy | Document what constitutes a breaking change |
| 🔵 | Add OpenAPI diff check | Fail CI when an unapproved breaking change occurs |
| ⚪ | Publish typed client package | Reusable client for Next.js, scripts, future apps |

---

### Application Observability

| Signal Category | What to Track |
|-----------------|---------------|
| Infrastructure | CPU, memory, disk, Tailscale state, backup age, external drive |
| Pipelines | Last attempted, last successful, duration, rows loaded, errors |
| Application | FastAPI latency/errors, Next.js failures, slow queries, DuckDB locks |
| AI | Generation success rate, latency, token usage, cost, recommendation acceptance |

Recommended stack: **Uptime Kuma** (service monitoring) + **Sentry** (FastAPI + Next.js errors) + `ops.pipeline_runs` + structured JSON logs.

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Deploy Uptime Kuma | Monitor FastAPI, Next.js, Plex, and local services |
| 🔵 | Add Sentry to FastAPI | Capture exceptions and performance data |
| 🔵 | Add Sentry to Next.js | Capture page and API-client failures |
| 🔵 | Standardize structured logs | JSON logs with run ID and service name |
| 🔵 | Create system health API endpoint | Expose infrastructure and service status |
| 🔵 | Create observability dashboard | Infrastructure, pipelines, app, and AI |
| 🔵 | Define retention policy | App logs 30d · pipeline runs indefinite · notifications 1yr · AI usage indefinite · traces 14d · system metrics 90d · security events 1yr · restore-test results indefinite |
| 🔵 | Create `config/retention.yaml` | Configurable retention thresholds per record type |
| ⚪ | OpenTelemetry traces | Follow requests across UI, API, database, AI |

---

### AI Evaluation Harness

OpenClaw output should be measured, not assumed to be useful.

Create `ai.evaluations`: accuracy, usefulness, specificity, actionability ratings, groundedness flag, stale-data flag, user feedback.

Golden evaluation questions: "How far behind am I on running?" · "What is my most neglected goal domain?" · "Should I train hard today?" · "What changed since last week?"

Evaluate when: prompts change, models change, data marts change, context construction changes.

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Create `ai.evaluations` | Store structured evaluation results |
| 🔵 | Create golden question set | Known questions with expected characteristics |
| 🔵 | Add groundedness check | Verify outputs reference available data |
| 🔵 | Add freshness check | Detect stale source usage |
| 🔵 | Add user feedback controls | Useful / wrong / obvious / acted on |
| 🔵 | Add prompt regression tests | Compare outputs across prompt versions |
| 🔵 | Track evaluation scores over time | Measure whether OpenClaw is improving |
| ⚪ | Automated LLM-as-judge evaluation | Use cautiously alongside human feedback |

---

### Scenario Planning

Create `main_marts.mart_goal_scenarios` — project outcomes without changing actual data.

Example questions: What happens if I run 10 miles/week? Can I still reach 160 CrossFit classes? What monthly contribution hits my savings target? Which goals become unrealistic if I miss two weeks?

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Create scenario calculation service | Project outcomes without mutating data |
| 🔵 | Add goal scenario UI | Adjust weekly pace, view projected completion |
| 🔵 | Add multi-goal tradeoff view | See which goals compete for time |
| 🔵 | Allow saved scenarios | Compare optimistic, expected, minimum plans |
| ⚪ | OpenClaw scenario generation | AI proposes realistic recovery scenarios |

---

### Daily Cross-Domain Feature Mart

One row per day combining all signals. Create `main_marts.mart_daily_features`.

Fields include: sleep, HRV, steps, running miles, CrossFit attendance, training load, soreness, energy, mood, focus, stress, meeting hours, weather, travel day, habit completion.

Enables: sleep → training performance · meeting load → mood · weather → running completion · CrossFit volume → running pace · concert attendance → next-day readiness.

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Create `mart_daily_features` | One-row-per-day analytical mart |
| 🔵 | Normalize missing data | Distinguish zero, missing, not applicable |
| 🔵 | Add correlation analysis | Directional insights, not causal claims |
| 🔵 | Add anomaly detection | Identify unusual days or combinations |
| 🔵 | Expose features to OpenClaw | Bounded context for pattern detection |
| ⚪ | Forecast selected outcomes | Only after sufficient historical data exists |

---

### Personal Experiments

Create `core.experiments` — test which interventions actually work.

Example experiments: morning run vs evening run · no meetings before 10am · phone-free evening · pre-planned vs spontaneous workout · alternate Daily 10 selection rules.

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Create experiment registry | Hypothesis, intervention, and metric |
| 🔵 | Add baseline comparison | Compare against pre-experiment period |
| 🔵 | Add experiment tracking UI | Active, complete, abandoned |
| 🔵 | Generate experiment summary | Outcome, confidence, limitations |
| 🔵 | Link outcomes to actions | Adopt interventions that work |
| ⚪ | OpenClaw experiment suggestions | Propose experiments based on recurring patterns |

---

### Notification Policy Engine

Create `ops.notification_rules` + `ops.notifications` — centralize all alert logic.

Rule fields: `event_type`, `severity`, `channel`, `quiet_hours_start/end`, `cooldown_minutes`, `deduplication_key`, `requires_action`, `enabled`

Example policies: required pipeline failure → immediate alert · source stale one day → morning summary · disk above 85% → immediate alert · goal slightly behind → weekly review only · CFB picks ready → Thursday notification.

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Create notification rule tables | Central policy for alerts |
| 🔵 | Add severity levels | Info, warning, error, critical |
| 🔵 | Add quiet hours | Prevent low-priority overnight alerts |
| 🔵 | Add deduplication | Prevent repeated alerts for same issue |
| 🔵 | Add cooldown periods | Reduce alert fatigue |
| 🔵 | Add acknowledgement tracking | `acknowledged_at`, `resolved_at`, `linked_action_id`, `resolution_notes` — distinguishes delivered from resolved |
| 🔵 | Add notification lifecycle statuses | pending → sent → acknowledged → action created → resolved / expired / failed |
| 🔵 | Create notification history page | Sent, suppressed, acknowledged, resolved |
| 🔵 | Wire sync and system alerts through policy engine | Remove ad hoc notification logic |

---

### Standard Record Metadata

All important operational, generated, imported, and user-created records should use a consistent metadata convention.

Recommended fields:

```
created_at             — when ONS created the record
updated_at             — most recent mutation
source_system          — original provider or capture method
source_record_id       — source identifier when available
source_timestamp       — when the event occurred in the source
ingested_at            — when ONS received the data
pipeline_run_id        — links record to ops.pipeline_runs
transformation_version — code or model version that produced it
privacy_level          — controls access and publishing
```

Applies to: `core.life_events` · `core.actions` · `raw.capture_inbox` · `raw.career_events` · `core.decisions` · `core.lessons` · `core.experiments` · `ai.claims` · `ai.recommendations` · `ai.generations` · `ai.feedback` · financial records · family memories · imported media records.

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Apply standard metadata to all core tables | created_at, updated_at, source_system, pipeline_run_id, privacy_level |
| 🔵 | Apply to all AI tables | ai.claims, ai.generations, ai.feedback, ai.evaluations |
| 🔵 | Apply to imported records | Strava, Hardcover, calendar, Letterboxd, KGLW |
| 🔵 | Add transformation_version tracking | Know which code version produced a record |

---

### Configuration as Data

```
config/
├── agent_permissions.yaml
├── ai_prompts.yaml
├── daily10.yaml
├── freshness.yaml
├── goal_scoring.yaml
├── goals.yaml
├── model_routing.yaml
├── notifications.yaml
├── privacy.yaml
├── publishing.yaml
├── retention.yaml
└── sources.yaml
```

Benefits: configuration changes are reviewable, rules are not hidden in scripts, behavior is portable, CI can validate configuration, OpenClaw can propose changes without editing application code.

| File | Purpose |
|------|---------|
| `agent_permissions.yaml` | Which OpenClaw actions are automatic or require approval |
| `ai_prompts.yaml` | Versioned prompts and output expectations |
| `daily10.yaml` | Spotify Daily 10 bucket and selection rules |
| `freshness.yaml` | Expected refresh cadence and stale thresholds by source |
| `goal_scoring.yaml` | Goal pacing, risk, and completion rules |
| `goals.yaml` | Declarative annual and long-term goals |
| `model_routing.yaml` | Model selection by task, privacy class, quality, and cost |
| `notifications.yaml` | Alert severity, channels, quiet hours, and cooldowns |
| `privacy.yaml` | Private, household, and public classification rules |
| `publishing.yaml` | Rules for public artifacts and website deployment |
| `retention.yaml` | How long each record type is retained |
| `sources.yaml` | Source configuration, enabled state, and ingestion cadence |

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Create central config directory | Canonical behavioral configuration |
| 🔵 | Move Daily 10 rules into YAML | Remove hardcoded selection logic |
| 🔵 | Move freshness thresholds into YAML | Per-source expected cadence |
| 🔵 | Move notification policy into YAML | Version-controlled alert behavior |
| 🔵 | Move privacy rules into YAML | Central publishing restrictions |
| 🔵 | Add config schema validation | Fail CI on invalid configuration |
| ⚪ | Configuration editor in UI | Safe forms for common settings |

---

### Disaster Recovery

*A backup that has never been restored is only a hypothesis.*

Target recovery flow: Fresh Mac → clone repo → restore secrets → install dependencies → restore DuckDB → register launchd → start FastAPI and Next.js → verify pipelines → verify backups.

Each restore test should record: `test_id`, `started_at`, `completed_at`, `backup_path`, `backup_timestamp`, `checksum_valid`, `restore_duration_minutes`, `database_opened`, `dbt_tests_passed`, `api_started`, `ui_started`, `status`, `error_message`, `notes`.

Files: `scripts/bootstrap_machine.sh` · `scripts/restore_duckdb.py` · `scripts/verify_backup.py` · `RUNBOOK.md`

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Add backup checksum verification | Detect corrupted backups |
| 🔵 | Add monthly automated restore test | Prove backup usability |
| 🔵 | Add encrypted off-machine backup | Protect against drive or machine loss |
| 🔵 | Create bootstrap script | Install and configure ONS on a new machine |
| 🔵 | Create restore script | Restore latest valid DuckDB backup |
| 🔵 | Document RPO and RTO | RPO: 24 hours · RTO: 4 hours |
| 🔵 | Measure restore duration | Confirm recovery meets the 4-hour target |
| 🔵 | Record restore-test results | Date, backup used, duration, outcome |
| 🔵 | Complete RUNBOOK.md | Recovery procedures and expected outputs |

---

### AI Model Routing

Don't use the most expensive model for every task.

| Task | Suggested model |
|------|----------------|
| Classification and tagging | Small or local model |
| Structured extraction | Small cloud model |
| Daily brief | Mid-tier (claude-sonnet-4-6) |
| Weekly review | Stronger reasoning (claude-opus-4-6) |
| Career writing | Strong writing model |
| Sensitive family content | Local model where practical |

Create `ai.model_routes` + `ai.model_usage` + `ai.model_costs`.

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Define AI task types | Classification, extraction, summary, reasoning, writing |
| 🔵 | Create routing configuration | Model selected by task and privacy class |
| 🔵 | Track model cost and latency | Per generation and task type |
| 🔵 | Add fallback behavior | Handle unavailable or failed providers |
| 🔵 | Evaluate small local models | Classification, tagging, deduplication |
| ⚪ | Automatic quality-based routing | Use evaluation results to change routing |

---

### Platform Cost and Usage Tracking

Create `ops.api_usage` + `main_marts.mart_platform_cost`.

Track: AI API tokens · GitHub Actions · MotherDuck · The Odds API · Google APIs · hosting · domains · notification services · paid data providers.

Questions: What does ONS cost per month? Which feature costs the most? What can be cached? What is the cost per useful AI recommendation?

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Create `ops.api_usage` | Track requests, tokens, estimated cost |
| 🔵 | Create cost mart | Daily and monthly cost by provider and domain |
| 🔵 | Add budget thresholds | Warn when projected monthly cost is high |
| 🔵 | Add cache effectiveness metrics | Measure avoided API calls |
| 🔵 | Add cost-per-feature view | Understand value relative to cost |
| ⚪ | Automated usage optimization | Recommend cheaper models or lower frequency |

---

### Search Everything

One search experience across: goals, life events, career wins, reports, family memories, concerts, books, movies, recommendations, actions, decisions, lessons, pipeline logs.

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Create unified search endpoint | Search across approved domain indexes |
| 🔵 | Add global search UI | Available from every page |
| 🔵 | Add filters | Domain, date, type, privacy level |
| 🔵 | Add result previews | Relevant text and linked entity |
| ⚪ | Semantic search | Embeddings for notes, reviews, memories, decisions |
| ⚪ | Hybrid search | Combine keyword and semantic ranking |

---

### Command Palette

Global keyboard-driven interface for common commands: run daily sync, refresh sources, generate weekly review, log a career win, add a family memory, record an injury note, check data freshness, trigger CFB report.

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Add command palette component | Global keyboard shortcut |
| 🔵 | Add navigation commands | Open pages and reports quickly |
| 🔵 | Add capture commands | Log events without leaving current page |
| 🔵 | Add safe operational commands | Trigger approved workflows |
| 🔵 | Add confirmation for destructive actions | Prevent accidental execution |
| ⚪ | Natural-language command routing | Map plain language to approved actions |

---

### What Changed View

Create `mart_changes_daily` + `mart_changes_weekly` — compare current state to previous period.

Questions: What changed since yesterday? Which goal newly became at risk? Which pipeline became stale? Which metric improved most? Which recommendation was completed?

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Create daily change detection mart | Compare current state to previous day |
| 🔵 | Create weekly change detection mart | Compare to previous week |
| 🔵 | Add Home page "What Changed" section | Prioritized changes only |
| 🔵 | Expose changes to morning brief | Focus AI on meaningful movement |
| ⚪ | Change severity scoring | Rank changes by impact and urgency |

---

### Personal Changelog

Generate `reports/changelog/YYYY-W##.md` + `reports/changelog/YYYY-MM.md`.

Categories: completed · started · learned · watched · read · trained · visited · built · decided · celebrated.

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Create changelog mart | Aggregate meaningful events by period |
| 🔵 | Generate weekly changelog | Structured, factual summary |
| 🔵 | Generate monthly narrative | Longer reflection with domain highlights |
| ⚪ | Annual personal report | Year-end narrative and visual summary |

---

### Data Lineage and Provenance

Add lineage and provenance metadata to important generated records.

Fields: `source_system`, `source_record_id`, `source_timestamp`, `ingested_at`, `pipeline_run_id`, `transformation_version`

Applies especially to: `core.life_events` · `core.actions` · `raw.capture_inbox` · `ai.claims` · financial records · career events · family memories.

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Add provenance fields to core tables | Source system, record ID, timestamp, pipeline run ID |
| 🔵 | Track transformation version | Know which model version produced a record |
| 🔵 | Expose lineage in UI | Show where a record came from and when |
| ⚪ | Full lineage graph | Trace from raw source to displayed metric |

---

### Evidence and Confidence for AI Claims

Every meaningful OpenClaw statement should expose its evidence.

Create `ai.claims`: `claim_text`, `source_model`, `source_record_ids`, `source_date`, `freshness_status`, `confidence`, `verified`.

Example: *"Running is at risk because actual mileage is 24 miles below expected pace."* — UI shows source model, source date, calculation, freshness, confidence.

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Create claim evidence model | Connect AI statements to source records |
| 🔵 | Show evidence in UI | Expandable source details |
| 🔵 | Show freshness status | Warn when evidence is stale |
| 🔵 | Add unsupported-claim detection | Flag claims without linked evidence |
| 🔵 | Include evidence in AI evaluation | Groundedness becomes measurable |

---

### Human Approval Boundaries

Document which OpenClaw capabilities may execute automatically. Governed by `config/agent_permissions.yaml`.

| Action | Execution policy |
|--------|-----------------|
| Read and summarize data | ✅ Automatic |
| Generate a report | ✅ Automatic |
| Propose an action | ✅ Automatic |
| Create a local draft action | ✅ Automatic |
| Classify a capture | ✅ Automatic |
| Create a draft email | ✅ Automatic |
| Send an email | 🔐 Explicit approval required |
| Modify a calendar event | 🔐 Explicit approval required |
| Create a financial record from uncertain data | 🔐 Explicit approval required |
| Publish content publicly | 🔐 Explicit approval required |
| Delete records | 🔐 Explicit approval required |
| Overwrite source data | 🔐 Explicit approval required |
| Change permissions or secrets | 🔐 Explicit approval required |

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Create `config/agent_permissions.yaml` | Canonical approval policy for all AI actions |
| 🔵 | Enforce permissions in OpenClaw | Check policy before executing any side effect |
| 🔵 | Surface pending approvals in UI | Actions waiting for human confirmation |
| 🔵 | Log all approval decisions | Who approved what and when |
| 🔵 | Add expiration to approvals | Prevent stale actions from being executed |
| ⚪ | Tier approvals by risk | Low, medium, high, and prohibited |

---

### Feedback Everywhere

Feedback options on every AI output: Useful · Not useful · Wrong · Already knew this · Acted on it · Remind me later · Do not show this again.

Create `ai.feedback`.

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Add feedback to recommendations | Capture usefulness and action |
| 🔵 | Add feedback to morning briefs | Rate overall brief quality |
| 🔵 | Add feedback to weekly reviews | Identify valuable sections |
| 🔵 | Track recurring negative feedback | Detect weak prompts or logic |
| 🔵 | Use feedback in evaluation reports | Measure product improvement |

---

### Additional APIs — Cross-Cutting Value

| API / Tool | Use Case |
|------------|----------|
| Todoist | Recommendation-to-action workflow |
| Apple Reminders | Native personal task integration |
| Google Tasks | Task creation linked to calendar context |
| Gmail API | Career praise, tickets, travel, receipts |
| Google Maps / Places | Family outings, venues, travel history |
| TMDB | Film and TV metadata for Plex + Letterboxd |
| MusicBrainz | Open artist, release, and recording metadata |
| Last.fm | Near-real-time listening history |
| Discogs | Record collection, wishlist, pressing metadata |
| Open-Meteo | Historical and forecast weather analytics |
| GitHub API | PRs, reviews, issues, releases, project impact |
| Sentry | FastAPI and Next.js error tracking |
| Uptime Kuma | Local service monitoring |
| RescueTime | Focus and application usage analytics |
| Google Photos export | Family memory timeline (strict privacy) |

---

### Recommended Immediate Priorities

The strongest next actions in sequence:

1. **Deploy FastAPI and Next.js** — validate the product layer that is already built
2. **Activate Mac mini runner and launchd jobs** — make existing automation operational
3. **Implement `ops.pipeline_runs`** — establish reliable freshness, status, and failure tracking
4. **Complete backup restore testing** — prove the system can recover before adding more complexity
5. **Add API contracts and generated TypeScript types** — stabilize the FastAPI / Next.js boundary
6. **Build `core.life_events`** — create the normalized event foundation
7. **Build `raw.capture_inbox`** — add low-friction capture for context APIs cannot provide
8. **Build `core.actions`** — close the loop from recommendation to execution
9. **Build `mart_goal_pacing`** — enable risk detection and corrective recommendations
10. **Build `mart_daily_features`** — enable cross-domain pattern analysis
11. **Activate the morning brief** — deliver the first complete OpenClaw vertical slice
12. **Add claims, evaluations, feedback, and permissions** — make AI output grounded, measurable, and safe

---

### Cross-Cutting Priority Summary

| Priority | Capability | Why It Matters |
|----------|-----------|----------------|
| P0 | Unified Action System | Closes the loop from insight to execution |
| P0 | Capture Inbox | Collects meaningful context APIs miss |
| P0 | Semantic Metrics Registry | Prevents metric-definition drift |
| P0 | API Contracts | Keeps FastAPI and Next.js synchronized |
| P0 | AI Evaluation Harness | Measures whether OpenClaw is actually useful |
| P0 | Disaster Recovery | ONS survives machine or drive loss |
| P1 | Daily Feature Mart | Enables cross-domain pattern analysis |
| P1 | Notification Policy Engine | Prevents noisy and duplicated alerts |
| P1 | Scenario Planning | Turns status into practical planning |
| P1 | Experiment Tracking | Tests which interventions actually work |
| P1 | Application Observability | Detects UI and API failures |
| P1 | Cost and Usage Tracking | Controls API and platform growth |
| P1 | Personal Knowledge Layer | Preserves decisions, lessons, context |
| P1 | Search Everything | Makes the growing platform discoverable |
| P1 | Command Palette | Reduces friction for common actions |
| P1 | What Changed View | Surfaces meaningful movement over static state |
| P1 | Evidence and Confidence | Makes AI claims traceable and trustworthy |
| P2 | Local Model Routing | Reduces cost, improves privacy |
| P2 | Personal Changelog | Durable weekly and monthly narratives |
| P2 | Semantic Search | Queries unstructured reports, notes, memories |
| P2 | Knowledge Graph View | Visualizes relationships across entities |
