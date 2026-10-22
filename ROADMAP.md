# ONS Product Roadmap

Last updated: 2026-10-21

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

## Agentic Layer — Replaces OpenClaw [NEW TRACK, 2026-10-11]

OpenClaw is being retired. Its analyzers were single-shot prompts: pull a mart, send one prompt, store the text. With no tools, no state and no way to check its own work, the output stayed generic and the Tier 2 analyzers never shipped. It also had no evals, so "did it work?" was answered by feel.

The replacement is a set of **LangGraph agents**: tool-calling, stateful, able to query, check and retry. Each agent has one narrow job and an eval suite before it ships.

### What carries over from OpenClaw

| Keep | Why |
|------|-----|
| `openclaw/rbac/policy.py` → read-only mart access | Becomes the permission layer for agent tools |
| `openclaw/db.py` → read-only DuckDB connection | Agents never get a writer |
| `openclaw/audit.py` + `data/ai/generations.jsonl` | Every agent run logged with tokens + cost |
| `raw.ai_*` output tables | Agent outputs land in the same place |

Retired: `openclaw/analyzers/*`, `openclaw/orchestrator.py`, the `openclaw_generation` sync step (once each replacement is live).

### Learning Path (deeplearning.ai)

| # | Course | Length | Why | Status |
|---|--------|--------|-----|--------|
| 1 | Agentic AI (Andrew Ng) | 8.2h | Design patterns: reflection, planning, tool use, multi-agent | 🟡 20% |
| 2 | AI Agents in LangGraph | 1.5h | Core build skill: stateful graphs + tool-calling nodes | 🔵 |
| 3 | Evaluating AI Agents | 2.5h | Moved earlier: evals gate every agent before it ships | 🔵 |
| 4 | Multi AI Agent Systems with crewAI | 3h | **Optional.** LangGraph covers supervisor/sub-agent patterns; only if a real multi-agent need appears | ⚪ |

Note: the LangGraph course predates LangGraph 1.x — port examples to the current API rather than pinning old versions.

### Phases

| Phase | Deliverable | Depends on | Status |
|-------|-------------|------------|--------|
| A0 | Retire OpenClaw analyzers; extract RBAC/db/audit into `agents/core/` | — | 🔵 |
| A1 | **Ask ONS** — natural-language Q&A over DuckDB (inspect schema → write SQL → run read-only → check → retry) | Courses 1–2 | 🔵 |
| A2 | **Eval harness** — golden question set, SQL correctness, groundedness, cost/latency per run, scores tracked over time in `ai.evaluations` | Course 3, A1 | 🔵 |
| A3 | **CFB weekly agent** — reads live picks, live strength, line movement, news signals; writes the Thursday "why this pick" brief; graded against real results | A2 | 🔵 |
| A4 | **Morning brief v2** — rebuilt as an agent using A1's tools; replaces the OpenClaw brief on Home | A2 | 🔵 |
| A5 | Habit/goal coach — trends, streak recovery, pacing risk → proposes items for `core.actions` | A2, Unified Action System | ⚪ |
| A6 | Multi-agent supervisor (only if A1–A5 show a need) | Course 4 (optional) | ⚪ |

### Agent Rules

- **Agents explain and orchestrate; they don't decide.** CFB picks stay in the deterministic scorer. Agents never change model rules or bet logic.
- **Read-only by default.** Tools query marts through the RBAC layer; writes only to `raw.ai_*`.
- **No eval, no ship.** Every agent has a golden set and a pass bar before it goes into `daily_sync.py` or the UI.
- **Bounded runs.** Max tool calls and a cost ceiling per run; failures are non-blocking for the sync.
- **One job per agent.** Vague mandates ("summarize my life") are what sank OpenClaw.

---

## Platform Milestones

| # | Milestone | Goal | Status |
|---|-----------|------|--------|
| 1 | **Stabilize Daily Operations** | Daily sync runs unattended with clear logs, health, backups | 🟢 |
| 2 | **Productize the Dashboard** | FastAPI + Next.js replacing Streamlit | 🟢 |
| 3 | **Agentic Layer** | LangGraph agents answer the three questions, with evals | 🔵 Replaces OpenClaw |
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
| 🟢 | FastAPI + Next.js launchd | `com.ons.fastapi.plist` + `com.ons.nextjs.plist`; FastAPI auto-unloaded/reloaded by daily_sync |
| 🟢 | DuckDB write-lock management | daily_sync unloads FastAPI before pipelines, reloads after |
| 🟢 | Timezone hardening | `tz_utils.py` across codebase |
| 🟢 | Remove hardcoded 2026 | 11 files updated with `datetime.now().year` |
| 🟢 | Smoke tests | `tests/smoke_test.py` — 18/18 passing |
| 🟢 | GitHub Actions CI | 5 jobs: syntax, CFB, hardcode, schema, TypeScript |
| 🟢 | OpenClaw integrated | Non-blocking sync step — to be retired (see Agentic Layer A0) |
| 🟡 | Token health checks | Detect expired auth before sync fails |
| 🔵 | Data freshness checks | Alert when a source stops advancing (e.g. latest `cfbd.games` week with scores lags the calendar). 2026 CFB scores sat at Week 4 for three weeks without anything noticing |
| 🟡 | `track_news_signals` step | SQL references columns not yet in schema — non-blocking, skipped |
| 🔵 | Spotify OAuth non-interactive | Token refresh without browser |
| 🔵 | Mac Mini health dashboard | Disk, DuckDB size, dbt, backups, Tailscale |

---

## UI Rebuild — Next.js + FastAPI

### Architecture
```
Mac mini
├── FastAPI   api/              Python (port 8000)
└── Next.js   web/              TypeScript (port 3000)
Remote: Cloudflare Tunnel
Domain: narcisystem.com (narcisystem.com → :3000, api.narcisystem.com → :8000)
```

### Status

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | FastAPI layer — all 10 routers | Real data debugged, confirmed response shapes |
| 🟢 | All 11 Next.js pages | Home, Habits, Fitness, Reading, Goals, Music, Shows, Sports, CFB, KGLW, Check-in |
| 🟢 | CFB team logos | 260/263 downloaded |
| 🟢 | OpenClaw morning brief | On Home page until Agentic Layer A4 replaces it |
| 🟢 | Cloudflare Tunnel | narcisystem.com live |
| 🟢 | narcisystem.com DNS | Live — Cloudflare Tunnel routing |
| 🟢 | Decommission Streamlit | Done — Next.js is the UI |

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
| 🟡 | 2026 live monitoring | Live strength, grading loop, full slate UI shipped; season-trend Teams view + week picker shipped 2026-10-17; Week 8 re-evaluation pending |
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
| CFBD | 🟢 | CFB games, 2021-2025 + 2026 live. `cfbd_pipeline` added to daily_sync 2026-10-17 — 2026 scores had stalled after Week 4 because only the PPA pipeline was scheduled |
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

### AI Evaluation Harness

Moved into the Agentic Layer as Phase A2.

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
