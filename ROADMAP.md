# ONS Product Roadmap

Last updated: 2026-06-07

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

## Status Legend

- 🟢 **Done** — shipped and working
- 🟡 **In Progress** — partially built or needs wiring
- 🔵 **Planned** — scoped, not started
- ⚪ **Idea** — not yet scoped

---

## Platform Milestones

| # | Milestone | Goal |
|---|-----------|------|
| 1 | **Stabilize Daily Operations** | Daily sync runs unattended with clear logs, health summaries, backups, and non-interactive failure handling |
| 2 | **Productize the Dashboard** | Migrate from Streamlit to FastAPI + Next.js while preserving current functionality — accessible from anywhere |
| 3 | **Activate Insights** | Turn accumulated metrics into weekly reflection artifacts, insight cards, and domain-level summaries |
| 4 | **Expand Warehouse Discipline** | Add dbt tests, mart documentation, source freshness checks, data contracts, and better failure observability |
| 5 | **Snowflake Experimentation** | Replicate selected marts into Snowflake and evaluate warehouse-native patterns, Cortex, and dynamic tables |

---

## Priority Order

### P0 — Make daily sync reliable
1. Enforce `run_if_exists` in `daily_sync.py`
2. Fix required-step failure propagation
3. Add daily sync health summary
4. Add DuckDB nightly backup + restore test
5. Add token health checks (Spotify, Strava, Google, OpenAI)
6. Make Spotify/OpenAI failures non-fatal where appropriate

### P1 — Finish the insight loop
1. Wire insight export scripts into weekly sync
2. Generate weekly reflection summaries
3. Surface insights in dashboard
4. Track weekly deltas and anomalies
5. Add reflection archive

### P2 — Formalize Daily 10
1. Fix 5 + 15 bucket logic
2. Move bucket rules to config
3. Cache event-of-day metadata
4. Log playlist ID, event, image status, and track counts
5. Add Daily 10 history mart

### P3 — Product surface rebuild (Next.js + FastAPI)
1. Define API contracts for all 8 route modules
2. Build read-only FastAPI endpoints over DuckDB/dbt marts
3. Build Next.js Home page — establishes design system in code
4. Build CFB Betting page — benefits most from proper UI
5. Port remaining pages in order of daily use
6. Set up remote access (Tailscale or Cloudflare Tunnel)
7. Decommission Streamlit after parity confirmed

### P4 — Snowflake experimentation
1. Export selected marts to Snowflake
2. Prototype Snowflake-native ingestion
3. Evaluate Streamlit in Snowflake
4. Evaluate Cortex summaries
5. Document local-first vs cloud-native tradeoffs

---

## P0 — Platform Stabilization

| Status | Item | Why It Matters |
|--------|------|----------------|
| 🔵 | Enforce `run_if_exists` in `daily_sync.py` | Steps should skip cleanly when optional scripts are unavailable |
| 🔵 | Fix required-step failure propagation | Required failures should stop the run predictably |
| 🔵 | Add daily sync health summary | One clear artifact showing success, failure, skipped, and duration |
| 🔵 | Add non-interactive Spotify auth checks | Daily automation should not require browser auth |
| 🔵 | **DuckDB backup/restore workflow** | **Highest priority unaddressed infrastructure risk — single-file warehouse** |
| 🔵 | Standardize timezone handling | Use America/Denver for day semantics and UTC for system timestamps |
| 🔵 | Remove hardcoded 2026 assumptions | Prepare for 2027 rollover — 10+ locations affected |
| 🔵 | Add smoke tests for critical workflows | Daily sync, Spotify Daily 10, CFB picks, metrics scripts |

---

## UI Rebuild — Next.js + FastAPI

### Decision
Streamlit is being replaced. It is the wrong tool for a personal dashboard — rigid layout,
no real routing, full-page reruns on every interaction, no mobile support, and CSS hacks
required to suppress its own chrome. The rebuild targets a proper web app accessible from
anywhere.

### Architecture
```
Mac mini
├── FastAPI   api/              Python — DuckDB query layer
│   └── routers/
│       ├── home.py             /api/home
│       ├── fitness.py          /api/fitness
│       ├── music.py            /api/music
│       ├── habits.py           /api/habits
│       ├── reading.py          /api/reading
│       ├── goals.py            /api/goals
│       ├── shows.py            /api/shows
│       ├── sports.py           /api/sports
│       └── cfb.py              /api/cfb/picks, /api/cfb/backtest
└── Next.js   web/              TypeScript — UI layer
    └── app/
        ├── page.tsx            Home
        ├── habits/page.tsx
        ├── fitness/page.tsx
        ├── reading/page.tsx
        ├── goals/page.tsx
        ├── music/page.tsx
        ├── shows/page.tsx
        ├── sports/page.tsx
        └── cfb/page.tsx

Remote access: Tailscale or Cloudflare Tunnel (no port forwarding required)
Domain: capuchin.cyou (registered, unused — point to production app)
```

### Design System
- Dark sidebar (#1a2420) with ONS logo mark and forest green accent (#4a7c5f)
- White content area — flat, minimal, bento grid layout
- Space Grotesk font carried over from current theme
- Fully responsive — works on phone via Tailscale

### Roadmap

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | Design concept | Bento grid Home layout reviewed and approved |
| 🟢 | Streamlit pages identified for port | 9 pages × ~400 lines avg |
| 🔵 | FastAPI layer — all 8 route modules | Port DuckDB queries from Streamlit pages |
| 🔵 | Next.js scaffold — routing, layout, sidebar | App Router, Tailwind |
| 🔵 | Home page | Calendar, stat cards, Daily 10, WOD, picks strip |
| 🔵 | CFB Betting page | Edge matrix, team intel, matchup analysis, picks |
| 🔵 | Habits page | Today checklist, streaks, YTD heatmap |
| 🔵 | Fitness page | Running stats, lift progressions, WOD log |
| 🔵 | Music page | Daily 10 embed, streaming stats, news |
| 🔵 | Reading page | Currently reading, books read 2026 |
| 🔵 | Goals page | Progress bars, pace tracking, domain grouping |
| 🔵 | Shows page | Denver concerts, artist matching, venue map |
| 🔵 | Sports page | Streams, team news, Degenerates Corner |
| 🔵 | Remote access setup | Tailscale or Cloudflare Tunnel |
| 🔵 | capuchin.cyou DNS | Point to production app |
| 🔵 | Decommission Streamlit | Remove app/ after parity confirmed |

---

## CFB Betting — Sports Modeling Lab

The CFB betting layer is a controlled environment for signal engineering, walk-forward
validation, ablation analysis, calibration, and weekly reporting. It is the most
technically complete module in the platform.

### Validated Model Results (walk-forward, no lookahead bias)

```
318 bets · 224-94 · 70.4% win rate · +34.5% ROI · 4/4 seasons profitable
Tested: 2022-2025 (walk-forward tiers, one row per game, prior-season PPA only)
Weeks 1-4:   +39.5% ROI  (strongest window — prior-season PPA freshest)
Weeks 5-8:   +24.4% ROI
Weeks 9-12:  +35.7% ROI
Weeks 13+:   +37.0% ROI
```

### Validated Signal Stack

| Signal | ΔROI removed | Per-season | Status |
|--------|-------------|------------|--------|
| Success rate interaction | -16.0% | 4/4 | ✅ Active |
| Team tier penalties | -7.2% | 4/4 | ✅ Active |
| Spread range filter | -5.1% | 3/4 | ✅ Active |
| Coach change filter | -3.5% | 4/4 | ✅ Active |
| Conference filter | -1.7% | 3/4 | ✅ Active |
| Returning production | -1.4% | 4/4 | ✅ Active |
| Recruiting/talent | -14.4% aggregate | 4/4 | ✅ Active |
| SP+ alignment | 0.0% | 0/4 | ❌ Disabled |
| Defensive havoc | 0.0% | 0/4 | ❌ Disabled |
| Travel distance | — | display only | ℹ️ Display |
| Coach H2H | — | display only | ℹ️ Display |

### Key Architecture
- `scripts/backtest_walk_forward.py` — canonical `score_game()` function
- `scripts/generate_picks.py` — imports `score_game()` directly, zero divergence
- `scripts/backtest_ablation.py` — per-season signal ablation (drop one, measure ΔROI)
- `dbt/models/marts/mart_cfbd_recruiting_talent.sql` — 4-year weighted talent model
- `dbt/models/marts/mart_cfbd_travel_distance.sql` — haversine via cfbd.weather
- `dbt/models/marts/mart_cfbd_coach_matchups.sql` — H2H record (display only)
- `data/bets/todays_picks.json` — weekly output consumed by Sports page

### Season Workflow (August–January)
| Day | Script | Action |
|-----|--------|--------|
| Sunday | `track_lines.py` | Opening lines snapshot |
| Mon–Fri | `track_lines.py` | Daily movement snapshots |
| Wed/Thu | `track_news_signals.py` | Injury/weather signals for movers |
| Tue/Wed | `generate_picks.py` | Pick generation |
| Thursday | `generate_picks_report.py` | Markdown report → `data/bets/` |
| Saturday | `track_lines.py` | Closing lines |

### Known Issues
- **Model score calibration:** 70-79 bucket slightly outperforms 90-99 — not monotonic.
  Likely caused by signal interactions at high scores. Investigate before August.
- **6-signal bucket underperforms 4/5/7:** Specific combinations are double-counting
  the same underlying information. Combo analysis needed.

### Roadmap

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | 14-signal model built and empirically calibrated | All weights from historical validation |
| 🟢 | Walk-forward backtester v3 | Prior-season SP+, 2+ season tiers, one row/game |
| 🟢 | Per-season ablation test | Identifies consistent vs era-specific signals |
| 🟢 | `generate_picks.py` uses `score_game()` | Single scorer, no divergence from backtest |
| 🟢 | SP+ and havoc disabled | 0% ΔROI all 4 seasons — removed from scoring |
| 🟢 | Human-readable edge strings in pick output | Plain English signal labels |
| 🟢 | Weekly picks report (Thursday) | Markdown → `data/bets/picks_report_YYYY_WkNN.md` |
| 🟢 | Walk-forward tiers built at runtime | No lookahead bias in live picks |
| 🔵 | Model score calibration audit | 70-79 outperforms 90-99 — investigate signal stacking |
| 🔵 | Line movement signal (in-season) | `track_lines.py` → `mart_cfbd_line_movement` → `score_game()` |
| 🔵 | News signal integration | `track_news_signals.py` → confidence adjustment |
| 🔵 | 2026 live performance tracker | Weekly P&L vs model_score, rolling ROI chart |
| 🔵 | Re-run ablation at 2026 Week 4 | Recalibrate weights against real data |
| 🔵 | Push alert for qualifying bets | ntfy.sh — Thursday report notification |
| 🔵 | Game Scout — weekly matchup browser | August, when 2026 schedule available |
| 🔵 | Refresh team profiles at 2026 Week 4 | `cfb_build_team_profiles.py --min-games 8` |
| 🔵 | Postmortem reports | Weekly review of wins/losses and signal behavior |
| 🔵 | NFL betting pipeline | The Odds API — same dbt mart pattern |
| 🔵 | MLB betting pipeline | The Odds API + Statcast for advanced metrics |
| ⚪ | Closing line value (CLV) dataset | Build from `track_lines.py` snapshots over a season |
| ⚪ | Injury proxy via player usage drops | `cfbd.player_usage` — currently skipped |

---

## Goals Page — Known Deficiencies

The Goals page is the weakest page in the platform. These issues will be fixed in the
Next.js rebuild rather than patched in Streamlit.

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| Binary goals show `in_progress` | No separate display path for non-numeric goals | Distinct component for binary vs numeric |
| Finance goals show 0% | No data pipeline for actuals | Plaid integration or manual CSV |
| Habit goals show >100% | Target set as `1` (binary) vs cumulative actuals | Change targets in `2026.yaml` to annual totals |
| Raw snake_case labels | Goal keys displayed unformatted | Format labels — remove underscores, title case |
| No pace indicator | Not implemented | Add "where should I be today?" logic |
| No on-track / at-risk / behind color | Everything same color | Green ≥ pace, amber 10% behind, red >20% behind |

---

## Shows Page

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | Denver concerts — AEG + Ticketmaster | Daily, artist matching against Tewnidge/Deeds |
| 🔵 | Venue map | Denver map with show pins |
| 🔵 | Artist similarity radar | `show_radar.py` exists but dormant |
| 🔵 | Calendar integration | One-click add to calendar |
| 🔵 | Personal attendance log | Mark attended, rate shows |
| ⚪ | Setlist integration | setlist.fm API |
| ⚪ | Pre-show playlist | Auto-generate Spotify playlist before a show |

---

## Spotify Daily 10

### Current Behavior
- **Bucket A:** 5 random tracks from top 500 most-played songs in full history
- **Bucket B:** 15 never-played tracks by artists on Tewnidge playlist
- Decorated with AI-generated historical cover art and Wikimedia On This Day description
- Created idempotently — same date always produces same playlist

### Known Issue
Bucket B sometimes produces fewer than 15 tracks if Tewnidge search returns few
unheard results. The 5 + 15 split is the target, not consistently achieved.

| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Finalize 5 + 15 playlist logic | Ensure Bucket B always included in final URIs |
| 🔵 | Move bucket rules to config | Avoid hardcoded playlist behavior |
| 🔵 | Add audit fields | Track selected artists, source, event title, image status |
| 🔵 | Cache historical event by date | Prevent event drift on reruns |
| 🔵 | Improve event ranking | Prefer science/culture/exploration over tragedy/war |
| 🔵 | Add fallback behavior | If art generation fails, still create playlist |
| 🔵 | Add Daily 10 history mart | Track playlist ID, track count, event, image status |
| 🔵 | Add tests for bucket logic | Validate top-500 sample, unheard filter, Tewnidge exclusion |

---

## Data Ingestion

| Status | Source | Current State | Next Step |
|--------|--------|--------------|-----------|
| 🟢 | Spotify | Extended streaming history, Daily 10 | Stabilize 5+15 bucket logic |
| 🟢 | Google Calendar | Date night and calendar metrics | Add family/focus time categorization |
| 🟢 | Hardcover | Reading metrics integrated | Add reading velocity and streaks |
| 🟢 | SugarWOD | Fitness attendance and performance | Add movement/category classification |
| 🟢 | Strava | Running metrics integrated | Add pace, effort, training load trends |
| 🟢 | Pixela | Habit posting and metrics | Add streaks and recovery indicators |
| 🟢 | AEG/Ticketmaster | Denver show discovery | Add attendance and interest tracking |
| 🟢 | CFBD | CFB historical 2021-2025 | Weekly during season, annual offseason |
| 🟢 | WOD scraper | Park Hill CrossFit via Playwright | Daily |
| 🟡 | Local manual inputs | Some JSON/CSV workflows | Standardize local input schema |
| 🟡 | Insights pipeline | Built but dormant | Wire into weekly sync |
| 🔵 | Apple Health | Not started | Sleep, HRV, steps, weight, recovery |
| 🔵 | Letterboxd | Not started | RSS feed letterboxd.com/{user}/rss/ |
| 🔵 | Plaid | Not started | Financial actuals for savings/spending goals |
| 🔵 | The Odds API | Not started | NFL/MLB historical + live lines |
| ⚪ | Sleep tracking | Not started | Oura/Garmin/Whoop — API varies by device |
| ⚪ | Weather | Not started | OpenWeatherMap — Denver daily forecast |

---

## Modeling Layer

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | Goal-driven metrics | Goals declared separately from metrics logic |
| 🟢 | Daily history | Longitudinal tracking via history_daily.csv |
| 🟢 | dbt integration | DuckDB + dbt patterns established |
| 🟢 | CFB mart layer | line_accuracy, game_context, recruiting_talent, travel_distance, coach_matchups |
| 🔵 | Source freshness checks | Detect stale inputs before dashboards consume them |
| 🔵 | Data contracts for key marts | Expected columns, grain, ownership |
| 🔵 | dbt tests | `not_null`, `unique`, `accepted_values`, relationship tests |
| 🔵 | Mart documentation | Grain, source, refresh cadence, downstream usage |
| 🔵 | Metrics registry | Centralize metric definitions to avoid drift |

---

## Artifact Generation

| Status | Artifact | Current State | Next Step |
|--------|----------|--------------|-----------|
| 🟢 | Daily 10 playlist | Created in Spotify | Stabilize 5+15 bucket logic |
| 🟢 | Daily 10 cover art | Generated with OpenAI, uploaded to Spotify | Cache event and image metadata |
| 🟢 | Daily 10 description | Historical context from Wikimedia | Improve event ranking |
| 🟢 | Shows summary | AEG/Ticketmaster events modeled | Add interest/attendance tracking |
| 🟢 | CFB picks report | Weekly markdown → `data/bets/` | Add notification delivery, postmortems |
| 🟡 | Weekly reflection | Scripts exist, not wired | Wire into weekly sync |
| 🟡 | Insights JSON | Concept exists | Surface in dashboard |
| 🔵 | Monthly recap | Planned | Domain-by-domain retrospective |
| 🔵 | Year-in-review | Planned | Annual summary artifact in December |

---

## AI + Agent Layer

AI operates as a bounded co-processor. Deterministic logic stays in code; AI enriches,
summarizes, and generates creative artifacts.

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | Date-based playlist art | Working end-to-end |
| 🟢 | Playlist description generation | Working with length/safety constraints |
| 🔵 | Event metadata cache | Store selected event, source URL, prompt hash |
| 🔵 | Weekly insight generation | Use metrics outputs as bounded context |
| 🔵 | Insight cards | "What changed?" summaries |
| 🔵 | Natural-language querying | Ask questions over DuckDB/dbt marts |
| ⚪ | Agent-assisted roadmap updates | Summarize codebase changes into roadmap diffs |

---

## Infrastructure & Operations

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | Mac mini daily sync via launchd | 9am daily |
| 🟢 | GitHub repo (cnvertbleweathr/life-os-2026) | Branch: main |
| 🟡 | Step-level logs | Logs exist under daily output directories |
| 🟡 | Best-effort failures | Some scripts degrade gracefully |
| 🔵 | **DuckDB nightly backup** | **Highest priority unaddressed infrastructure risk** |
| 🔵 | Restore test | Prove backups are usable |
| 🔵 | Failure notifications | ntfy.sh, email, or Slack |
| 🔵 | Token health checks | Spotify, Google, Strava, OpenAI |
| 🔵 | Source freshness dashboard | Show stale inputs before metrics drift |
| 🔵 | Runbook docs | How to recover failed daily syncs |
| 🔵 | Spotify headless auth | Non-interactive token refresh for launchd |
| 🔵 | Launchd hardening | Scheduled jobs run without terminal interaction |
| 🔵 | Dependency audit | Remove dead scripts and unused packages |
| ⚪ | Push notifications (ntfy.sh) | Morning digest — WOD, games today, calendar alerts |

---

## Technical Debt

| Priority | Issue | Impact | Resolution |
|----------|-------|--------|------------|
| P0 | DuckDB backup not finalized | Local warehouse has single-file risk | Nightly backup + restore test |
| P0 | Daily sync failure handling | A failed required step may not stop correctly | Enforce required-step semantics |
| P0 | Spotify OAuth may require browser auth | Breaks unattended automation | Token health check + fail-gracefully mode |
| P1 | Hardcoded 2026 values (10+ locations) | Year rollover fragility | Central year config + dynamic filters |
| P1 | Daily 10 bucket rules in script | Harder to evolve playlist logic | Move buckets into config |
| P1 | Some artifacts are overwritten | Loss of historical audit detail | Append history with date/playlist metadata |
| P1 | Streamlit UX limits | Mobile and routing constraints | Migrate to FastAPI + Next.js |
| P1 | CFB model score not monotonic | 70-79 outperforms 90-99 | Signal stacking audit before August |
| P2 | Mixed old/new pipeline patterns | Maintenance drift | Consolidate toward ingestion → dbt → marts |
| P2 | Limited test coverage | Changes break workflows silently | Smoke tests + lightweight unit tests |

---

## Snowflake-Native Evolution

ONS runs local-first on DuckDB. The architecture intentionally mirrors warehouse-native
patterns and can be migrated or replicated into Snowflake. This is a future direction,
not a current dependency.

| Status | Item | Notes |
|--------|------|-------|
| ⚪ | Mirror selected marts to Snowflake | Preserve local-first while enabling cloud analytics |
| ⚪ | External stage experiment | Land CSV/JSON artifacts into object storage |
| ⚪ | Snowpipe prototype | Evaluate event-driven ingestion |
| ⚪ | Dynamic tables | Replace some scheduled transformations |
| ⚪ | Streamlit in Snowflake | Compare with local dashboard |
| ⚪ | Cortex summaries | Generate weekly insights from governed metrics |
| ⚪ | Cost-aware warehouse sizing | Treat personal analytics as a mini FinOps lab |
| ⚪ | Governance experiment | Naming, lineage, access, and retention conventions |

---

## Testing Roadmap

| Status | Test Area | Purpose |
|--------|-----------|---------|
| 🔵 | Daily sync smoke test | Verify orchestrator completes and writes expected artifacts |
| 🔵 | Spotify Daily 10 test | Validate final track count and bucket composition |
| 🔵 | Daily 10 decorator test | Validate fallback when OpenAI or Spotify fails |
| 🔵 | Metrics schema test | Ensure output CSVs have required columns |
| 🔵 | dbt tests | Validate mart quality |
| 🔵 | Token health tests | Detect auth failures before scheduled runs |
| 🔵 | Source freshness tests | Detect stale integrations |
| 🔵 | CFB model regression test | Verify `score_game()` output unchanged after edits |

---

## Documentation Roadmap

| Status | Document | Purpose |
|--------|----------|---------|
| 🟢 | README | Public-facing project overview |
| 🟡 | ROADMAP | Product and platform direction |
| 🔵 | RUNBOOK | Operational recovery and troubleshooting |
| 🔵 | DATA_DICTIONARY | Metric and table documentation |
| 🔵 | ARCHITECTURE | System design and data flow |
| 🔵 | API_CONTRACTS | FastAPI endpoint contracts |
| 🔵 | MODELING_NOTES | dbt conventions and mart definitions |
| 🔵 | DECISIONS | Lightweight ADR-style technical decisions |

---

## Definition of Done

A roadmap item is complete when:

- It is implemented in code
- It is runnable from a documented command
- It writes an auditable artifact or updates a modeled table
- It fails safely without corrupting state
- It is reflected in README, ROADMAP, or RUNBOOK when relevant
- It can be re-run without side effects

---

## Guiding Principle

ONS should make the right action easier than the default action.

The platform exists to reduce friction between intention and execution by combining data
engineering, automation, analytics, AI-assisted enrichment, and personal reflection.

The goal is not to track everything. The goal is to create a system where the most
important things become visible, measurable, and easier to act on.
