# Operating Narcisystem (ONS) 2026

ONS is a personal analytics platform that treats life as a system — observable, measurable, automatable, and continuously improvable. It ingests your entire existence, runs it through a data stack, and tells you whether you're actually getting shit done or just think you are.


---

## Architecture

```
Your Life → DLT Pipelines → DuckDB → dbt → FastAPI → Next.js
                                ↑
                         Local Inputs
                    (habits, SugarWOD CSV, goals YAML)
```

The dashboard moved from Streamlit to a proper FastAPI + Next.js split in June 2026. FastAPI is a thin read-only query layer over DuckDB/dbt marts; Next.js is the actual UI. Streamlit is retired.

Full architecture diagrams, dbt lineage, and the daily sync sequence live in [`ARCHITECTURE.md`](./ARCHITECTURE.md) — kept separate from this README so each stays focused.

---

## Repository Structure

```
ons-2026/
├── goals/
│   └── 2026.yaml                      # What you said you'd do. No judgment.
│
├── pipelines/                         # DLT ingestion pipelines
│   ├── strava_pipeline.py             # Strava API → DuckDB
│   ├── hardcover_pipeline.py          # Hardcover API → DuckDB
│   ├── habits_pipeline.py             # Local JSONL → DuckDB
│   ├── cfbd_pipeline.py               # CFB games, lines, SP+ ratings → DuckDB
│   ├── cfbd_extended_pipeline.py      # Weather, coaches, PPA, returning production → DuckDB
│   ├── letterboxd_pipeline.py         # Letterboxd RSS → DuckDB (no auth)
│   └── kglw_pipeline.py               # King Gizzard live show catalog → DuckDB (no auth)
│
├── scripts/                           # Orchestration + auxiliary scripts
│   ├── daily_sync.py                  # ← The one command to rule them all
│   ├── backup_duckdb.py               # Timestamped backups, 7-day retention
│   ├── notify.py                      # ntfy.sh push notifications (sync-ok/sync-fail/picks)
│   ├── tz_utils.py                    # Denver-timezone-correct date helpers
│   ├── generate_morning_brief.py      # OpenClaw — Claude API daily brief
│   ├── generate_weekly_review.py      # OpenClaw — Claude API Sunday review
│   ├── sync_goal_progress.py          # Pull actuals from DuckDB → goal_progress.csv
│   ├── sync_playlist_artists.py       # Tewnidge + Deeds artists → show cross-reference
│   ├── fetch_streams.py               # Today's sports streams via streamed.pk
│   ├── calendar_export.py             # Google Calendar → CSV
│   ├── calendar_metrics.py            # Date night tracking (you're welcome)
│   ├── import_sugarwod_csv.py         # SugarWOD CSV → DuckDB
│   ├── spotify_ingest_streaming.py    # Spotify JSON export → streams_clean.csv
│   ├── spotify_metrics.py             # Compute YTD listening stats
│   ├── spotify_daily10_playlist.py    # Generate Daily 10 playlist (Bucket A + B)
│   ├── spotify_daily10_decorate.py    # AI cover art (gpt-image-1 + retry logic)
│   ├── aeg_events_fetch.py            # AEG concert data → Denver shows
│   ├── ticketmaster_fetch_denver.py   # Ticketmaster → Denver shows
│   ├── download_cfb_logos.py          # CFBD team logos → web/public/logos/
│   ├── track_lines.py                 # CFB line movement snapshots (in-season)
│   ├── track_news_signals.py          # CFB news-driven line-mover signals (in-season)
│   ├── generate_picks.py              # Weekly CFB picks (unified scorer)
│   ├── generate_picks_report.py       # Human-readable Thursday picks briefing
│   ├── generate_postmortem.py         # Sat/Sun results vs picks, season log
│   ├── pregame_lookup.py              # CFB pre-game edge report (queries DuckDB)
│   ├── cfb_backtest.py                # Simulate $1 bets on historical games
│   ├── backtest_walk_forward.py       # Canonical walk-forward scorer — score_game()
│   ├── cfb_edge_validation.py         # Cross-season edge validation (2021-2025)
│   ├── cfb_team_analysis.py           # Per-team ATS profiles
│   ├── cfb_build_team_profiles.py     # Build cfbd.team_profiles (run annually)
│   └── setup_runner.py                # Mac mini GitHub Actions self-hosted runner guide
│
├── api/                               # FastAPI backend — read-only query layer
│   ├── main.py                        # App entry, lifespan-managed DuckDB connection, CORS
│   ├── deps.py                        # Shared get_db / query / query_one helpers (NaN-safe)
│   └── routers/
│       ├── home.py                    # /api/home — digest, calendar, WOD, daily10, goals
│       ├── habits.py                  # /api/habits — today + streaks
│       ├── fitness.py                 # /api/fitness — running summary, recent runs
│       ├── reading.py                 # /api/reading — books read, in-progress (always [])
│       ├── goals.py                   # /api/goals — progress, by-domain (array of groups)
│       ├── music.py                   # /api/music — top artists, news
│       ├── shows.py                   # /api/shows — Denver concerts, artist matching
│       ├── sports.py                  # /api/sports — news
│       ├── cfb.py                     # /api/cfb — teams, picks, line accuracy, model info
│       └── kglw.py                    # /api/kglw — KGLW show/song/venue/jamchart catalog
│
├── web/                                # Next.js frontend — the actual UI
│   ├── app/
│   │   ├── page.tsx                   # Home
│   │   ├── habits/page.tsx
│   │   ├── fitness/page.tsx
│   │   ├── reading/page.tsx
│   │   ├── goals/page.tsx
│   │   ├── music/page.tsx
│   │   ├── shows/page.tsx
│   │   ├── sports/page.tsx
│   │   ├── cfb/page.tsx
│   │   ├── kglw/page.tsx              # King Gizzard show/song explorer
│   │   └── checkin/page.tsx           # Daily subjective check-in
│   ├── components/
│   │   ├── nav/Sidebar.tsx
│   │   └── ui/{primitives,TeamLogo}.tsx
│   ├── lib/
│   │   ├── api.ts                     # Typed client — every type matches CONFIRMED API shapes
│   │   └── cfb_team_ids.json          # 263-team name → CFBD numeric ID map
│   └── public/logos/                  # 260/263 CFB team logo PNGs (download_cfb_logos.py)
│
├── dbt/                                # Transformation layer
│   ├── models/
│   │   ├── core/
│   │   │   └── core__life_events.sql  # Universal event timeline (incremental)
│   │   ├── staging/                   # stg_* — clean + type raw sources
│   │   └── marts/                     # mart_* — business logic, CFB betting, goal pacing
│   └── profiles/
│
├── data/                               # Your entire life, locally stored
│   ├── warehouse/ons.duckdb           # DuckDB warehouse (gitignored, obviously)
│   ├── backups/duckdb/                # Nightly backups, 7-day retention
│   ├── daily/                         # Per-day sync logs + health.txt + summary.json
│   ├── habits/habits_log.jsonl        # Habit log (gitignored)
│   ├── calendar/
│   ├── spotify/
│   │   └── processed/daily10_latest.json
│   ├── sugarwod/
│   ├── shows/
│   ├── streams/today.json             # Live sports streams
│   ├── bets/todays_picks.json         # Current week's CFB picks
│   └── manual/goal_progress.csv
│
├── reports/
│   ├── daily/                         # OpenClaw morning briefs (YYYY-MM-DD.md)
│   └── weekly/                        # OpenClaw weekly reviews (YYYY-Www.md)
│
├── tests/
│   ├── smoke_test.py                  # 18 checks — cfb/env/metrics/sync groups
│   └── fixtures/load_fixtures.py      # Ephemeral fixture DuckDB for CI
│
├── .github/
│   ├── workflows/                     # ci.yml, ci-analytics.yml, picks-validation.yml,
│   │                                   # motherduck-sync.yml, mac-mini-refresh.yml
│   └── dependabot.yml
│
├── launchd/
│   ├── com.ons.daily-sync.plist       # 9am daily
│   └── com.ons.backup-duckdb.plist    # 2am nightly
│
├── notebooks/
│   ├── 01_line_accuracy_overview.ipynb
│   └── 02_extended_factors.ipynb
│
├── run_pipelines.py                   # Run DLT pipelines directly
└── secrets/                           # OAuth tokens (gitignored, not that kind)
```

---

## Daily Workflow

Runs automatically at 9am via launchd (`com.ons.daily-sync.plist`). Backup runs at 2am (`com.ons.backup-duckdb.plist`). You don't have to do anything. The system knows.

```bash
source .venv/bin/activate
python scripts/daily_sync.py
```

**Run the actual app:**
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
python scripts/daily_sync.py --skip spotify
```

**Important:** DuckDB only allows one read-write connection at a time. FastAPI opens its connection **read-only**, so it does *not* block pipeline writes — but two pipeline processes (or a pipeline and a manual `duckdb` CLI session) still will. If you hit a lock conflict, check `ps aux` for a stray process holding the file open.

---

## Setup

### Prerequisites
- Python 3.12+
- [uv](https://github.com/astral-sh/uv)
- Node.js 18+ / npm
- A concerning amount of self-interest

### Install
```bash
git clone https://github.com/cnvertbleweathr/life-os-2026.git
cd life-os-2026
uv sync
source .venv/bin/activate

cd web
npm install
cd ..
```

### Configure
```bash
cp .env.example .env
# Fill in your credentials. All of them.
```

| Key | Source |
|---|---|
| `STRAVA_CLIENT_ID` / `STRAVA_CLIENT_SECRET` | [Strava API](https://www.strava.com/settings/api) |
| `HARDCOVER_TOKEN` | [Hardcover Settings](https://hardcover.app/account/api) |
| `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` | [Spotify Developer](https://developer.spotify.com/dashboard) |
| `OPENAI_API_KEY` | [OpenAI](https://platform.openai.com/api-keys) — Daily 10 cover art |
| `ANTHROPIC_API_KEY` | [Anthropic](https://console.anthropic.com/) — morning brief, weekly review (OpenClaw) |
| `NEWS_API_KEY` | [NewsAPI](https://newsapi.org) — Music and Sports news feeds (optional; pages degrade gracefully without it) |
| `TICKETMASTER_API_KEY` | [Ticketmaster Developer](https://developer.ticketmaster.com) |
| `CFBD_API_TOKEN` | [CFBD](https://collegefootballdata.com) — Patreon tier for weather endpoint |
| `NTFY_TOPIC` | [ntfy.sh](https://ntfy.sh) — push notifications, no signup |
| `LETTERBOXD_USERNAME` | Your Letterboxd handle — public RSS, no auth |
| `KGLW_ATTENDED_SHOW_IDS` | Comma-separated show IDs from kglw.net — optional, personal attended-show log |

### First Run
```bash
# One-time OAuth dances
python scripts/strava_auth.py
python scripts/calendar_export.py  # opens browser

# Create directories
mkdir -p data/warehouse data/habits data/backups/duckdb

# Boot the system
python scripts/daily_sync.py

# Logos for the CFB page
python scripts/download_cfb_logos.py

# Run the app
uvicorn api.main:app --reload --port 8000 &
cd web && npm run dev
```

### SugarWOD (manual — they don't have an API, barbarians)
```bash
python scripts/import_sugarwod_csv.py --input /path/to/workouts.csv
```

### Spotify Streaming History
Request from Spotify → Account → Privacy Settings → Request Data. Takes a few days. Worth it.
```bash
python scripts/spotify_ingest_streaming.py
python scripts/spotify_metrics.py
```

### CFB Betting Setup
```bash
# Load historical data (2021-2025)
python pipelines/cfbd_pipeline.py
python pipelines/cfbd_extended_pipeline.py

# Build team ATS profiles (run once, then annually at season start)
python scripts/cfb_build_team_profiles.py --min-games 15

# Pre-game lookup
python scripts/pregame_lookup.py --home "Ohio State" --away "Michigan" --spread -7 --ou 45.5
```

### KGLW Show Catalog
```bash
python pipelines/kglw_pipeline.py --shows-only
```
No auth required. Confirmed live data shape as of 2026-06-20: 1104 shows, 1001 songs, 671 venues, 247 jam chart entries. **No lat/lng anywhere in the API** — the show/song explorer is a list/search UI, not a literal globe, until a separate geocoding pass exists.

---

## Data Sources

| Source | Method | Cadence | What it tracks |
|---|---|---|---|
| Strava | DLT + OAuth | Daily | Running miles, pace, weekly volume |
| Hardcover | DLT + GraphQL | Daily | Books read, fiction vs nonfiction |
| Habits | Local JSONL | Daily | Meditation, pushups, reading pages |
| Google Calendar | OAuth API | Mon/Thu | Date nights, events, birthdays you shouldn't forget |
| SugarWOD | CSV export | Manual | CrossFit classes, PRs, lift progressions |
| Spotify | JSON export + API | Daily | Streaming stats, Daily 10 playlist + AI cover art |
| AEG / Ticketmaster | Public API | Daily | Upcoming Denver concerts |
| Letterboxd | Public RSS, no auth | Daily | Diary entries, ratings |
| KGLW.net | Public API v2, no auth | On demand | King Gizzard shows, songs, venues, jam chart |
| streamed.pk | Public API | Daily | Live sports streams, AI-ranked top 5 |
| CFBD | DLT + Bearer token | Annual + in-season | CFB games, lines, SP+, PPA, weather, coaches |

---

## App Pages

| Page | What it shows |
|---|---|
| **Home** | Stat row, this week's calendar, today's WOD, Daily 10, goal pacing |
| **Habits** | Today's checklist, current + longest streaks |
| **Fitness** | YTD/total running miles, avg pace, weekly miles bar chart, recent runs |
| **Reading** | Books read, fiction/nonfiction split (in-progress tracking not yet available — Hardcover only syncs finished books) |
| **Goals** | All domains, pace status badges, progress bars (str-type goals like Roth IRA show "not numerically tracked" rather than a meaningless 0%) |
| **Music** | Top artists, music news (both degrade to an honest empty state without `NEWS_API_KEY` / a populated streams pipeline) |
| **Shows** | Upcoming Denver concerts, ⭐ artist matching (substring search — approximate, not exact) |
| **Sports** | Sports news (same `NEWS_API_KEY` dependency as Music) |
| **CFB Betting** | Validated model summary, sortable team performance table with real logos, consistently-profitable team list |
| **King Gizzard** | Upcoming shows, "on this day," searchable song catalog, jam chart notable versions |
| **Check-in** | 30-second daily energy/mood/focus/sleep/soreness/stress log |

---

## CFB Betting System

Cross-season validated edges (2021–2025, walk-forward, no lookahead):

```
318 bets · 224-94 · 70.4% win rate · +34.5% ROI · 4/4 seasons profitable
```

| Signal | ΔROI removed | Seasons consistent | Status |
|---|---|---|---|
| Success rate parity | -16.0% | 4/4 | ✅ Active |
| Team tier | -7.2% | 4/4 | ✅ Active |
| Spread range (3–17) | -5.1% | 3/4 | ✅ Active |
| Coach change | -3.5% | 4/4 | ✅ Active |
| Conference | -1.7% | 3/4 | ✅ Active |
| Returning production | -1.4% | 4/4 | ✅ Active |
| Recruiting / talent | -14.4% (aggregate) | 4/4 | ✅ Active |
| SP+ alignment | 0.0% | 0/4 | ❌ Disabled |
| Defensive havoc | 0.0% | 0/4 | ❌ Disabled |

Full team profiles for all 263 FBS teams stored in `cfbd.team_profiles`. Pre-game lookup available via `pregame_lookup.py`. One canonical scorer (`score_game()` in `backtest_walk_forward.py`) is imported directly by `generate_picks.py` — never a second, drifting copy of the scoring logic.

---

## Design Principles

**Separation of concerns** — intent (`goals/2026.yaml`), facts (`data/`), and logic (`scripts/`, `dbt/`) are explicitly separated. What you want to do and what you actually do live in different tables for a reason.

**Automation over willpower** — runs at 9am daily via launchd. Willpower is finite. Cron jobs are not.

**DuckDB as the hub** — all sources land in DuckDB. dbt builds clean marts on top. FastAPI queries marts read-only. No spaghetti.

**DLT for extraction** — schema inference, merge semantics, and load state handled by DLT. No bespoke fetch scripts held together with prayers.

**Verify, don't assume** — every API integration in this repo has, at some point, had a wrong field-name assumption caught by actually hitting the live endpoint and reading the real response. This isn't an embarrassment; it's the discipline that keeps the platform honest. When a router or pipeline doc comment says "confirmed real shape as of [date]," that means someone checked, not guessed.

**AI as co-processor** — used for bounded, testable tasks: morning brief, weekly review, playlist cover art, news feeds. Never for core data logic. The AI assists. The data tells the truth.
