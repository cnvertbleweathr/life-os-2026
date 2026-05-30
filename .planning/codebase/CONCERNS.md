# Concerns & Technical Debt
_Last updated: 2026-05-29_

## Summary
The codebase is functional and well-structured for a personal life-OS, but carries several reliability risks around OAuth token expiry, hardcoded year values that will break at year-end, and three fully-built insight pipeline scripts that are dormant and not wired into the daily sync or dashboard. Security posture is acceptable for a personal project but has a few rough edges.

## High Severity

### `streamed.pk` Dependency (Sports data)
- **Location:** `scripts/` (sports/fixture fetching)
- **Issue:** `streamed.pk` is an unofficial, piracy-adjacent sports streaming API with no SLA, no documented stability guarantees, and a history of domain changes. It can vanish or change without notice, silently breaking sports data in the dashboard.
- **Risk:** Data loss, silent failures on sports page.

### Spotify OAuth `open_browser=True` — Breaks Headless launchd Sync
- **Location:** Spotify auth flow in scripts
- **Issue:** When the Spotify OAuth token expires, the auth flow calls `open_browser=True`, which opens a browser window. In a headless launchd daily sync context (no display), this fails silently or errors out with no useful log message.
- **Risk:** Daily sync silently skips Spotify data after token expiry; no alert to user.

### Insight Pipeline Scripts Fully Built but Not Wired In
- **Location:** `scripts/generate_insights.py`, `scripts/weekly_reflection.py`, `scripts/export_for_insights.py`
- **Issue:** These scripts are complete and functional but are explicitly noted as "dormant — not wired into sync or dashboard yet" (per git commit message). They represent significant completed work with zero value delivered.
- **Risk:** Wasted work; the longer they sit unwired, the more likely they drift out of sync with the data schema.

---

## Medium Severity

### Hardcoded `2026` Year in 10+ Locations
- **Location:** `app/pages/`, `scripts/`, SQL queries, file paths
- **Issue:** The year `2026` is hardcoded throughout the codebase — in Streamlit page queries, file path templates, dbt SQL, and data lookups. At year-end this will silently return empty results rather than erroring visibly.
- **Risk:** All year-scoped data goes dark on Jan 1, 2027 without obvious error.

### Running Goal Hardcoded in `strava_pipeline.py`
- **Location:** `scripts/strava_pipeline.py`
- **Issue:** The annual running goal (`350.0` miles) is hardcoded in the script rather than read from `goals/2026.yaml`, which exists for this purpose.
- **Risk:** Inconsistency; changing the goal requires editing source code.

### Spotify Playlist IDs Hardcoded in Source
- **Location:** `scripts/sync_playlist_artists.py`
- **Issue:** Two Spotify playlist IDs are hardcoded in source code instead of being read from environment variables or config.
- **Risk:** Breaks if playlists are recreated; IDs in source code is a minor hygiene issue.

### Google Calendar OAuth Token Refresh Not Implemented
- **Location:** Google Calendar auth flow
- **Issue:** Token refresh for Google Calendar OAuth is not implemented. After the initial token expires, the headless daily sync will fail.
- **Risk:** Calendar data silently disappears from the dashboard after token expiry.

### `fitness_metrics.py` Not Wired into `daily_sync.py`
- **Location:** `scripts/fitness_metrics.py`, `scripts/daily_sync.py`
- **Issue:** The fitness metrics pipeline script exists but is not called from the daily sync orchestrator.
- **Risk:** Fitness metrics data is stale unless run manually.

### `daily10_audit.csv` Referenced but Never Written
- **Location:** Music page in Streamlit app
- **Issue:** The Music page references `daily10_audit.csv` but no script writes this file.
- **Risk:** Music page feature is broken/missing data silently.

---

## Low Severity

### Personal Email Hardcoded in Wikimedia User-Agent Header
- **Location:** Wikimedia API calls
- **Issue:** Personal email address embedded in HTTP User-Agent string in source code.
- **Risk:** Minor privacy/hygiene issue; email appears in server logs.

### Pixela Leftovers in `.env.example`
- **Location:** `.env.example`
- **Issue:** Pixela (habit tracking service) was removed in May 2026 but its env var entries remain in `.env.example`.
- **Risk:** Confusing for future reference; no functional impact.

### `CHECKPOINT.md` References Deleted Scripts
- **Location:** `CHECKPOINT.md`
- **Issue:** The checkpoint file references scripts that have been deleted, presenting a stale picture of the system.
- **Risk:** Misleading documentation.

### Debug `print` Statements in `spotify_daily10_playlist.py`
- **Location:** `scripts/spotify_daily10_playlist.py`
- **Issue:** Debug print statements left in production script.
- **Risk:** Noisy logs; minor.

### `redis` in `requirements.txt` but Never Imported
- **Location:** `requirements.txt`
- **Issue:** `redis` package listed as a dependency but never imported anywhere in the codebase.
- **Risk:** Unnecessary dependency; minor install overhead.

### Tewnidge-Skip Logic Comment Without Implementation
- **Location:** Source (Spotify or music scripts)
- **Issue:** A "Bucket B Tewnidge-skip" comment exists but the actual skip logic is not implemented.
- **Risk:** Feature described in comment does not work.

### Orphan Utility Scripts Without Docstrings
- **Location:** Various `scripts/`
- **Issue:** Several utility scripts have no module-level docstring explaining their purpose or how to invoke them.
- **Risk:** Maintenance friction.

---

## Opportunities

- **Wire insights pipeline:** Connect `generate_insights.py`, `weekly_reflection.py`, and `export_for_insights.py` into `daily_sync.py` and add an Insights page to the Streamlit dashboard.
- **Year-agnostic pages:** Introduce a shared `CURRENT_YEAR` constant (or derive from `datetime.now().year`) and replace all hardcoded `2026` references.
- **Centralize goal loading:** Create a shared `load_goals(year)` utility so all scripts/pages read from `goals/{year}.yaml` consistently.
- **Add retry logic:** Strava and Hardcover API calls have no retry on transient failures; a simple exponential backoff wrapper would improve reliability.
- **Sync failure notification:** Add a sentinel file or Streamlit home page banner when `daily_sync.py` fails, so failures are visible without checking logs.
