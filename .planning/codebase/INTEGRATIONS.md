# External Integrations
_Last updated: 2026-05-29_

## Summary

Operating Narcisystem 2026 integrates with eight external data sources plus two AI providers. All integrations are polling-based (no webhooks). Authentication uses a mix of OAuth 2.0 (Strava, Google Calendar, Spotify) and static API tokens (Hardcover, Ticketmaster, OpenAI). Credentials live in `.env` and OAuth token caches live in `secrets/`.

---

## Strava API

**Purpose:** Daily running activity ingestion (miles, pace, elevation, heart rate)

**Auth:** OAuth 2.0 with offline refresh token
- One-time setup: `python scripts/strava_auth.py` — opens browser, runs local HTTP callback server on `localhost:8000`
- Tokens persisted to: `data/running/raw/strava_tokens.json`
- Auto-refresh: `pipelines/strava_pipeline.py` calls `_refresh_if_needed()` before every run

**Env vars:**
- `STRAVA_CLIENT_ID`
- `STRAVA_CLIENT_SECRET`
- `STRAVA_REDIRECT_URI` (default: `http://localhost:8000/callback`)

**SDK/Client:** Raw `requests` — no official Strava SDK

**Endpoints used:**
- `POST https://www.strava.com/oauth/token` — token refresh
- `GET https://www.strava.com/api/v3/athlete/activities` — paginated activity list (200/page)

**Pipeline:** `pipelines/strava_pipeline.py` → DLT → `strava.activities` and `strava.running_summary` tables in DuckDB

---

## Hardcover API (GraphQL)

**Purpose:** Book tracking — reads books, fiction/nonfiction classification, reading progress toward annual goals

**Auth:** Static bearer token
- Token stored in `.env` as `HARDCOVER_TOKEN`
- Sent as `authorization` header (not `Bearer` prefixed — raw token value)

**Env vars:**
- `HARDCOVER_TOKEN`
- `HARDCOVER_API_URL` (default: `https://api.hardcover.app/v1/graphql`)

**SDK/Client:** Raw `requests` with hand-written GraphQL queries in `pipelines/hardcover_pipeline.py`

**Queries used:**
- `Me` — resolve authenticated user ID
- `UserBooksRead` — paginated list of books with status 3 (read), tags, and author data

**Pipeline:** `pipelines/hardcover_pipeline.py` → DLT → `hardcover.books_read` and `hardcover.reading_summary` tables in DuckDB

---

## Spotify Web API

**Purpose:** Three distinct use cases:
1. Daily 10 playlist generation — create/replace a dated playlist from listening history + Tewnidge discovery
2. Playlist artist sync — extract artists from "Tewnidge" and "Deeds" playlists for show cross-referencing
3. Playlist cover art upload — AI-generated impressionist JPEG uploaded as playlist cover image

**Auth:** OAuth 2.0 via `spotipy` with PKCE/redirect flow
- Token cache: `secrets/spotify_token_cache.json` (used by `spotify_daily10_playlist.py`) and `secrets/.spotify_cache` (used by `sync_playlist_artists.py`)
- Also `.spotify_token_cache` in project root (used by `spotify_daily10_decorate.py`)

**Env vars:**
- `SPOTIFY_CLIENT_ID`
- `SPOTIFY_CLIENT_SECRET`
- `SPOTIFY_REDIRECT_URI` (default: `http://localhost:8888/callback`)
- `SPOTIFY_TEWNIDGE_PLAYLIST_ID` (hardcoded fallback: `7hxa1w4AzUjm6xgvU3Zf3x`)

**SDK/Client:** `spotipy` 2.26.0 with `SpotifyOAuth` auth manager

**Scopes used:**
- `playlist-modify-private`, `playlist-modify-public` — create/update playlists
- `playlist-read-private`, `playlist-read-collaborative` — read playlist tracks
- `ugc-image-upload` — upload cover art

**Scripts:**
- `scripts/spotify_daily10_playlist.py` — reads `data/spotify/processed/streams_clean.csv`, builds 10-track playlist
- `scripts/spotify_daily10_decorate.py` — uploads AI cover image + updates playlist description
- `scripts/sync_playlist_artists.py` — extracts artists from Tewnidge (`7hxa1w4AzUjm6xgvU3Zf3x`) and Deeds (`6GP6ERcYJArZ7WWaC2g0Xv`) playlists

**Spotify streaming history (offline):**
- Raw JSON export files placed manually at `data/spotify/raw/streaming_history/`
- Processed by `scripts/spotify_ingest_streaming.py` → `data/spotify/processed/streams_clean.csv`
- Stats computed by `scripts/spotify_metrics.py` → `data/spotify/metrics/`

---

## Google Calendar API

**Purpose:** Export calendar events for home-page digest display and date-night tracking

**Auth:** OAuth 2.0 via `google-auth-oauthlib` InstalledAppFlow
- One-time setup: `python scripts/calendar_export.py` — opens browser
- Credentials file: `secrets/google_calendar_credentials.json`
- Token cache: `secrets/google_calendar_token.json`
- Scope: `https://www.googleapis.com/auth/calendar.readonly` (read-only)

**Env vars:**
- `GOOGLE_CALENDAR_CREDENTIALS` (default: `secrets/google_calendar_credentials.json`)
- `GOOGLE_CALENDAR_TOKEN` (default: `secrets/google_calendar_token.json`)
- `GOOGLE_CALENDAR_ID` (default: `primary`)

**SDK/Client:** `google-api-python-client` 2.196.0 with `googleapiclient.discovery.build("calendar", "v3")`

**Endpoints used:**
- `Events.list` with `timeMin`/`timeMax` pagination — fetches all events for a given year

**Output:** `data/calendar/raw/events_{year}_{date}.json` (raw) and `data/calendar/processed/events_clean_{year}.csv` (processed)

**Scripts:** `scripts/calendar_export.py` (export) and `scripts/calendar_metrics.py` (date-night tracking)

---

## OpenAI API

**Purpose:** Three bounded AI tasks:
1. **Daily digest** (`app/Home.py`) — calendar summarization via chat completions
2. **Sports stream ranking** (`scripts/fetch_streams.py`) — GPT-4o selects top 5 nationally prominent games from streamed.pk results
3. **Playlist cover art** (`scripts/spotify_daily10_decorate.py`) — DALL-E 3 generates impressionist painting from a Wikipedia "On This Day" event; image uploaded to Spotify

**Auth:** Static API key

**Env vars:**
- `OPENAI_API_KEY`
- `OPENAI_IMAGE_MODEL` (default: `dall-e-3`)
- `OPENAI_IMAGE_SIZE` (default: `1024x1024`)

**SDK/Client:** Raw `requests` — no `openai` Python package; calls REST endpoints directly

**Endpoints used:**
- `POST https://api.openai.com/v1/chat/completions` — model `gpt-4o`, used in Home.py, fetch_streams.py, generate_insights.py, show_radar.py, weekly_reflection.py
- `POST https://api.openai.com/v1/images/generations` — model `dall-e-3` (or env override), used in spotify_daily10_decorate.py

**Note:** `generate_insights.py` has a function named `call_claude()` but it calls the OpenAI API — this is a naming artifact, not an Anthropic integration.

---

## Ticketmaster Discovery API

**Purpose:** Fetch upcoming music events within 50 miles of Denver, CO

**Auth:** Static API key passed as query parameter

**Env vars:**
- `TICKETMASTER_API_KEY`
- `TM_CITY` (default: `Denver`)
- `TM_STATE` (default: `CO`)
- `TM_COUNTRY` (default: `US`)
- `TM_RADIUS_MILES` (default: `50`)
- `TM_CLASSIFICATION` (default: `music`)
- `TM_SIZE` (default: `200`)

**SDK/Client:** Raw `requests`

**Endpoint:** `GET https://app.ticketmaster.com/discovery/v2/events.json` — paginated, polite 350ms delay between pages, safety cap at 50 pages

**Output:** Raw JSON to `data/shows/raw/ticketmaster/`, processed CSV to `data/shows/processed/denver_events_ticketmaster.csv`

**Script:** `scripts/ticketmaster_fetch_denver.py`

---

## AEG / AXS Venue Feeds

**Purpose:** Fetch upcoming events from specific Denver AEG-managed venues (Ball Arena, Red Rocks, etc.) via public Azure Blob Storage JSON feeds

**Auth:** None — public JSON endpoints

**Env vars:**
- `AEG_EVENTS_URLS` — pipe-delimited list of JSON feed URLs (5 venue IDs configured in `.env.example`)
- `AEG_VENUES` — optional pipe-delimited venue name filter

**SDK/Client:** Raw `requests`

**Data source:** `https://aegwebprod.blob.core.windows.net/json/events/{venue_id}/events.json` — public, no auth

**Output:** Raw JSON to `data/shows/raw/aeg/`, processed CSV to `data/shows/processed/denver_events_upcoming.csv`

**Script:** `scripts/aeg_events_fetch.py`

---

## streamed.pk API

**Purpose:** Fetch today's live and upcoming sports streams; GPT-4o ranks top 5 nationally prominent games

**Auth:** None — public API

**Env vars:** None required

**SDK/Client:** Raw `requests` with `User-Agent: ons/1.0`

**Endpoints used:**
- `GET https://streamed.pk/api/matches/all-today` — all matches today
- `GET https://streamed.pk/api/matches/live` — currently live matches
- Watch links: `https://streamed.pk/watch/{match_id}`

**Output:** `data/streams/today.json`

**Script:** `scripts/fetch_streams.py`

---

## Wikipedia / Wikimedia REST API

**Purpose:** "On This Day" historical events used as inspiration for Spotify playlist cover art prompts

**Auth:** None — public API

**SDK/Client:** Raw `requests` with `User-Agent: ons-2026/1.0 (contact: karey.graham@gmail.com)`

**Endpoint:** `GET https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{mm}/{dd}`

**Script:** `scripts/spotify_daily10_decorate.py` — called inline during playlist decoration

---

## SugarWOD (Manual CSV Export)

**Purpose:** CrossFit class attendance, lift progressions, and PRs

**Auth:** None — manual export process

**Method:** User exports CSV from SugarWOD app (Settings → Export Data), then runs `python scripts/import_sugarwod_csv.py --input /path/to/workouts.csv`

**Output:** Loaded into DuckDB `raw.*` schema

---

## Data Storage

**Primary store:** DuckDB at `data/warehouse/ons.duckdb` — gitignored, local only

**File-based intermediates:**
- `data/habits/habits_log.jsonl` — habit log written by Streamlit UI; source for habits DLT pipeline
- `data/calendar/processed/events_clean_{year}.csv` — calendar events for dashboard
- `data/spotify/processed/streams_clean.csv` — processed Spotify streaming history
- `data/shows/processed/` — merged AEG + Ticketmaster event CSVs
- `data/streams/today.json` — today's sports streams
- `data/spotify/processed/my_artists.json` — playlist artist roster
- `data/shows/my_artist_shows.json` — artist-matched upcoming shows (alerts)
- `goals/2026.yaml` — declarative goal definitions (committed)
- `data/manual/goal_progress.csv` — manual goal progress overrides

**Secrets / OAuth tokens (gitignored):**
- `secrets/google_calendar_credentials.json`
- `secrets/google_calendar_token.json`
- `secrets/spotify_token_cache.json`
- `secrets/.spotify_cache`
- `data/running/raw/strava_tokens.json`

---

## Environment Variables Reference

All required variables documented in `.env.example`:

| Variable | Service | Notes |
|---|---|---|
| `STRAVA_CLIENT_ID` | Strava | OAuth app client ID |
| `STRAVA_CLIENT_SECRET` | Strava | OAuth app client secret |
| `STRAVA_REDIRECT_URI` | Strava | Default: `http://localhost:8000/callback` |
| `HARDCOVER_TOKEN` | Hardcover | Static bearer token |
| `HARDCOVER_API_URL` | Hardcover | Default: `https://api.hardcover.app/v1/graphql` |
| `GOOGLE_CALENDAR_CREDENTIALS` | Google Calendar | Path to credentials JSON |
| `GOOGLE_CALENDAR_TOKEN` | Google Calendar | Path to token cache JSON |
| `GOOGLE_CALENDAR_ID` | Google Calendar | Default: `primary` |
| `SPOTIFY_CLIENT_ID` | Spotify | OAuth app client ID |
| `SPOTIFY_CLIENT_SECRET` | Spotify | OAuth app client secret |
| `SPOTIFY_REDIRECT_URI` | Spotify | Default: `http://localhost:8888/callback` |
| `SPOTIFY_TEWNIDGE_PLAYLIST_ID` | Spotify | Playlist for Daily 10 discovery bucket |
| `OPENAI_API_KEY` | OpenAI | Used for digest, stream ranking, image generation |
| `OPENAI_IMAGE_MODEL` | OpenAI | Default: `dall-e-3` |
| `OPENAI_IMAGE_SIZE` | OpenAI | Default: `1024x1024` |
| `TICKETMASTER_API_KEY` | Ticketmaster | Discovery API key |
| `TM_CITY` / `TM_STATE` / `TM_COUNTRY` | Ticketmaster | Geo filter (default: Denver, CO, US) |
| `TM_RADIUS_MILES` | Ticketmaster | Default: `50` |
| `TM_CLASSIFICATION` | Ticketmaster | Default: `music` |
| `TM_SIZE` | Ticketmaster | Results per page, default: `200` |
| `AEG_EVENTS_URLS` | AEG | Pipe-delimited venue JSON feed URLs |
| `PIXELA_USERNAME` / `PIXELA_TOKEN` | Pixela | In `.env.example` but **not used** — replaced by DuckDB habits pipeline |

---

## Webhooks and Event Streams

**None.** All integrations are outbound polling. No incoming webhooks are configured or handled.
