# Operating Narcisystem (ONS) 2026

**Because if you're going to be obsessed with yourself, you might as well make it a data pipeline.**

ONS is a personal analytics platform that treats life as a system — observable, measurable, automatable, and continuously improvable. It ingests your entire existence, runs it through a data stack, and tells you whether you're actually getting shit done or just think you are.

Built on the same principles as modern data infrastructure, because your 9am runs and CrossFit PRs deserve the same rigor as production databases.

---

## Architecture

```
Your Life → DLT Pipelines → DuckDB → dbt → Streamlit Dashboard
                                ↑
                         Local Inputs
                    (habits, SugarWOD CSV)
```

### Full Data Flow

```mermaid
flowchart TD
    subgraph Sources["📡 Data Sources (your whole life)"]
        STRAVA[Strava API]
        HARDCOVER[Hardcover API]
        SPOTIFY[Spotify API]
        GCAL[Google Calendar API]
        SUGARWOD[SugarWOD CSV]
        HABITS[Habit Checkboxes\nStreamlit UI]
        AEG[AEG / Ticketmaster API]
        STREAMED[streamed.pk API]
    end

    subgraph Pipelines["⚙️ Ingestion"]
        P1[strava_pipeline.py]
        P2[hardcover_pipeline.py]
        P3[habits_pipeline.py]
        P4[calendar_export.py]
        P5[import_sugarwod_csv.py]
        P6[spotify_ingest_streaming.py]
        P7[aeg_events_fetch.py\nticketmaster_fetch_denver.py]
        P8[fetch_streams.py]
        P9[sync_playlist_artists.py]
    end

    subgraph DuckDB["🦆 DuckDB Warehouse"]
        S1[(strava.*)]
        S2[(hardcover.*)]
        S3[(habits.*)]
        S4[(calendar.*)]
        S5[(raw.*)]
    end

    subgraph DBT["🔧 dbt Transformations"]
        STG[Staging Models\nstg_*]
        MART[Mart Models\nmart_*]
    end

    subgraph Dashboard["📊 Streamlit Dashboard"]
        HOME[🧭 Home\nDigest + Streams + Alerts]
        HABITS_PAGE[✅ Habits\nCheckboxes + Streaks]
        FITNESS[💪 Fitness\nRunning + CrossFit]
        READING[📚 Reading\nFiction + Nonfiction]
        GOALS[🎯 Goals\nProgress by Domain]
        MUSIC[🎵 Music\nSpotify Stats + Daily 10]
        SHOWS[🎸 Shows\nDenver Concerts + Artist Alerts]
    end

    STRAVA --> P1 --> S1
    HARDCOVER --> P2 --> S2
    HABITS --> P3 --> S3
    GCAL --> P4 --> S4
    SUGARWOD --> P5 --> S5
    SPOTIFY --> P6 --> S5
    AEG --> P7 --> S5
    STREAMED --> P8
    SPOTIFY --> P9

    S1 & S2 & S3 & S4 & S5 --> STG --> MART

    MART --> HOME & HABITS_PAGE & FITNESS & READING & GOALS & MUSIC & SHOWS
```

---

### DLT Pipeline Detail

```mermaid
flowchart LR
    subgraph strava["Strava Pipeline"]
        direction TB
        SA[Strava API\nOAuth Token] --> SR[strava_activities\nresource]
        SR -->|merge on strava_id| SD[(strava.activities)]
        SD --> SS[running_summary\nresource]
        SS -->|replace| SRS[(strava.running_summary)]
    end

    subgraph hardcover["Hardcover Pipeline"]
        direction TB
        HA[Hardcover\nGraphQL API] --> HR[books_read\nresource]
        HR -->|merge on book_id| HD[(hardcover.books_read)]
        HD --> HS[reading_summary\nresource]
        HS -->|replace| HRS[(hardcover.reading_summary)]
    end

    subgraph habits["Habits Pipeline"]
        direction TB
        HF[data/habits/\nhabits_log.jsonl] --> HLR[habit_log\nresource]
        HLR -->|merge on date+habit| HLD[(habits.habit_log)]
        HLD --> HSR[habit_summary\nresource]
        HSR -->|replace| HSRD[(habits.habit_summary)]
    end
```

---

### dbt Transformation Layer

```mermaid
flowchart TD
    subgraph raw["Raw Layer"]
        RG[(raw.raw_goals)]
        RGP[(raw.raw_goal_progress)]
    end

    subgraph staging["Staging Layer"]
        SGA[stg_goals__annual_goals\nunnest JSON → one row per goal]
        SGP[stg_goals__progress]
        SHL[stg_habits__log]
        SHS[stg_habits__summary]
    end

    subgraph marts["Mart Layer"]
        MHP[mart_habit_performance\ndaily pivot + completion %]
        MHS[mart_habit_streaks\ncurrent + longest streak]
        MGD[mart_goal_detail]
        MGP[mart_goal_progress\ntargets + actuals]
        MHC[mart_ons_healthcheck]
    end

    RG --> SGA --> MGD --> MGP
    RGP --> SGP --> MGP
    SHL --> MHP & MHS
    SHS --> MGP
```

---

### Daily Sync Orchestration

```mermaid
sequenceDiagram
    participant L as launchd (9am)
    participant DS as daily_sync.py
    participant DLT as DLT Pipelines
    participant DB as DuckDB
    participant DBT as dbt
    participant STR as Streamlit

    L->>DS: triggers daily at 9am
    DS->>DLT: strava + hardcover + habits
    DLT->>DB: upsert all sources
    DS->>DS: calendar + shows + spotify
    DS->>DS: fetch_streams + sync_playlist_artists
    DS->>DS: sync_goal_progress
    DS->>DBT: dbt run
    DBT->>DB: build staging + mart models
    Note over STR: open any time — data is fresh
    STR->>DB: query mart_*
    STR->>STR: AI digest + streams + alerts
```

---

## Repository Structure

```
ons-2026/
├── goals/
│   └── 2026.yaml                    # What you said you'd do. No judgment.
│
├── pipelines/                       # DLT ingestion pipelines
│   ├── strava_pipeline.py           # Strava API → DuckDB
│   ├── hardcover_pipeline.py        # Hardcover API → DuckDB
│   └── habits_pipeline.py           # Local JSONL → DuckDB
│
├── scripts/                         # Orchestration + auxiliary scripts
│   ├── daily_sync.py                # ← The one command to rule them all
│   ├── sync_goal_progress.py        # Pull actuals from DuckDB → goal_progress.csv
│   ├── sync_playlist_artists.py     # Tewnidge + Deeds artists → show cross-reference
│   ├── fetch_streams.py             # Today's sports streams via streamed.pk
│   ├── calendar_export.py           # Google Calendar → CSV
│   ├── calendar_metrics.py          # Date night tracking (you're welcome)
│   ├── import_sugarwod_csv.py       # SugarWOD CSV → DuckDB
│   ├── spotify_ingest_streaming.py  # Spotify JSON export → streams_clean.csv
│   ├── spotify_metrics.py           # Compute YTD listening stats
│   ├── spotify_daily10_playlist.py  # Generate Daily 10 playlist
│   ├── spotify_daily10_decorate.py  # AI cover art (gpt-image-1 + retry logic)
│   ├── aeg_events_fetch.py          # AEG concert data → Denver shows
│   └── ticketmaster_fetch_denver.py # Ticketmaster → Denver shows
│
├── dbt/                             # Transformation layer
│   ├── models/
│   │   ├── staging/                 # stg_* — clean + type raw sources
│   │   └── marts/                   # mart_* — business logic + goal progress
│   └── profiles/
│
├── app/                             # Streamlit dashboard
│   ├── Home.py                      # Entry point — digest, streams, artist alerts
│   └── pages/
│       ├── 1_Habits.py              # Did you do the things? (checkbox edition)
│       ├── 2_Fitness.py             # Running (Strava) + CrossFit lift progressions
│       ├── 3_Reading.py             # Books: fiction escapism + nonfiction guilt
│       ├── 4_Goals.py               # The gap between ambition and reality
│       ├── 5_Music.py               # Spotify stats + Daily 10 embed
│       └── 6_Shows.py               # Denver concerts + ⭐ artist matching
│
├── data/                            # Your entire life, locally stored
│   ├── warehouse/ons.duckdb         # DuckDB warehouse (gitignored, obviously)
│   ├── habits/habits_log.jsonl      # Habit log (gitignored)
│   ├── calendar/
│   ├── spotify/
│   ├── sugarwod/
│   ├── shows/
│   └── manual/goal_progress.csv
│
├── run_pipelines.py                 # Run DLT pipelines directly
└── secrets/                         # OAuth tokens (gitignored, not that kind)
```

---

## Daily Workflow

Runs automatically at 9am via launchd. You don't have to do anything. The system knows.

```bash
# Manual override if you're impatient
source .venv/bin/activate
python scripts/daily_sync.py
streamlit run app/Home.py
```

**Surgical strikes:**
```bash
python scripts/daily_sync.py --only pipelines    # DLT only
python scripts/daily_sync.py --only dbt          # sync + dbt only
python scripts/daily_sync.py --skip spotify      # skip a step
python scripts/daily_sync.py --only aeg_events ticketmaster shows_metrics
```

---

## Setup

### Prerequisites
- Python 3.12+
- [uv](https://github.com/astral-sh/uv)
- A concerning amount of self-interest

### Install
```bash
git clone https://github.com/cnvertbleweathr/ons-2026.git
cd ons-2026
uv sync
source .venv/bin/activate
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
| `OPENAI_API_KEY` | [OpenAI](https://platform.openai.com/api-keys) |
| `TICKETMASTER_API_KEY` | [Ticketmaster Developer](https://developer.ticketmaster.com) |

### First Run
```bash
# One-time OAuth dances
python scripts/strava_auth.py
python scripts/calendar_export.py  # opens browser

# Create directories
mkdir -p data/warehouse data/habits

# Boot the system
python scripts/daily_sync.py

# Open the dashboard and contemplate your life choices
streamlit run app/Home.py
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

---

## Data Sources

| Source | Method | Cadence | What it tracks |
|---|---|---|---|
| Strava | DLT + OAuth | Daily | Running miles, pace, weekly volume |
| Hardcover | DLT + GraphQL | Daily | Books read, fiction vs nonfiction |
| Habits | Streamlit UI | Daily | Meditation, pushups, reading pages |
| Google Calendar | OAuth API | Daily | Date nights, events, birthdays you shouldn't forget |
| SugarWOD | CSV export | Manual | CrossFit classes, PRs, lift progressions |
| Spotify | JSON export + API | Daily | Streaming stats, Daily 10 playlist + AI cover art |
| AEG / Ticketmaster | Public API | Daily | Upcoming Denver concerts |
| streamed.pk | Public API | Daily | Live sports streams, AI-ranked top 5 |

---

## Dashboard Pages

| Page | What it shows |
|---|---|
| 🧭 **Home** | AI daily digest, sports streams, ⭐ artist show alerts, calendar, goals scoreboard |
| ✅ **Habits** | Did you meditate? Do pushups? Read? The data knows. |
| 💪 **Fitness** | Strava running metrics + weekly chart, CrossFit lift progressions + PR log |
| 📚 **Reading** | Hardcover fiction/nonfiction progress, book list with classification |
| 🎯 **Goals** | What you said you'd do vs what you actually did |
| 🎵 **Music** | Spotify streaming stats, top artists/tracks, listening heatmap, Daily 10 embed |
| 🎸 **Shows** | Upcoming Denver concerts, ⭐ Tewnidge/Deeds artist matching, ticket links |

---

## Design Principles

**Separation of concerns** — intent (`goals/2026.yaml`), facts (`data/`), and logic (`scripts/`, `dbt/`) are explicitly separated. What you want to do and what you actually do live in different tables for a reason.

**Automation over willpower** — runs at 9am daily via launchd. Willpower is finite. Cron jobs are not.

**DuckDB as the hub** — all sources land in DuckDB. dbt builds clean marts on top. The dashboard queries marts only. No spaghetti.

**DLT for extraction** — schema inference, merge semantics, and load state handled by DLT. No bespoke fetch scripts held together with prayers.

**AI as co-processor** — used for bounded, testable tasks: daily digest, sports stream ranking, playlist cover art. Never for core data logic. The AI assists. The data tells the truth.
