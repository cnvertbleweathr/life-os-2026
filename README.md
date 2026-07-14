# Operating Narcisystem (ONS) 2026

ONS is a personal analytics platform that treats life as a system — observable, measurable, automatable, and continuously improvable. It ingests your entire existence, runs it through a data stack, and tells you whether you're actually getting shit done or just think you are.

---

## Architecture

```
Your Life → DLT Pipelines → DuckDB → dbt → FastAPI → Next.js
                                ↑                        ↑
                         Local Inputs              OpenClaw (Claude API)
                    (habits, SugarWOD CSV,      morning brief, picks analysis,
                       goals YAML)                 habit insights, weekly recap
```

The dashboard runs on FastAPI + Next.js (replaced Streamlit in June 2026). FastAPI is a thin read-only query layer over DuckDB/dbt marts; Next.js is the actual UI. OpenClaw is the AI intelligence layer that generates daily briefs, weekly reviews, and game analysis.

Full architecture diagrams, dbt lineage, and the daily sync sequence live in [`ARCHITECTURE.md`](./ARCHITECTURE.md).

---

## Repository Structure

```
ons-2026/
├── goals/
│   └── 2026.yaml                      # What you said you'd do. No judgment.
│
├── openclaw/                          # AI analytics layer
│   ├── config.py
│   ├── db.py                          # Read-only DuckDB connection (RBAC enforced)
│   ├── audit.py                       # Immutable execution log
│   ├── orchestrator.py                # run_openclaw_tier1()
│   ├── rbac/policy.py                 # Zero-trust read policy
│   └── analyzers/
│       ├── morning_brief.py           # Daily 3-4 sentence summary ✓ LIVE
│       ├── weekly_recap.py            # Sunday 400-word narrative ✓ LIVE
│       └── cfb_narratives.py          # Post-game analysis (active in-season)
│
├── pipelines/                         # DLT ingestion pipelines
│   ├── strava_pipeline.py
│   ├── hardcover_pipeline.py
│   ├── habits_pipeline.py
│   ├── cfbd_pipeline.py
│   ├── cfbd_extended_pipeline.py
│   ├── letterboxd_pipeline.py
│   └── kglw_pipeline.py
│
├── scripts/                           # Orchestration + auxiliary scripts
│   ├── daily_sync.py                  # ← The one command to rule them all
│   ├── backup_duckdb.py
│   ├── notify.py                      # ntfy.sh push notifications
│   ├── tz_utils.py                    # Denver-timezone-correct date helpers
│   ├── generate_picks.py
│   ├── generate_picks_report.py
│   ├── generate_postmortem.py
│   └── [20+ other utilities]
│
├── api/                               # FastAPI backend — read-only query layer
│   ├── main.py
│   ├── deps.py
│   └── routers/
│       ├── home.py                    # /api/home — digest, brief, calendar, WOD, daily10
│       ├── habits.py
│       ├── fitness.py
│       ├── reading.py
│       ├── goals.py
│       ├── music.py
│       ├── shows.py
│       ├── sports.py
│       ├── cfb.py
│       └── kglw.py
│
├── web/                               # Next.js frontend
│   ├── app/
│   │   ├── page.tsx                   # Home — displays OpenClaw morning brief
│   │   ├── habits/page.tsx
│   │   ├── fitness/page.tsx
│   │   ├── reading/page.tsx
│   │   ├── goals/page.tsx
│   │   ├── music/page.tsx
│   │   ├── shows/page.tsx
│   │   ├── sports/page.tsx
│   │   ├── cfb/page.tsx
│   │   ├── kglw/page.tsx
│   │   └── checkin/page.tsx
│   ├── components/
│   │   ├── nav/Sidebar.tsx
│   │   └── ui/{primitives,TeamLogo}.tsx
│   ├── lib/
│   │   ├── api.ts
│   │   └── cfb_team_ids.json
│   └── public/logos/                  # 260/263 CFB team logo PNGs
│
├── dbt/
│   ├── models/
│   │   ├── core/core__life_events.sql
│   │   ├── staging/
│   │   └── marts/
│   └── profiles/
│
├── data/
│   ├── warehouse/ons.duckdb           # DuckDB warehouse (gitignored)
│   ├── backups/duckdb/                # Nightly backups, 7-day retention
│   ├── daily/                         # Per-day sync logs + health.txt
│   ├── ai/generations.jsonl           # OpenClaw audit trail — every generation logged
│   ├── habits/habits_log.jsonl
│   ├── bets/todays_picks.json
│   └── [other domains]
│
├── reports/
│   ├── daily/                         # OpenClaw morning briefs (YYYY-MM-DD.md)
│   └── weekly/                        # OpenClaw weekly reviews (YYYY-Www.md)
│
├── tests/
│   ├── smoke_test.py                  # 18 checks — cfb/env/metrics/sync groups
│   └── fixtures/load_fixtures.py
│
├── .github/workflows/                 # ci.yml, ci-analytics.yml, picks-validation.yml,
│                                      # motherduck-sync.yml, mac-mini-refresh.yml
├── launchd/
│   ├── com.ons.daily-sync.plist       # 9am daily
│   └── com.ons.backup-duckdb.plist    # 2am nightly
└── secrets/
```

---

## Daily Workflow

Runs automatically at 9am via launchd (`com.ons.daily-sync.plist`). Backup at 2am. OpenClaw runs at 9:25am as Step 16 (after dbt, before backup).

```bash
source .venv/bin/activate
PYTHONPATH=/Users/kg/life-os-2026 python scripts/daily_sync.py
```

**Run the app:**
```bash
# Terminal 1 — API
uvicorn api.main:app --reload --port 8000

# Terminal 2 — UI
cd web && npm run dev
```

Open `http://localhost:3000`. FastAPI docs at `http://localhost:8000/docs`.

**Surgical strikes:**
```bash
python scripts/daily_sync.py --only strava hardcover habits
python scripts/daily_sync.py --only openclaw_generation
python scripts/daily_sync.py --skip spotify
```

**Important:** DuckDB only allows one read-write connection at a time. FastAPI opens read-only, so it doesn't block pipeline writes — but stop it before any `dbt run` and restart afterward.

---

## Setup

### Prerequisites
- Python 3.12+, [uv](https://github.com/astral-sh/uv)
- Node.js 18+ / npm

### Install
```bash
git clone https://github.com/cnvertbleweathr/life-os-2026.git
cd life-os-2026
uv sync
source .venv/bin/activate
cd web && npm install && cd ..
```

### Configure
```bash
cp .env.example .env
```

| Key | Source |
|---|---|
| `STRAVA_CLIENT_ID` / `STRAVA_CLIENT_SECRET` | [Strava API](https://www.strava.com/settings/api) |
| `HARDCOVER_TOKEN` | [Hardcover Settings](https://hardcover.app/account/api) |
| `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` | [Spotify Developer](https://developer.spotify.com/dashboard) |
| `ANTHROPIC_API_KEY` | [Anthropic](https://console.anthropic.com/) — **OpenClaw (morning brief, weekly review, picks analysis)** |
| `OPENAI_API_KEY` | [OpenAI](https://platform.openai.com/api-keys) — Daily 10 cover art |
| `NEWS_API_KEY` | [NewsAPI](https://newsapi.org) — optional |
| `TICKETMASTER_API_KEY` | [Ticketmaster Developer](https://developer.ticketmaster.com) |
| `CFBD_API_TOKEN` | [CFBD](https://collegefootballdata.com) |
| `NTFY_TOPIC` | [ntfy.sh](https://ntfy.sh) |
| `LETTERBOXD_USERNAME` | Your Letterboxd handle — public RSS |
| `KGLW_ATTENDED_SHOW_IDS` | Comma-separated show IDs from kglw.net (optional) |

---

## App Pages

| Page | What it shows |
|---|---|
| **Home** | OpenClaw morning brief, stat row, calendar, WOD, Daily 10, goal pacing |
| **Habits** | Today's checklist, current + longest streaks |
| **Fitness** | YTD/weekly running miles, pace, bar chart, recent runs |
| **Reading** | Books read, fiction/nonfiction split |
| **Goals** | All domains, pace status badges, progress bars |
| **Music** | Top artists, Daily 10 playlist, news |
| **Shows** | Upcoming Denver concerts, artist matching |
| **Sports** | Streams, AI-ranked top 5, news |
| **CFB Betting** | Validated model, sortable team table, weekly picks |
| **King Gizzard** | Upcoming shows, on-this-day, song catalog, jam chart |
| **Check-in** | 30-second daily energy/mood/focus/sleep/soreness/stress log |

---

## OpenClaw — AI Intelligence Layer

OpenClaw sits above the marts and generates daily insights. It runs at 9:25am as Step 16 in `daily_sync.py` (after dbt, before backup), uses Claude Sonnet 4.6 with prompt caching (~$0.80/month), and logs every execution.

**Live (Days 1-5, completed 2026-07-13):**
- Morning brief — displayed on Home page, stored in `raw.ai_life_briefs`
- Weekly recap — generated Sundays, stored in `raw.ai_life_briefs`
- CFB narratives — active in-season, stored in `raw.ai_cfb_narratives`

**Next (Tier 2):**
- CFB picks analysis — weekly game previews + signal breakdown + why each pick was made
- Habit insights — trend analysis, streak patterns, motivation signals

**Audit trail:**
```bash
cat data/ai/generations.jsonl | jq '.[-1]'
# → {timestamp, analyzer_name, tokens_input, tokens_output, cost_usd, status}
```

**RBAC:** Read-only access to 12 mart tables. Writes only to 5 `raw.ai_*` tables. Enforced in `openclaw/rbac/policy.py`.

---

## CFB Betting System

**Cross-season validated edges (2021–2025, walk-forward, no lookahead):**

```
107-32 · 77.0% win rate · +47.0% ROI · 5/5 seasons profitable
Favorites: 66-23 (74.2% cover, +41.6% ROI)
Underdogs: 37-8 (82.2% cover, +57.0% ROI)
```

Active signals: talent/recruiting, PPA gap > 0.15, success rate parity, conference tailwind, underdog bonus, home efficiency vs away talent, coach change.

Disabled (July 2026): spread range (anti-predictive), away efficiency beats talent (market prices correctly), returning production (padding without signal).

**Documentation:**
- 7-minute overview: [`docs/SYSTEM_EXPLAINER.md`](./docs/SYSTEM_EXPLAINER.md)
- Full deep dive: [`docs/SYSTEM_DEEP_DIVE.md`](./docs/SYSTEM_DEEP_DIVE.md)

---

## Data Sources

| Source | Method | What it tracks |
|---|---|---|
| Strava | DLT + OAuth | Running miles, pace, weekly volume |
| Hardcover | DLT + GraphQL | Books read, fiction vs nonfiction |
| Habits | Local JSONL | Meditation, pushups, reading pages |
| Google Calendar | OAuth API | Events, date nights |
| SugarWOD | CSV export | CrossFit classes, PRs |
| Spotify | JSON export + API | Streaming stats, Daily 10 |
| AEG / Ticketmaster | Public API | Denver shows |
| Letterboxd | Public RSS | Film diary, ratings |
| KGLW.net | Public API v2 | Shows, songs, venues, jam chart |
| streamed.pk | Public API | Live sports streams |
| CFBD | DLT + Bearer | CFB games, lines, SP+, PPA, weather |

---

## Design Principles

**Separation of concerns** — Intent (`goals/2026.yaml`), facts (`data/`), and logic (`scripts/`, `dbt/`) are explicitly separated.

**Automation over willpower** — Runs at 9am daily. Willpower is finite. Cron jobs are not.

**DuckDB as the hub** — All sources land in DuckDB. dbt builds clean marts. FastAPI queries read-only. No spaghetti.

**Verify, don't assume** — Every API integration has confirmed field names against live data. Guessing wrong once in production is expensive.

**AI as co-processor** — Used for bounded, testable tasks (brief, recap, picks analysis, cover art). Never for core data logic.
