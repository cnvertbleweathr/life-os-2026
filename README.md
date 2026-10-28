# Operating Narcisystem (ONS) 2026

ONS is a personal analytics platform that treats life as a system — observable, measurable, automatable, and continuously improvable. It ingests your entire existence, runs it through a data stack, and tells you whether you're actually getting shit done or just think you are.

---

## Architecture

```
Your Life → DLT Pipelines → DuckDB → dbt → FastAPI → Next.js
                                ↑            │
                         Local Inputs        └─ writes ─→ JSONL logs ─┐
                    (habits, check-ins,         (habits, check-in,    │
                     Capture inbox,              Capture)             │
                     SugarWOD CSV, goals YAML) ←──── loaded nightly ──┘

AI layer: OpenClaw (Claude API) — morning brief, weekly recap, CFB narratives
          → being replaced by LangGraph agents
```

The dashboard runs on FastAPI + Next.js (replaced Streamlit in June 2026). FastAPI is a thin query layer over DuckDB/dbt marts and never writes to the warehouse: what you enter in the UI (habits, check-ins, Capture) is appended to JSONL logs under `data/` and loaded by the nightly sync (see [Personal input](#personal-input--the-write-key)). Next.js is the actual UI. OpenClaw is the current AI layer (daily briefs, weekly reviews, game analysis); it is being retired in favor of LangGraph agents — see [ROADMAP › Agentic Layer](./ROADMAP.md#agentic-layer--replaces-openclaw-new-track-2026-10-11).

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
│   ├── habits_pipeline.py             # habits JSONL → habits.* (latest entry per day)
│   ├── checkin_pipeline.py            # check-in JSONL → checkin.daily_checkin
│   ├── inbox_pipeline.py              # Capture JSONL → raw.capture_inbox
│   ├── _jsonl.py                      # shared latest-row-per-key reader
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
│   ├── freshness_check.py             # alerts when a source/step stops updating
│   ├── spotify_compat.py              # playlist reads for Spotify's 2026 API shape
│   ├── spotify_check.py               # Spotify access diagnostic (read-only)
│   ├── tz_utils.py                    # Denver-timezone-correct date helpers
│   ├── generate_picks.py              # Weekly picks (Mon–Wed)
│   ├── generate_picks_report.py       # Thursday briefing
│   ├── grade_picks.py                 # Grades results (Mon + Thu–Sun)
│   ├── generate_postmortem.py
│   ├── kglw_video_qa.py               # KGLW freshness + unmatched-upload report
│   └── [20+ other utilities]
│
├── api/                               # FastAPI backend — never writes to DuckDB
│   ├── main.py
│   ├── deps.py
│   ├── store.py                       # append-only JSONL write path (habits, check-in, inbox)
│   ├── auth.py                        # write key for personal endpoints over the tunnel
│   └── routers/
│       ├── home.py                    # /api/home — digest, brief, calendar, WOD, daily10
│       ├── habits.py                  # incl. POST /log, GET /recent
│       ├── checkin.py                 # /api/checkin — POST /log, /today, /history
│       ├── inbox.py                   # /api/inbox — capture + list
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
│   │   ├── checkin/page.tsx
│   │   └── capture/page.tsx           # Capture inbox
│   ├── components/
│   │   ├── nav/Sidebar.tsx
│   │   ├── cfb/LiveTrackerBanner.tsx
│   │   └── ui/{primitives,icons,viz,TeamLogo,ProTeamLogo}.tsx
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
│   ├── daily/                         # Per-day sync logs, health.txt, freshness.json
│   ├── ai/generations.jsonl           # OpenClaw audit trail — every generation logged
│   ├── habits/habits_log.jsonl        # written by the web UI (append-only)
│   ├── checkin/checkin_log.jsonl      # written by the web UI (append-only)
│   ├── inbox/capture_inbox.jsonl      # written by the web UI (append-only)
│   ├── bets/todays_picks.json
│   └── [other domains]
│
├── tests/
│   ├── smoke_test.py                  # 18 checks — cfb/env/metrics/sync groups (run directly)
│   ├── test_write_path.py             # 15 tests — store, endpoints, write key, pipelines
│   ├── test_freshness_check.py        # 8 tests — incl. replays of the Oct 2026 silent failures
│   └── test_spotify_compat.py         # 3 tests — old/new playlist shapes, unreadable playlists
│
├── ops/macmini/
│   ├── harden.sh                      # check: what would keep ONS offline · apply: power, updates, heartbeat
│   ├── heartbeat.sh                   # 5-min healthchecks.io ping from boot; /fail with reason
│   └── com.ons.heartbeat.plist.template
│
├── .github/workflows/                 # ci.yml (syntax, Python tests, ShellCheck, hardcode audit,
│                                      #   dbt parse, TypeScript), picks-validation.yml (Thu)
├── launchd/
│   ├── com.ons.daily-sync.plist       # 9am daily sync
│   └── com.ons.backup-duckdb.plist    # 2am nightly backup
│   # com.ons.fastapi / com.ons.nextjs live only in ~/Library/LaunchAgents on the Mac mini
└── secrets/
```

---

## Daily Workflow

Runs automatically at 9am via launchd (`com.ons.daily-sync.plist`); a separate nightly backup runs at 2am (`com.ons.backup-duckdb.plist`). The sync runs 36 steps in order. Some steps only run on certain days:

| Stage | Steps | When |
|---|---|---|
| Life data | strava, hardcover, habits, checkin, capture_inbox, calendar, shows, spotify, Daily 10, streams, WOD | Daily (calendar export Mon/Thu) |
| CFB lines + news | `track_lines`, `track_news_signals` | Daily · Wed/Thu |
| CFB in-season | `cfbd_pipeline --skip-advanced` (games + final scores, lines, SP+) → `cfbd_extended_pipeline` (per-game PPA) → `mart_cfb_live_strength` → `grade_picks` → `live_picks_pipeline` → `mart_live_picks` | Mon + Thu–Sun |
| CFB picks | `generate_picks` · `generate_picks_report` | Mon–Wed · Thu |
| King Gizzard | `kglw` (kglw.net catalog, `--shows-only`), `kglw_youtube` (channel uploads + music-videos playlist) | Daily, before dbt |
| Goals + transform | `sync_playlist_artists`, `sync_goal_progress`, `dbt`, `load_goals`, `load_goal_progress` | Daily |
| Ops + AI + backup | `openclaw_generation`, `freshness_check`, `backup_duckdb` | Daily, last |

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
| `ONS_WRITE_TOKEN` | Any long random string — the write key for habits/check-in/Capture over narcisystem.com (see below) |
| `HEARTBEAT_URL` / `HEALTHCHECK_SYNC_URL` | [healthchecks.io](https://healthchecks.io) ping URLs — Mac mini heartbeat and daily-sync dead-man's switch |
| `SPOTIFY_TEWNIDGE_PLAYLIST_ID` / `SPOTIFY_DEEDS_PLAYLIST_ID` | Optional overrides — must be playlists you own or collaborate on (Spotify, since Mar 2026) |

---

## Operations & Monitoring

The Mac mini is the single host for the warehouse, API, UI and tunnel, so it has to come back on its own and say so when it doesn't. Full procedure: [`docs/MACMINI_RUNBOOK.md`](./docs/MACMINI_RUNBOOK.md).

| Layer | What | Alerts via |
|---|---|---|
| Machine | `ops/macmini/heartbeat.sh` every 5 min from boot: Tailscale, cloudflared, FastAPI, Next.js | healthchecks.io (`/fail` with reason; silence = Mac down) |
| Daily sync | `daily_sync.py` pings start/end; red only if a required step aborts | healthchecks.io (missed 9am run) |
| Data | `freshness_check` step: steps failing 2+ runs, last success overdue (learned per step), stale CFB scores in season, backups > 36h, Daily 10 and show listings | ntfy |
| Config | `bash ops/macmini/harden.sh check` — power, updates, FileVault, Remote Login, Tailscale variant, cloudflared mode, services, env | (run by hand) |

---

## App Pages

| Page | What it shows |
|---|---|
| **Home** | OpenClaw morning brief, stat row, calendar, WOD, Daily 10, goal pacing |
| **Habits** | Today's checklist (tap to log — saved immediately), current + longest streaks, real 21-day history |
| **Fitness** | YTD/weekly running miles, pace, bar chart, recent runs |
| **Reading** | Books read, fiction/nonfiction split |
| **Goals** | All domains, pace status badges, progress bars |
| **Music** | Year listening stats, Daily 10 playlist, Artist of the Day (from Tewnidge), upcoming Denver shows with artist matching and Google Calendar links (`/shows` redirects here) |
| **Sports** | Streams, AI-ranked top 5, news |
| **CFB Betting** | **This Week:** week picker for any 2026 week, official picks + watch list with WIN/LOSS and final scores once graded, weekly record, drill-down showing both teams' season-to-date trends going into that week · **Matchup Lab:** head-to-head model run · **Teams:** sortable table of Off/Def percentile, Off/Def/Net trend and points for/against; team profile with trend chart and game log |
| **King Gizzard** | **Shows:** live shows and music videos in one list (All · Upcoming · Music Videos · Watchable), with embedded YouTube recordings and official videos · **Songs:** song catalog |
| **Check-in** | 30-second daily energy/mood/focus/sleep/soreness/stress log with readiness score; saved, and re-saving updates today's entry |
| **Capture** | Quick inbox for ideas, tasks, links and notes (⌘/Ctrl+Enter), tagged by kind and area; newest first |

---

## Personal Input & the Write Key

The API holds a read-only DuckDB connection (single-writer rule), so it never writes to the warehouse. Anything entered in the UI is appended to a JSONL log by `api/store.py`; the matching pipeline loads the latest entry per day (or per item) on the next sync.

| Input | Endpoint | Log | Warehouse table |
|---|---|---|---|
| Habit toggles | `POST /api/habits/log` | `data/habits/habits_log.jsonl` | `habits.habit_log`, `habits.habit_summary` |
| Daily check-in | `POST /api/checkin/log` | `data/checkin/checkin_log.jsonl` | `checkin.daily_checkin` |
| Capture | `POST /api/inbox` | `data/inbox/capture_inbox.jsonl` | `raw.capture_inbox` |

The Habits page reads today and the 21-day strip straight from the log, so a toggle shows up immediately; streaks and YTD figures update after the sync. Habits can be backfilled up to 7 days.

**Write key.** narcisystem.com is public, so habit logging and everything under `/api/checkin` and `/api/inbox` require `X-ONS-Write-Token` when the request comes through Cloudflare. The first time a device needs it, the page asks for the key and keeps it in that browser. Requests on the Mac mini or over Tailscale don't need it. If `ONS_WRITE_TOKEN` isn't set, those endpoints refuse public traffic. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

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
| Habits | Web UI → JSONL | Meditation, pushups, reading pages |
| Daily check-in | Web UI → JSONL | Energy, mood, focus, sleep, soreness, stress, readiness |
| Capture inbox | Web UI → JSONL | Ideas, tasks, links, notes |
| Google Calendar | OAuth API | Events, date nights |
| SugarWOD | CSV export | CrossFit classes, PRs |
| Spotify | JSON export + API | Streaming stats, Daily 10 |
| AEG / Ticketmaster | Public API | Denver shows |
| Letterboxd | Public RSS | Film diary, ratings (pipeline built, not yet in the daily sync) |
| KGLW.net | Public API v2 | Shows (incl. announced dates), songs, venues, jam chart |
| YouTube (KGLW channel) | Data API v3 | Live recordings matched to shows; official music videos from the band's music-videos playlist |
| Last.fm / Wikipedia / TheAudioDB | Public APIs | Artist of the Day bios |
| ESPN | Public site API (unofficial, keyless) | Live scores, team schedules, team news |
| CFBD | DLT + Bearer | CFB games, lines, SP+, PPA, weather |

---

## Design Principles

**Separation of concerns** — Intent (`goals/2026.yaml`), facts (`data/`), and logic (`scripts/`, `dbt/`) are explicitly separated.

**Automation over willpower** — Runs at 9am daily. Willpower is finite. Cron jobs are not.

**DuckDB as the hub** — All sources land in DuckDB. dbt builds clean marts. FastAPI queries read-only; user input goes to append-only logs that the sync loads. No spaghetti.

**Verify, don't assume** — Every API integration has confirmed field names against live data. Guessing wrong once in production is expensive.

**AI as co-processor** — Used for bounded, testable tasks (brief, recap, picks analysis, cover art). Never for core data logic.
