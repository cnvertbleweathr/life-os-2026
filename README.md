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
Film:     Letterboxd + Plex → mart_film_watches → scene catalog (Claude suggests, you approve)
          → 64×32 pixel GIFs → /film page and a Raspberry Pi LED panel (/api/display)
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
│   ├── progeny_pipeline.py            # kids' YAML + JSONL → progeny.* (see Progeny)
│   ├── _jsonl.py                      # shared latest-row-per-key reader
│   ├── cfbd_pipeline.py
│   ├── cfbd_extended_pipeline.py      # Per-game PPA (current season), recruiting, etc.
│   ├── live_picks_pipeline.py         # Graded picks → cfbd.live_picks
│   ├── letterboxd_pipeline.py         # Letterboxd RSS → letterboxd.diary_entries (TMDB id, rating, liked)
│   ├── plex_pipeline.py               # Plex watch history (movies) → plex.history, incremental; --full reloads
│   ├── film_catalog_pipeline.py       # scene catalog JSONL → film.scene_catalog
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
│   ├── import_letterboxd_csv.py       # one-off: full Letterboxd history from the data export
│   ├── film_suggest_scenes.py         # Claude (Haiku 5.5) suggests each new film's GIF scene
│   ├── film_catalog.py                # review the scene catalog: list / approve / edit / reject
│   ├── film_gif_render.py             # render approved films' 64×32 GIFs
│   ├── dev.sh                         # dev servers (:8001 API with ONS_DEV=1, :3001 UI)
│   └── [20+ other utilities]
│
├── film/                              # GIF renderer: palette (from globals.css), 3×5 font,
│   ├── canvas.py · palette.py · font.py   #   motifs (rain · projector · vhs), sprites/ (public-domain
│   ├── motifs.py · clip.py            #   scenes, e.g. Nosferatu), clip.py (ffmpeg + Bayer dither)
│   └── sprites/
│
├── api/                               # FastAPI backend — never writes to DuckDB
│   ├── main.py
│   ├── deps.py
│   ├── store.py                       # append-only JSONL write path (habits, check-in, inbox)
│   ├── auth.py                        # write key for personal endpoints over the tunnel
│   ├── espn.py                        # ESPN client; my_games() feeds the ticker and the LED panel
│   ├── film_catalog.py                # scene catalog rules + approve/edit/reject (JSONL snapshots)
│   ├── display.py                     # 64×32 score and clock frames for the LED panel
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
│       ├── kglw.py
│       ├── film.py                    # /api/film — watches, library, scene, strip (public); queue (owner)
│       └── display.py                 # /api/display — LED panel playlist, GIFs, frames (owner)
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
│   │   ├── capture/page.tsx           # Capture inbox
│   │   └── film/page.tsx              # Film: watches, review queue, Screening Room
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
│   │                                  #      mart_kglw_youtube_matches, mart_kglw_music_videos,
│   │                                  #      mart_film_watches (Letterboxd + Plex, one row per film per day)
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
│   ├── film/scene_catalog.jsonl       # film scene catalog (append-only snapshots)
│   ├── film/gifs/                     # rendered GIFs — gitignored; plex_clip ones are owner-only
│   ├── display/logos/                 # ESPN logos cached at 12×12 for the LED panel
│   ├── bets/todays_picks.json
│   └── [other domains]
│
├── tests/
│   ├── smoke_test.py                  # 18 checks — cfb/env/metrics/sync groups (run directly)
│   ├── test_write_path.py             # 15 tests — store, endpoints, write key, pipelines
│   ├── test_freshness_check.py        # 10 tests — incl. replays of the Oct 2026 silent failures
│   ├── test_spotify_compat.py         # 3 tests — old/new playlist shapes, unreadable playlists
│   ├── test_film_pipelines.py         # 6 tests — Letterboxd RSS parsing, Plex GUIDs, --full reload
│   ├── test_letterboxd_csv.py         # 21 tests — CSV import, TMDB lookup cache, RSS/CSV dedupe via dbt
│   ├── test_film_catalog.py           # 15 tests — catalog rules, queue API, suggestion step, mirror
│   ├── test_film_render.py            # 16 tests — palette, font, loops, clip dither, render flow
│   ├── test_film_api.py               # 4 tests — /api/film visibility and strips
│   └── test_display.py                # 21 tests — score frames, playlist curation, the Pi player
│
├── ops/macmini/
│   ├── harden.sh                      # check: what would keep ONS offline · apply: power, updates, heartbeat
│   ├── heartbeat.sh                   # 5-min healthchecks.io ping from boot; /fail with reason
│   └── com.ons.heartbeat.plist.template
├── ops/pi/display/                    # LED panel player for the Raspberry Pi (+ systemd unit, setup README)
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

Runs automatically at 9am via launchd (`com.ons.daily-sync.plist`); a separate nightly backup runs at 2am (`com.ons.backup-duckdb.plist`). The sync runs 39 steps in order. Some steps only run on certain days:

| Stage | Steps | When |
|---|---|---|
| Life data | strava, hardcover, habits, checkin, capture_inbox, calendar, shows, spotify, Daily 10, streams, WOD | Daily (calendar export Mon/Thu) |
| CFB lines + news | `track_lines`, `track_news_signals` | Daily · Wed/Thu |
| CFB in-season | `cfbd_pipeline --skip-advanced` (games + final scores, lines, SP+) → `cfbd_extended_pipeline` (per-game PPA) → `mart_cfb_live_strength` → `grade_picks` → `live_picks_pipeline` → `mart_live_picks` | Mon + Thu–Sun |
| CFB picks | `generate_picks` · `generate_picks_report` | Mon–Wed · Thu |
| King Gizzard | `kglw` (kglw.net catalog, `--shows-only`), `kglw_youtube` (channel uploads + music-videos playlist) | Daily, before dbt |
| Film in | `letterboxd` (RSS diary), `plex` (watch history; a no-op until `PLEX_URL`/`PLEX_TOKEN` are set) | Daily, before dbt |
| Goals + transform | `sync_playlist_artists`, `sync_goal_progress`, `dbt`, `load_goals`, `load_goal_progress` | Daily |
| Film out | `film_suggest_scenes` (Claude suggests a scene per new film), `film_gif_render` (approved → GIFs), `film_catalog` (catalog → DuckDB) | Daily, after dbt |
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
| `PLEX_URL` / `PLEX_TOKEN` | Your Plex server and its `X-Plex-Token` — film watch history and `plex_clip` GIFs |
| `PLEX_ACCOUNT_ID` | Optional — whose plays count: `1` (server owner, default) or `all` |
| `PLEX_MEDIA_PATH_MAP` | Optional — `server_prefix=local_prefix` if Plex's media is mounted on the Mac mini (otherwise clips stream from Plex) |
| `TMDB_API_KEY` | Optional — [TMDB](https://www.themoviedb.org/settings/api) v3 key or v4 token; resolves TMDB ids for the Letterboxd CSV backfill |
| `DISPLAY_QUIET_HOURS` | Optional — e.g. `23-7`: the LED panel goes dark between those local hours |
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
| **Progeny** | Kids: birthday / due-date countdowns, this week's learning focus, timeline, learning paths, CDC milestones, read-aloud count, baby-prep burndown, and a log form. Owner-only, reads included. See [Progeny](#progeny-kids-development) |
| **Film** | Watches this year (Letterboxd + Plex, with the source of each), average rating, by month and by decade; the scene review queue (owner only); the Screening Room wall of every rendered loop. The title scene is a cinema playing your latest watch's loop |

---

## Personal Input & the Write Key

The API holds a read-only DuckDB connection (single-writer rule), so it never writes to the warehouse. Anything entered in the UI is appended to a JSONL log by `api/store.py`; the matching pipeline loads the latest entry per day (or per item) on the next sync.

| Input | Endpoint | Log | Warehouse table |
|---|---|---|---|
| Habit toggles | `POST /api/habits/log` | `data/habits/habits_log.jsonl` | `habits.habit_log`, `habits.habit_summary` |
| Daily check-in | `POST /api/checkin/log` | `data/checkin/checkin_log.jsonl` | `checkin.daily_checkin` |
| Capture | `POST /api/inbox` | `data/inbox/capture_inbox.jsonl` | `raw.capture_inbox` |
| Film scene review | `POST /api/film/queue/{film}/approve` · `/reject`, `PATCH /api/film/queue/{film}` | `data/film/scene_catalog.jsonl` | `film.scene_catalog` |
| Progeny (quotes, firsts, books, learning, milestones, prep tasks) | `POST /api/progeny/{kind}` | `data/progeny/{kind}.jsonl` | `progeny.*` |

The Habits page reads today and the 21-day strip straight from the log, so a toggle shows up immediately; streaks and YTD figures update after the sync. Habits can be backfilled up to 7 days.

**Write key.** narcisystem.com is public, so habit logging and everything under `/api/checkin`, `/api/inbox`, `/api/film/queue`, `/api/display` and `/api/progeny` (reads too) require `X-ONS-Write-Token` when the request comes through Cloudflare. The first time a device needs it, the page asks for the key and keeps it in that browser. Requests on the Mac mini or over Tailscale don't need it. If `ONS_WRITE_TOKEN` isn't set, those endpoints refuse public traffic. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

---

## Progeny (kids' development)

A page on narcisystem.com (`/progeny`: `web/app/progeny/page.tsx` over `api/routers/progeny.py`) for the kids: quotes, firsts, CDC milestones, learning paths, books read aloud (toward 1,000 Books Before Kindergarten) and a baby-prep burndown.

**Privacy.** Everything about the kids lives in `data/progeny/`, which is gitignored (the rule sits at the end of `.gitignore` so nothing re-includes it). Only code, the generic reference YAML and the config template are committed. `tests/test_progeny.py` fails if `data/progeny/` ever stops being ignored. OpenClaw can't read the `progeny` schema (it isn't on the allowlist in `openclaw/rbac/policy.py`). Every `/api/progeny` endpoint is owner-only, **reads included**: through Cloudflare the page shows nothing until the device has the write key, and it never prompts on load. On the Mac mini and over Tailscale it opens without one. `tests/test_progeny_api.py` checks this.

| File | Committed? | What it is |
|---|---|---|
| `progeny/config/kids.example.yaml` | yes | Template for the kids config |
| `progeny/reference/cdc_milestones.yaml` | yes | CDC *Learn the Signs. Act Early.* checklists, 2 months to 5 years, with stable ids |
| `progeny/reference/learning_paths.yaml` | yes | Skill trees (literacy, numeracy, fine/gross motor, social-emotional, music, practical life) with levels and activities |
| `data/progeny/kids.yaml` | **no** | Real kids: `kid_id`, `display_name`, `birthdate`, `due_date`, optional `kindergarten_start` |
| `data/progeny/{quotes,firsts,books,milestones,path_evidence,prep_tasks}.jsonl` | **no** | Append-only logs written by the page |

**Setup.** `mkdir -p data/progeny && cp progeny/config/kids.example.yaml data/progeny/kids.yaml`, then edit it. Every log row points at `kid_id`, never a name, so a kid can be renamed at any time. When the baby arrives, set `display_name` and `birthdate`: the header switches from the due-date countdown to the baby's age, and milestones start. Ages are never stored. The `mart_progeny_*` models are views that compute them from the birthdate on every read.

**Logging.** Use the **Log** card on the page (quote, first, book, learning, milestone, prep task), the **Seen it** buttons on the Milestones tab, or **Done** on Baby prep. Each one calls `POST /api/progeny/{kind}`, which appends a line with a uuid `id` to the matching JSONL file (`progeny/store.py`) and never touches DuckDB. Books are marked as re-reads automatically, checking the warehouse and the not-yet-synced log. Entries appear after the next daily sync, or run `python scripts/daily_sync.py --only progeny dbt`. To fix an entry, append a full copy with the same `id`. To delete one, append `{"id": "…", "deleted": true}`. The latest line per id wins.

**Data flow.** `pipelines/progeny_pipeline.py` (`progeny` step in the daily sync) loads the YAML and the logs into the `progeny` schema, merging on `id`. Then dbt builds `stg_progeny__*` and these marts:

| Mart | Grain |
|---|---|
| `mart_progeny_kids` | Kid: age, birthday and due-date countdowns, kindergarten target |
| `mart_progeny_timeline` | Event (quote, first, milestone, learning evidence) with age at the event |
| `mart_progeny_milestones` | Kid × milestone in the current and next CDC band: observed or not yet (no "behind" scoring) |
| `mart_progeny_paths` | Kid × path: reached level, % complete, focus level and activities |
| `mart_progeny_reading` / `_reading_titles` | Kid: reads toward 1,000 and the pace needed · Kid × title: times read |
| `mart_progeny_prep` / `_prep_tasks` | Day: open tasks vs an ideal line to the due date · Task: status |

Every staging model falls back to a typed empty select (`select_or_empty` macro) when the pipeline hasn't loaded a table yet, so dbt runs clean before anything has been logged.

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

## Film

Plan: [`docs/film/ONS_FILM_SECTION_PLAN.md`](./docs/film/ONS_FILM_SECTION_PLAN.md). Four stages, all in the daily sync:

1. **Watched.** `letterboxd` (RSS, ~50 latest entries) and `plex` (watch history, movies only) feed `stg_letterboxd__diary` and `stg_plex__history` → `mart_film_watches`: one row per film per day, `source` = letterboxd / plex / both. Films key on the TMDB id; a Plex play within a day of a Letterboxd entry for the same film counts as that watch. For full Letterboxd history, run the one-off CSV backfill: `python scripts/import_letterboxd_csv.py --file ~/Downloads/letterboxd-export/diary.csv` (stop `com.ons.fastapi` first; see the script).
2. **Scene picked.** `film_suggest_scenes` asks Claude Haiku 5.5 for each new film's most iconic moment (about $0.0001 a film, logged to `data/ai/generations.jsonl`, stopping at the shared $5/month AI budget). Nothing renders until you approve it, on `/film` or with `python scripts/film_catalog.py approve tmdb:30497 --clip 3400 3405`.
3. **GIF rendered.** `film_gif_render` makes two 64×32, 5-second loops per approved film: `gif_web` (light palette) and `gif_matrix` (dark palette, for the LED panel). The render mode is set by rule, not by the model:
   - `sprite` — a hand-built pixel scene, only for US public-domain films (`film/sprites/`);
   - `plex_clip` — 5 seconds of your own Plex copy, pixelated (owner-only: never served publicly);
   - `motif` — an original loop with the title (rain, projector, VHS).
4. **Shown.** On `/film` (title scene and Screening Room), and on a 64×32 LED panel: a Raspberry Pi plays whatever `GET /api/display/playlist` returns — film loops with score cards for your teams between them, and live games pre-empting the films. Setup: [`ops/pi/display/README.md`](./ops/pi/display/README.md).

---

## CFB Betting System

**Cross-season validated edges (2021–2025, walk-forward, no lookahead; figures from [`docs/SYSTEM_EXPLAINER.md`](./docs/SYSTEM_EXPLAINER.md)):**

```
250-115 · 68.5% cover · +30.8% ROI at -110 · 5/5 seasons profitable
Favorites (official): 186-97 (65.7% cover, +25.5% ROI)
Underdogs (official): 33-9 (78.6% cover, +50.0% ROI)
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
| Letterboxd | Public RSS + data-export CSV | Film diary, ratings, likes, rewatches; TMDB id from the feed |
| Plex | Server API (`X-Plex-Token`) | Movie watch history, TMDB ids, and the files `plex_clip` GIFs are cut from |
| TMDB | Search API (optional) | TMDB ids for the Letterboxd CSV backfill |
| KGLW.net | Public API v2 | Shows (incl. announced dates), songs, venues, jam chart |
| YouTube (KGLW channel) | Data API v3 | Live recordings matched to shows; official music videos from the band's music-videos playlist |
| Last.fm / Wikipedia / TheAudioDB | Public APIs | Artist of the Day bios |
| ESPN | Public site API (unofficial, keyless) | Live scores, team schedules, team news, team logos (ticker, Sports page, LED panel) |
| CFBD | DLT + Bearer | CFB games, lines, SP+, PPA, weather |

---

## Design Principles

**Separation of concerns** — Intent (`goals/2026.yaml`), facts (`data/`), and logic (`scripts/`, `dbt/`) are explicitly separated.

**Automation over willpower** — Runs at 9am daily. Willpower is finite. Cron jobs are not.

**DuckDB as the hub** — All sources land in DuckDB. dbt builds clean marts. FastAPI queries read-only; user input goes to append-only logs that the sync loads. No spaghetti.

**Verify, don't assume** — Every API integration has confirmed field names against live data. Guessing wrong once in production is expensive.

**AI as co-processor** — Used for bounded, testable tasks (brief, recap, picks analysis, cover art). Never for core data logic.
