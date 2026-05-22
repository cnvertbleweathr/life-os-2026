# Life OS 2026

**Life OS 2026** is a personal analytics platform that treats life as a system — observable, measurable, automatable, and continuously improvable.

It uses the same principles that power modern data stacks: declarative intent, automated ingestion, transformation pipelines, and a dashboard for reflection and decision-making.

---

## Architecture

```
External Sources → DLT Pipelines → DuckDB → dbt → Streamlit Dashboard
                                     ↑
                              Local Inputs
                         (habits, SugarWOD CSV)
```

### Full Data Flow

```mermaid
flowchart TD
    subgraph Sources["📡 Data Sources"]
        STRAVA[Strava API]
        HARDCOVER[Hardcover API]
        SPOTIFY[Spotify API]
        GCAL[Google Calendar API]
        SUGARWOD[SugarWOD CSV]
        HABITS[Habit Checkboxes\nStreamlit UI]
        AEG[AEG / Ticketmaster API]
    end

    subgraph Pipelines["⚙️ Ingestion — DLT Pipelines"]
        P1[strava_pipeline.py]
        P2[hardcover_pipeline.py]
        P3[habits_pipeline.py]
        P4[calendar_export.py]
        P5[import_sugarwod_csv.py]
        P6[spotify_ingest_streaming.py]
        P7[aeg_events_fetch.py\nticketmaster_fetch_denver.py]
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
        HOME[🧭 Home\nDaily Digest + AI Summary]
        HABITS_PAGE[✅ Habits\nCheckboxes + Streaks]
        FITNESS[💪 Fitness\nRunning + CrossFit]
        READING[📚 Reading\nFiction + Nonfiction]
        GOALS[🎯 Goals\nProgress by Domain]
        MUSIC[🎵 Music\nSpotify Daily 10]
    end

    STRAVA --> P1
    HARDCOVER --> P2
    HABITS --> P3
    GCAL --> P4
    SUGARWOD --> P5
    SPOTIFY --> P6
    AEG --> P7

    P1 --> S1
    P2 --> S2
    P3 --> S3
    P4 --> S4
    P5 --> S5
    P6 --> S5
    P7 --> S5

    S1 & S2 & S3 & S4 & S5 --> STG
    STG --> MART

    MART --> HOME
    MART --> HABITS_PAGE
    MART --> FITNESS
    MART --> READING
    MART --> GOALS
    MART --> MUSIC
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
        SGP[stg_goals__progress\nclean progress values]
        SHL[stg_habits__log\nparse dates + year/month]
        SHS[stg_habits__summary\ncompletion rates]
    end

    subgraph marts["Mart Layer"]
        MHP[mart_habit_performance\ndaily pivot + completion %]
        MHS[mart_habit_streaks\ncurrent + longest streak]
        MGD[mart_goal_detail\ngoal targets with types]
        MGP[mart_goal_progress\njoin targets + actuals]
        MHC[mart_lifeos_healthcheck\nsystem status]
    end

    RG --> SGA
    RGP --> SGP
    SGA --> MGD
    SGP --> MGP
    MGD --> MGP
    SHL --> MHP
    SHL --> MHS
    SHS --> MGP
```

---

### Daily Sync Orchestration

```mermaid
sequenceDiagram
    participant U as You
    participant DS as daily_sync.py
    participant DLT as DLT Pipelines
    participant DB as DuckDB
    participant DBT as dbt
    participant STR as Streamlit

    U->>DS: python scripts/daily_sync.py
    DS->>DLT: strava_pipeline.py
    DLT->>DB: upsert strava.activities
    DS->>DLT: hardcover_pipeline.py
    DLT->>DB: upsert hardcover.books_read
    DS->>DLT: habits_pipeline.py
    DLT->>DB: upsert habits.habit_log
    DS->>DS: calendar_export.py
    DS->>DS: shows / spotify steps
    DS->>DS: sync_goal_progress.py
    DS->>DBT: dbt run
    DBT->>DB: build staging + mart models
    U->>STR: streamlit run app/Home.py
    STR->>DB: query mart_*
    STR->>U: Daily digest + dashboards
```

---

## Repository Structure

```
life-os-2026/
├── goals/
│   └── 2026.yaml              # Declarative intent — all goals defined here
│
├── pipelines/                 # DLT ingestion pipelines
│   ├── strava_pipeline.py     # Strava API → DuckDB
│   ├── hardcover_pipeline.py  # Hardcover API → DuckDB
│   └── habits_pipeline.py     # Local JSONL → DuckDB
│
├── scripts/                   # Orchestration + auxiliary scripts
│   ├── daily_sync.py          # Daily orchestrator — run this every morning
│   ├── sync_goal_progress.py  # Pull actuals from DuckDB → goal_progress.csv
│   ├── calendar_export.py     # Google Calendar → CSV
│   ├── calendar_metrics.py    # Date night tracking
│   ├── import_sugarwod_csv.py # SugarWOD CSV → DuckDB
│   ├── spotify_*.py           # Spotify ingestion + Daily 10 playlist
│   ├── aeg_events_fetch.py    # AEG concert data
│   └── ticketmaster_fetch_denver.py
│
├── dbt/                       # Transformation layer
│   ├── models/
│   │   ├── staging/           # stg_* — clean + type raw sources
│   │   └── marts/             # mart_* — business logic + goal progress
│   └── profiles/
│
├── app/                       # Streamlit dashboard
│   ├── Home.py                # Entry point — daily digest + AI summary
│   └── pages/
│       ├── 1_Habits.py        # Checkbox logging + streaks + history
│       ├── 2_Fitness.py       # Running + CrossFit lift progressions
│       ├── 3_Reading.py       # Hardcover fiction + nonfiction
│       ├── 4_Goals.py         # Goal progress by domain
│       └── 5_Music.py         # Spotify Daily 10 + streaming stats
│
├── data/                      # Local data (gitignored except examples)
│   ├── warehouse/lifeos.duckdb
│   ├── habits/habits_log.jsonl
│   ├── calendar/
│   ├── spotify/
│   ├── sugarwod/
│   └── manual/goal_progress.csv
│
├── run_pipelines.py           # Run DLT pipelines directly
└── secrets/                   # OAuth tokens (gitignored)
```

---

## Daily Workflow

```bash
# 1. Activate environment
source .venv/bin/activate

# 2. Run everything
python scripts/daily_sync.py

# 3. Open dashboard
streamlit run app/Home.py
```

**Or run specific steps:**
```bash
python scripts/daily_sync.py --only pipelines    # DLT only
python scripts/daily_sync.py --only dbt          # sync + dbt only
python scripts/daily_sync.py --skip spotify      # skip a step
```

---

## Setup

### Prerequisites
- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### Install
```bash
git clone https://github.com/cnvertbleweathr/life-os-2026.git
cd life-os-2026
uv sync
source .venv/bin/activate
```

### Configure
Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Required keys:
| Key | Source |
|---|---|
| `STRAVA_CLIENT_ID` / `STRAVA_CLIENT_SECRET` | [Strava API](https://www.strava.com/settings/api) |
| `HARDCOVER_TOKEN` | [Hardcover Settings](https://hardcover.app/account/api) |
| `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` | [Spotify Developer](https://developer.spotify.com/dashboard) |
| `OPENAI_API_KEY` | [OpenAI](https://platform.openai.com/api-keys) |
| `TICKETMASTER_API_KEY` | [Ticketmaster Developer](https://developer.ticketmaster.com) |

### First Run
```bash
# Authenticate Strava (one-time OAuth)
python scripts/strava_auth.py

# Set up Google Calendar credentials
# → Download OAuth JSON from Google Cloud Console
# → Save to secrets/google_calendar_credentials.json
python scripts/calendar_export.py  # opens browser for OAuth

# Create warehouse directory
mkdir -p data/warehouse data/habits

# Run everything
python scripts/daily_sync.py
```

---

## Data Sources

| Source | Method | Cadence | What it tracks |
|---|---|---|---|
| Strava | DLT + OAuth | Daily | Running miles, pace, weekly volume |
| Hardcover | DLT + GraphQL | Daily | Books read, fiction vs nonfiction |
| Habits | Streamlit UI | Daily | Meditation, pushups, reading pages |
| Google Calendar | OAuth API | Daily | Date nights, events, birthdays |
| SugarWOD | CSV export | Manual | CrossFit classes, PRs, lift weights |
| Spotify | JSON export | On receipt | Streaming minutes, top artists/tracks |
| AEG / Ticketmaster | Public API | Daily | Upcoming Denver concerts |

---

## Design Principles

**Separation of concerns** — intent (`goals/2026.yaml`), facts (`data/`), and logic (`scripts/`, `dbt/`) are explicitly separated. Goals evolve without rewriting logic.

**Automation over willpower** — if a metric matters, it's automatically ingested, computed, and surfaced. Manual effort is treated as technical debt.

**DuckDB as the hub** — all sources land in DuckDB. dbt builds clean marts on top. The dashboard queries marts only.

**Append-only history** — raw data is never mutated. DLT handles merge/replace semantics at the pipeline level.

**AI as co-processor** — used for bounded, testable tasks: daily digest generation, playlist cover art. Never for core data logic.
