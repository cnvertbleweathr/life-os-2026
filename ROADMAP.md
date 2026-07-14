# ONS Product Roadmap

Last updated: 2026-07-13

---

## What ONS Is

ONS is a local-first personal data platform, automation layer, and intelligence system. It collects real-world data, models progress, generates artifacts, and uses AI to reduce manual overhead.

The platform is intentionally designed around modern analytics stack principles: declarative goals, scripted ingestion, explicit raw/processed/metrics layers, idempotent daily syncs, append-oriented historical tracking, automated artifact generation, and agent-assisted enrichment.

---

## The Three Questions ONS Must Answer

> **What is happening?**
> **Why does it matter?**
> **What should I do next?**

The platform has matured past "collect more data." The next phase focuses on helping ONS notice patterns, explain what matters, surface risks, recommend useful next actions, and reduce cognitive overhead.

---

## Status Legend

- 🟢 **Done** — shipped and working
- 🟡 **In Progress** — partially built or needs wiring
- 🔵 **Planned** — scoped, not started
- ⚪ **Idea** — not yet scoped
- 🔴 **Blocked externally** — confirmed broken, not fixable on our side

---

## OpenClaw — AI Intelligence Layer [COMPLETED DAYS 1-5, 2026-07-13]

OpenClaw is the AI layer that sits above the data and answers all three questions. It is only possible because ONS built the data foundation to support it.

### What's Live (Days 1-5)

| Day | Component | Status | Notes |
|-----|-----------|--------|-------|
| 1 | RBAC + DuckDB layer + audit | 🟢 | Zero-trust read-only connection, 5 writable tables, immutable audit log |
| 2-3 | Morning Brief + Weekly Recap | 🟢 | Claude Sonnet 4.6, prompt caching, $0.80/month cost |
| 4 | Daily Sync integration | 🟢 | Non-blocking Step 16 in daily_sync.py, AFTER dbt, BEFORE backup |
| 5 | Dashboard live | 🟢 | Next.js Home page displays live morning brief, FastAPI endpoints working |

### Tier 1 Analyzers (Live)

| Analyzer | Cadence | Output | Status |
|----------|---------|--------|--------|
| Morning Brief | Daily (9:25am) | `raw.ai_life_briefs` | 🟢 On Home page, 3-4 sentence daily summary |
| Weekly Recap | Sundays | `raw.ai_life_briefs` | 🟢 400-word narrative (ready, not yet on dashboard) |
| CFB Narratives | As games complete | `raw.ai_cfb_narratives` | 🟡 Built, disabled (no live games until Aug 29) |

### Tier 2 Analyzers (Planned, Starting Now)

| Analyzer | Cadence | Purpose | Status |
|----------|---------|---------|--------|
| CFB Picks Analysis | Weekly (Thursdays) | Game previews, signal breakdown, "why this pick" | 🔵 Planned |
| Habit Insights | Bi-weekly | Trend analysis, streak patterns, motivation | 🔵 Planned |
| [More to come] | TBD | To be defined | ⚪ Idea |

**Tier 2 approach:** Start with CFB picks (leverages existing validated model) and habit insights (existing habit data rich enough). Additional analyzers added as use cases emerge and prove valuable. No internal pressure to fill every possible domain.

### Infrastructure (All Complete)

| Component | Status | Notes |
|-----------|--------|-------|
| Module structure | 🟢 | `openclaw/{config,db,audit,rbac,orchestrator,analyzers}/` |
| DuckDB tables | 🟢 | 5 writable `raw.ai_*` tables created |
| Read-only RBAC | 🟢 | 12 readable marts, zero-trust enforcement |
| Audit trail | 🟢 | Every generation logged to `data/ai/generations.jsonl` |
| FastAPI endpoints | 🟢 | `/api/home/brief/latest`, `/api/home/briefs` |
| Dashboard integration | 🟢 | Home page displays morning brief with markdown |
| Cost tracking | 🟢 | ~$0.80/month with 90% prompt-cache discount |

### Next Steps for Tier 2

1. **CFB Picks Analysis (Week 1 of 2026 season, ~Aug 29)**
   - Weekly Thursday report: why each pick was made
   - Game preview: teams, spreads, edge signals
   - Signal breakdown: which signals drove the score
   - Output: `raw.ai_cfb_picks_analysis` or extend `raw.ai_cfb_narratives`

2. **Habit Insights (Bi-weekly)**
   - Trend analysis: improving, stable, declining
   - Streak patterns: current streak, longest, recovery from lapse
   - Motivation: "you're at your longest streak in 6 months" 
   - Output: `raw.ai_habit_insights`

3. **More use cases (Later)**
   - Proposed by OpenClaw analysis or user request
   - Validated against real data before shipping
   - No internal pressure to fill the matrix

---

## Platform Milestones

| # | Milestone | Goal | Status |
|---|-----------|------|--------|
| 1 | **Stabilize Daily Operations** | Daily sync runs unattended with clear logs, health, backups | 🟢 |
| 2 | **Productize the Dashboard** | FastAPI + Next.js replacing Streamlit | 🟢 |
| 3 | **Activate OpenClaw** | AI layer answers all three questions | 🟢 Days 1-5 ✓ |
| 4 | **Expand Warehouse Discipline** | dbt tests, mart documentation, data contracts | 🔵 |
| 5 | **Snowflake/MotherDuck** | Mirror selected marts to cloud | 🔵 |

---

## P0 — Platform Stabilization

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | `run_if_exists` enforced | Missing path → skipped, not crash |
| 🟢 | Required step failure aborts run | Remaining steps skipped |
| 🟢 | Daily sync health summary | `health.txt` per run |
| 🟢 | DuckDB backup script | Timestamped copies, 7-day retention |
| 🟢 | DuckDB backup launchd | `com.ons.backup-duckdb.plist` at 2am |
| 🟢 | Daily sync launchd | `com.ons.daily-sync.plist` at 9am |
| 🟢 | Timezone hardening | `tz_utils.py` across codebase |
| 🟢 | Remove hardcoded 2026 | 11 files updated with `datetime.now().year` |
| 🟢 | Smoke tests | `tests/smoke_test.py` — 18/18 passing |
| 🟢 | GitHub Actions CI | 5 jobs: syntax, CFB, hardcode, schema, TypeScript |
| 🟢 | OpenClaw integrated | Non-blocking Step 16 in daily_sync.py |
| 🟡 | Token health checks | Detect expired auth before sync fails |
| 🔵 | Spotify OAuth non-interactive | Token refresh without browser |
| 🔵 | Mac Mini health dashboard | Disk, DuckDB size, dbt, backups, Tailscale |

---

## UI Rebuild — Next.js + FastAPI

### Architecture
```
Mac mini
├── FastAPI   api/              Python (port 8000)
└── Next.js   web/              TypeScript (port 3000)
Remote: Tailscale or Cloudflare Tunnel
Domain: capuchin.cyou
```

### Status

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | FastAPI layer — all 10 routers | Real data debugged, confirmed response shapes |
| 🟢 | All 11 Next.js pages | Home, Habits, Fitness, Reading, Goals, Music, Shows, Sports, CFB, KGLW, Check-in |
| 🟢 | CFB team logos | 260/263 downloaded |
| 🟢 | OpenClaw morning brief | Displayed on Home page |
| 🔵 | Tailscale setup | 15 min |
| 🔵 | capuchin.cyou DNS | Point to production app |
| 🔵 | Decommission Streamlit | After parity confirmed |
| 🔵 | OpenClaw weekly review page | Display Sunday narratives |

---

## CFB Betting — Sports Modeling Lab

### Validated Model (Walk-Forward, 2021-2025)

```
107-32 · 77.0% win rate · +47.0% ROI · 5/5 seasons profitable
Favorites: 66-23 (74.2% cover, +41.6% ROI)
Underdogs: 37-8 (82.2% cover, +57.0% ROI)
```

### Active Signals

| Signal | ΔROI removed | Status |
|--------|-------------|--------|
| Talent / recruiting | -14.4% | ✅ |
| PPA extreme gap | -14.1% | ✅ |
| Success rate parity | -16.0% | ✅ |
| Conference tailwind | +13.1% | ✅ |
| Underdog bonus | +12.1% | ✅ |
| Home efficiency vs away talent | +10.8% | ✅ |
| Coach change | -3.5% | ✅ |
| Neutral site filter | N/A | ✅ |

### Disabled Signals (July 2026 Audit)

| Signal | Reason | Status |
|--------|--------|--------|
| Spread range (3–17) | Anti-predictive, Spearman=-0.065 | ❌ |
| Away efficiency beats away talent | Market prices correctly (56.2% cover) | ❌ |
| Returning production | Padding without predictive value | ❌ |

### Roadmap

| Status | Item |
|--------|------|
| 🟢 | Walk-forward backtester v3 |
| 🟢 | Per-season ablation |
| 🟢 | Unified scorer |
| 🟢 | Weekly picks report |
| 🟢 | CFB postmortem + grading |
| 🟢 | Calibration audit suite |
| 🟢 | Quality-of-Win system (Phases A-D) |
| 🟡 | 2026 live monitoring | Week 8 re-evaluation pending |
| 🔵 | Line movement signal |
| 🔵 | Re-run ablation at 2026 Week 4 |

---

## Data Ingestion

| Source | Status | Notes |
|--------|--------|-------|
| Strava | 🟢 | Running, full history synced to 2019 |
| Hardcover | 🟢 | Books read, daily |
| Habits | 🟢 | JSONL local log |
| Google Calendar | 🟢 | Events, time allocation |
| SugarWOD | 🟢 | CSV import, CrossFit classes |
| Spotify | 🟢 | Streaming history, Daily 10, cover art |
| CFBD | 🟢 | CFB games, 2021-2025 + 2026 live |
| KGLW | 🟢 | 1104 shows, 1001 songs, 671 venues |
| YouTube (KGLW) | 🟢 | 167 videos, 61 matched to shows |
| AEG/Ticketmaster | 🟢 | Denver shows |
| Letterboxd | 🟡 | Dry-run confirmed, not yet in daily_sync |
| Setlist.fm | 🔵 | Full concert history (planned) |
| Apple Health | 🔵 | Sleep, HRV, steps, weight |
| Whoop/Garmin | 🔵 | Recovery, strain, sleep |

---

## Cross-Cutting Platform Capabilities

### Unified Action System (P0)

Create `core.actions` — canonical place to manage what should happen next.

| Status | Item |
|--------|------|
| 🔵 | Create `core.actions` with status workflow |
| 🔵 | Link recommendations to actions |
| 🔵 | Add Actions page (Next.js) |

### Capture Inbox (P0)

Create `raw.capture_inbox` — universal holding area for manual input.

| Status | Item |
|--------|------|
| 🔵 | Create `raw.capture_inbox` |
| 🔵 | Mobile quick-capture form |
| 🔵 | AI classification (suggest domain, event type) |

### Semantic Metrics Registry (P0)

Create `metadata.metrics` — prevent metric-definition drift.

| Status | Item |
|--------|------|
| 🔵 | Create `metadata.metrics` |
| 🔵 | Document grain, unit, privacy, freshness |
| 🔵 | Expose through FastAPI |

### Daily Feature Mart (P1)

Create `mart_daily_features` — one row per day combining all signals.

| Status | Item |
|--------|------|
| 🔵 | Create mart (sleep, HRV, steps, running, workouts, mood, meetings, weather) |
| 🔵 | Enable cross-domain correlation analysis |

### Notification Policy Engine (P1)

Create `ops.notification_rules` — centralize alert logic.

| Status | Item |
|--------|------|
| 🔵 | Create notification rule tables |
| 🔵 | Add severity, quiet hours, deduplication, cooldown |
| 🔵 | Wire sync and system alerts through policy engine |

### Application Observability (P1)

Monitor infrastructure, pipelines, FastAPI, Next.js, and AI operations.

| Status | Item |
|--------|------|
| 🔵 | Deploy Uptime Kuma |
| 🔵 | Add Sentry to FastAPI + Next.js |
| 🔵 | Create system health API endpoint |
| 🔵 | Create observability dashboard |

### AI Evaluation Harness (P1)

Create `ai.evaluations` — measure OpenClaw output quality.

| Status | Item |
|--------|------|
| 🔵 | Create evaluation tables |
| 🔵 | Create golden question set |
| 🔵 | Add groundedness + freshness checks |
| 🔵 | Track scores over time |

### Personal Knowledge Layer (P1)

Create `core.entities` + relationships — preserve decisions, lessons, context.

| Status | Item |
|--------|------|
| 🔵 | Create entity registry |
| 🔵 | Create decisions + lessons logs |
| 🔵 | Link notes to events + entities |

### FastAPI & Next.js Data Contracts (P1)

Generate TypeScript client from OpenAPI schema — prevent drift.

| Status | Item |
|--------|------|
| 🟡 | Add Pydantic response models to all routes |
| 🔵 | Generate TypeScript API client |
| 🔵 | Add schema snapshot testing in CI |

---

## Mandarin Study System (TBD Phase)

A daily Mandarin learning session integrated into ONS. Habit tracking + HSK-level pacing + SRS spaced-repetition engine.

| Status | Item |
|--------|------|
| ⚪ | SM-2 algorithm + card state |
| ⚪ | FastAPI session endpoint |
| ⚪ | Next.js flashcard UI |
| ⚪ | Streak + session summary |

---

## Artist of the Week (TBD Phase)

Weekly ritual: pick one artist, listen to their discography, rate on a structured template. Cross-check against Spotify listening data.

| Status | Item |
|--------|------|
| ⚪ | Seed `music.artist_queue` (wheel + similar artists) |
| ⚪ | Review entry form + rating template |
| ⚪ | History view + filtering by tag |

---

## Sports Betting Lab — NFL, NHL, NBA (Future)

Extend CFB model to other sports. Walk-forward backtesting, per-season ablation, unified scorer.

| Sport | Status |
|--------|--------|
| NFL | 🔵 Planned — rest, efficiency, QB, weather signals |
| NHL | 🔵 Planned — Corsi, Fenwick, PDO, goalie signals |
| NBA | 🔵 Planned — net rating, pace, rest, injury signals |

---

## GitHub Actions — Learning Roadmap

Using ONS as a real-world environment for CI/CD, analytics engineering, secrets management, and deployment automation. 18 phases structured from fundamentals to advanced.

| Phase | Name | Status |
|-------|------|--------|
| 1 | CI Fundamentals | 🟢 |
| 2 | Reproducible Analytics Testing | 🟢 |
| 3 | dbt Quality Gates | 🟡 |
| 4 | Dependency Automation | 🟢 |
| 5 | Security Automation | 🟡 |
| 6 | Python Compatibility Matrix | 🟢 |
| 7 | Workflow Artifacts | 🟢 |
| 8 | Mac Mini Self-Hosted Runner | 🔵 |
| 9+ | Advanced orchestration | 🔵 |

---

## Roadmap Scope Rule

New items only added when they satisfy at least one:

- Close a clear gap in the three core questions
- Reduce manual effort
- Improve trust, reliability, privacy, or recovery
- Enable an existing planned capability
- Provide a meaningful learning opportunity
- Produce a concrete user-facing outcome

New APIs are not added solely because they are available. Complete vertical slices are prioritized over additional conceptual expansion.

---

## Guiding Principle

**ONS should make the right action easier than the default action.**

The platform should quietly collect reliable data, preserve meaningful context, surface important changes, explain why they matter, recommend practical actions, and measure whether those actions helped.

Life OS should not become another obligation. It should help identify the most valuable next action — without making life feel like another job.
