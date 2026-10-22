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
                                                 → being replaced by LangGraph agents
```

The dashboard runs on FastAPI + Next.js (replaced Streamlit in June 2026). FastAPI is a thin read-only query layer over DuckDB/dbt marts; Next.js is the actual UI. OpenClaw is the current AI layer (daily briefs, weekly reviews, game analysis); it is being retired in favor of LangGraph agents — see [ROADMAP › Agentic Layer](./ROADMAP.md#agentic-layer--replaces-openclaw-new-track-2026-10-11).

Live at **[narcisystem.com](https://narcisystem.com)** via Cloudflare Tunnel from the Mac mini (`narcisystem.com` → Next.js :3000, `api.narcisystem.com` → FastAPI :8000).

The CFB betting system is documented in [`docs/SYSTEM_EXPLAINER.md`](./docs/SYSTEM_EXPLAINER.md) and [`docs/SYSTEM_DEEP_DIVE.md`](./docs/SYSTEM_DEEP_DIVE.md); deployment notes live in [`DEPLOYMENT_NOTES.md`](./DEPLOYMENT_NOTES.md).

---

## Repository Structure

```
life-os-2026/
├── goals/
│   └── 2026.yaml                      # What you said you'd do. No judgment.
│
├── openclaw/                          # AI analytics layer
│   ├── config.py
│   ├── db.py                          # DuckDB connection (RBAC enforced)
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
│   ├── cfbd_extended_pipeline.py      # Per-game PPA (current season), recruiting, etc.
│   ├── live_picks_pipeline.py         # Graded picks → cfbd.live_picks
│   ├── letterboxd_pipeline.py
│   ├── kglw_pipeline.py
│   └── kglw_youtube_pipeline.py
│
├── scripts/                           # Orchestration + auxiliary scripts
│   ├── daily_sync.py                  # ← The one command to rule them all
│   ├── backup_duckdb.py
│   ├── notify.py                      # ntfy.sh push notifications
│   ├── tz_utils.py                    # Denver-timezone-correct date helpers
│   ├── generate_picks.py              # Weekly picks (Mon–Wed)
│   ├── generate_picks_report.py       # Thursday briefing
│   ├── grade_picks.py                 # Grades results (Mon + Thu–Sun)
│   ├── generate_postmortem.py
│   ├── kglw_video_qa.py               # KGLW freshness + unmatched-upload report
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
│   │   ├── music/page.tsx             # incl. Denver shows (merged in Oct 2026)
│   │   ├── shows/page.tsx             # redirects to /music
│   │   ├── sports/page.tsx
│   │   ├── cfb/page.tsx               # This Week · Matchup Lab · Teams
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
│   │   ├── staging/
│   │   └── marts/                     # incl. core__life_events, mart_cfb_live_strength,
│   │                                  #      mart_live_picks, mart_goal_pacing,
│   │                                  #      mart_kglw_youtube_matches, mart_kglw_music_videos
│   └── profiles.yml                   # profile: ons → data/warehouse/ons.duckdb
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
├── tests/
│   ├── smoke_test.py                  # 18 checks — cfb/env/metrics/sync groups
│   └── fixtures/load_fixtures.py
│
├── .github/workflows/                 # ci.yml, picks-validation.yml
├── launchd/
│   ├── com.ons.daily-sync.plist       # 9am daily sync
│   ├── com.ons.backup-duckdb.plist    # 2am nightly backup
│   ├── com.ons.fastapi.plist          # FastAPI (port 8000) — managed by daily_sync
│   └── com.ons.nextjs.plist           # Next.js (port 3000)
└── secrets/
```

---

## Daily Workflow

Runs automatically at 9am via launchd (`com.ons.daily-sync.plist`); a separate nightly backup runs at 2am (`com.ons.backup-duckdb.plist`). The sync runs 32 steps in order. Some steps only run on certain days:

| Stage | Steps | When |
|---|---|---|
| Life data | strava, hardcover, habits, calendar, shows, spotify, Daily 10, streams, WOD | Daily (calendar export Mon/Thu) |
| CFB lines + news | `track_lines`, `track_news_signals` | Daily · Wed/Thu |
| CFB in-season | `cfbd_pipeline --skip-advanced` (games + final scores, lines, SP+) → `cfbd_extended_pipeline` (per-game PPA) → `mart_cfb_live_strength` → `grade_picks` → `live_picks_pipeline` → `mart_live_picks` | Mon + Thu–Sun |
| CFB picks | `generate_picks` · `generate_picks_report` | Mon–Wed · Thu |
| King Gizzard | `kglw` (kglw.net catalog, `--shows-only`), `kglw_youtube` (channel uploads + music-videos playlist) | Daily, before dbt |
| Goals + transform | `sync_playlist_artists`, `sync_goal_progress`, `dbt`, `load_goals`, `load_goal_progress` | Daily |
| AI + backup | `openclaw_generation`, `backup_duckdb` | Daily, last |

```bash
source .venv/bin/activate
PYTHONPATH=/Users/kg/life-os-2026 python scripts/daily_sync.py
```

**Run the app:** in normal operation both run under launchd (`com.ons.fastapi`, `com.ons.nextjs`) and are reachable at [narcisystem.com](https://narcisystem.com). Restart either with `launchctl kickstart -k gui/$(id -u)/com.ons.fastapi` (or `com.ons.nextjs`; rebuild with `cd web && npm run build` first). For local development:
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

**Important:** DuckDB only allows one read-write connection at a time. `daily_sync.py` handles this automatically: it unloads FastAPI via `launchctl unload` at startup (before any imports), runs all pipeline steps, then reloads FastAPI when done. If you run a pipeline or `dbt run` by hand, unload FastAPI first.

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
| `ANTHROPIC_API_KEY` | [Anthropic](https://console.anthropic.com/) — OpenClaw now; agentic layer next |
| `OPENAI_API_KEY` | [OpenAI](https://platform.openai.com/api-keys) — Daily 10 cover art |
| `NEWS_API_KEY` | [NewsAPI](https://newsapi.org) — optional |
| `TICKETMASTER_API_KEY` | [Ticketmaster Developer](https://developer.ticketmaster.com) |
| `CFBD_API_TOKEN` | [CFBD](https://collegefootballdata.com) |
| `NTFY_TOPIC` | [ntfy.sh](https://ntfy.sh) |
| `LETTERBOXD_USERNAME` | Your Letterboxd handle — public RSS |
| `LASTFM_API_KEY` | [Last.fm](https://www.last.fm/api/account/create) — Artist of the Day bios |
| `AUDIODB_API_KEY` | [TheAudioDB](https://www.theaudiodb.com/api_guide.php) — optional, premium key only |
| `YOUTUBE_API_KEY` | [YouTube Data API v3](https://console.cloud.google.com/apis/library/youtube.googleapis.com) — KGLW live recordings + music videos |
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
| **Music** | Year listening stats, Daily 10 playlist, Artist of the Day (from Tewnidge), upcoming Denver shows with artist matching and Google Calendar links (`/shows` redirects here) |
| **Sports** | Streams, AI-ranked top 5, news |
| **CFB Betting** | **This Week:** week picker for any 2026 week, official picks + watch list with WIN/LOSS and final scores once graded, weekly record, drill-down showing both teams' season-to-date trends going into that week · **Matchup Lab:** head-to-head model run · **Teams:** sortable table of Off/Def percentile, Off/Def/Net trend and points for/against; team profile with trend chart and game log |
| **King Gizzard** | **Shows:** live shows and music videos in one list (All · Upcoming · Music Videos · Watchable), with embedded YouTube recordings and official videos · **Songs:** song catalog |
| **Check-in** | 30-second daily energy/mood/focus/sleep/soreness/stress log |

---

## OpenClaw — AI Intelligence Layer

> **Being retired.** OpenClaw stays live until each analyzer has an agent replacement with an eval suite. See [ROADMAP › Agentic Layer](./ROADMAP.md#agentic-layer--replaces-openclaw-new-track-2026-10-11).

OpenClaw sits above the marts and generates daily insights. It runs as the `openclaw_generation` step near the end of `daily_sync.py` (after dbt, before backup), uses Claude Sonnet 4.6 with prompt caching (~$0.80/month), and logs every execution.

**Live (Days 1-5, completed 2026-07-13):**
- Morning brief — displayed on Home page, stored in `raw.ai_life_briefs`
- Weekly recap — generated Sundays, stored in `raw.ai_life_briefs`
- CFB narratives — active in-season, stored in `raw.ai_cfb_narratives`

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

**In-season tracking (2026):**
- **Live strength:** `mart_cfb_live_strength` scores each team's 2026 per-game PPA against its prior-season baseline (z-scored), plus a market residual, so ratings drift with real performance instead of sitting on 2025 numbers. Built from the games table, so unplayed games keep their schedule rows.
- **Grading loop:** `grade_picks` → `live_picks_pipeline` → `mart_live_picks` keeps the record and header stats current through the week.
- **Week anchoring:** `current_cfb_week` anchors on the last Saturday of August, so Week 1 runs through the following Friday.
- **Season trends:** `/api/cfb/team-trends` joins `cfbd.ppa_games` (PPA per play) to `cfbd.games` (scores). Trend = last 3 games minus first 3, signed so positive always means improving; defensive PPA is *allowed*, so lower is better. Percentiles are FBS-wide on season-average PPA. `through_week` limits it to games already played, so past weeks show no lookahead.
- **API:** `/api/cfb/slate` (weekly ranked slate), `/api/cfb/weeks` (archived weeks for the picker), `/api/cfb/team-trends`, `/api/cfb/strength` and `/api/cfb/strength/summary` (live strength), `/api/cfb/schedule` (FBS-only, with final scores), `/api/cfb/live-tracker`, `/api/cfb/matchup-lab`.

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
| KGLW.net | Public API v2 | Shows (incl. announced dates), songs, venues, jam chart |
| YouTube (KGLW channel) | Data API v3 | Live recordings matched to shows; official music videos from the band's music-videos playlist |
| Last.fm / Wikipedia / TheAudioDB | Public APIs | Artist of the Day bios |
| streamed.pk | Public API | Live sports streams |
| CFBD | DLT + Bearer | CFB games, lines, SP+, PPA, weather |

---

## Design Principles

**Separation of concerns** — Intent (`goals/2026.yaml`), facts (`data/`), and logic (`scripts/`, `dbt/`) are explicitly separated.

**Automation over willpower** — Runs at 9am daily. Willpower is finite. Cron jobs are not.

**DuckDB as the hub** — All sources land in DuckDB. dbt builds clean marts. FastAPI queries read-only. No spaghetti.

**Verify, don't assume** — Every API integration has confirmed field names against live data. Guessing wrong once in production is expensive.

**AI as co-processor** — Used for bounded, testable tasks (brief, recap, picks analysis, cover art). Never for core data logic.
