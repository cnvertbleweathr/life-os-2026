# ONS Product Roadmap

Last updated: 2026-06-07

---

## Status Legend
- 🟢 **Done** — shipped and working
- 🟡 **In Progress** — partially built or needs wiring
- 🔵 **Planned** — scoped, not started
- ⚪ **Idea** — not yet scoped

---

## UI Rebuild — Next.js + FastAPI

### Decision
Streamlit is being replaced. It is the wrong tool for this use case — layout constraints,
no real routing, full-page reruns on interaction, and no mobile support. The rebuild
targets a proper web app accessible from anywhere.

### Architecture
```
Mac mini
├── FastAPI          api/           Python — DuckDB query layer
│   └── routers/
│       ├── home.py                /api/home
│       ├── fitness.py             /api/fitness
│       ├── music.py               /api/music
│       ├── habits.py              /api/habits
│       ├── reading.py             /api/reading
│       ├── goals.py               /api/goals
│       ├── shows.py               /api/shows
│       ├── sports.py              /api/sports
│       └── cfb.py                 /api/cfb/picks, /api/cfb/backtest
└── Next.js          web/           TypeScript — UI layer
    └── app/
        ├── page.tsx               Home
        ├── habits/page.tsx
        ├── fitness/page.tsx
        ├── reading/page.tsx
        ├── goals/page.tsx
        ├── music/page.tsx
        ├── shows/page.tsx
        ├── sports/page.tsx
        └── cfb/page.tsx

Remote access: Tailscale or Cloudflare Tunnel (no port forwarding required)
Domain: capuchin.cyou (registered, unused)
```

### Design System
- Dark sidebar (#1a2420) with ONS logo mark and forest green accent (#4a7c5f)
- White content area — flat, minimal, no decorative effects
- Bento grid layout for dashboard — stat cards, calendar, picks, music, WOD
- Space Grotesk font carried over from current theme
- Fully responsive — works on phone via Tailscale

### Roadmap

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | Design concept approved | Mockup reviewed — bento grid Home layout |
| 🔵 | FastAPI layer — all 8 route modules | Port DuckDB queries from Streamlit pages |
| 🔵 | Next.js scaffold — routing + layout + sidebar | App Router, Tailwind |
| 🔵 | Home page | Calendar, stat cards, Daily 10, WOD, picks strip |
| 🔵 | Habits page | Today checklist, streaks, YTD heatmap |
| 🔵 | Fitness page | Running stats, lift progressions, WOD log |
| 🔵 | Reading page | Currently reading, books read 2026 |
| 🔵 | Goals page | Progress bars, pace tracking, domain grouping |
| 🔵 | Music page | Daily 10 embed, streaming stats, news |
| 🔵 | Shows page | Denver concerts, artist matching, venue map |
| 🔵 | Sports page | Streams, team news, Degenerates Corner |
| 🔵 | CFB Betting page | Edge matrix, team intel, matchup, picks |
| 🔵 | Remote access setup | Tailscale or Cloudflare Tunnel |
| 🔵 | Point capuchin.cyou | DNS to production app |
| 🔵 | Decommission Streamlit | Remove app/ directory after parity confirmed |

### Build Order
1. FastAPI layer first — all endpoints, tested against DuckDB directly
2. Home page — highest value, establishes design system in code
3. CFB Betting page — most complex, benefits most from proper UI
4. Remaining pages in order of daily use

---

## CFB Betting Model — Current State

### Validation Results (walk-forward, no lookahead bias)
- **318 bets · 224-94 · 70.4% win rate · +34.5% ROI · 4/4 seasons profitable**
- Tested: 2022-2025 (walk-forward tiers, one row per game, prior-season PPA)
- Weeks 1-4: +39.5% ROI (strongest window — prior PPA freshest)
- Model score monotonic: 70-79 → +38%, 80-89 → +33%, 90-99 → +30%

### Validated Signal Stack
| Signal | ΔROI when removed | Per-season consistency |
|--------|------------------|----------------------|
| Success rate interaction | -16.0% | 4/4 seasons |
| Team tier penalties | -7.2% | 4/4 seasons |
| Coach change filter | -3.5% | 4/4 seasons |
| Conference filter | -1.7% | 3/4 seasons |
| Spread range | -5.1% | 3/4 seasons |
| Recruiting/talent | (see below) | 4/4 seasons |
| Returning production | -1.4% | 4/4 seasons |
| SP+ alignment | 0.0% | DISABLED |
| Defensive havoc | 0.0% | DISABLED |
| Travel distance | display only | display only |
| Coach H2H | display only | display only |

### Architecture
- `scripts/backtest_walk_forward.py` — canonical scorer (`score_game()`)
- `scripts/generate_picks.py` — imports `score_game()` directly, no divergence
- `scripts/backtest_ablation.py` — per-season signal ablation
- `dbt/models/marts/mart_cfbd_recruiting_talent.sql` — 4-year weighted model
- `dbt/models/marts/mart_cfbd_travel_distance.sql` — haversine via cfbd.weather
- `dbt/models/marts/mart_cfbd_coach_matchups.sql` — H2H record (display only)
- `data/bets/todays_picks.json` — weekly output consumed by dashboard

### Season Workflow (August–January)
- **Sunday**: `track_lines.py` — opening lines
- **Mon–Fri**: `track_lines.py` — daily movement snapshots
- **Wed/Thu**: `track_news_signals.py` — injury/weather signals for movers
- **Tue/Wed**: `generate_picks.py` — pick generation
- **Thursday**: `generate_picks_report.py` — markdown report to `data/bets/`
- **Saturday**: `track_lines.py` — closing lines

### Roadmap

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | 14-signal model built and validated | All signals empirically calibrated |
| 🟢 | Walk-forward backtester (v3) | Prior-season SP+, 2+ season tiers, one row/game |
| 🟢 | Per-season ablation test | Identifies consistent vs era-specific signals |
| 🟢 | generate_picks.py uses score_game() | Single scorer, no divergence from backtest |
| 🟢 | SP+ and havoc disabled | 0% ΔROI all 4 seasons — removed from scoring |
| 🟢 | Human-readable edge strings | Pick output uses plain English labels |
| 🟢 | Weekly picks report (Thursday) | Markdown to data/bets/ |
| 🔵 | Re-run ablation at 2026 Week 4 | After 4 weeks of real data, recalibrate weights |
| 🔵 | Model score calibration audit | 70-79 bucket slightly outperforms 90-99 — investigate |
| 🔵 | Line movement signal (in-season) | track_lines.py → mart_cfbd_line_movement → score_game |
| 🔵 | News signal integration | track_news_signals.py → confidence adjustment |
| 🔵 | 2026 live performance tracker | Weekly P&L vs model_score, rolling ROI chart |
| 🔵 | Push alert for qualifying bets | ntfy.sh — Thursday report notification |
| 🔵 | Game Scout — weekly matchup browser | August, when 2026 schedule available |
| 🔵 | Refresh team profiles at 2026 Week 4 | `cfb_build_team_profiles.py --min-games 8` |
| 🔵 | Fix 2026 hardcoded in 10+ locations | Use `datetime.now().year` or shared constant |
| 🔵 | NFL betting pipeline | The Odds API — same dbt mart pattern |
| 🔵 | MLB betting pipeline | The Odds API + Statcast for advanced metrics |
| ⚪ | Injury proxy via player usage drops | cfbd.player_usage — currently skipped --|
| ⚪ | Closing line value (CLV) dataset | Build from track_lines.py snapshots over a season |

---

## Dashboard & UI (Streamlit — legacy, pending rebuild)

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | New color palette (charcoal-olive / forest green) | Space Grotesk font |
| 🟢 | Sports page — model_score field, n_edges, warnings | Updated for v3 model |
| 🟢 | Havoc display-only note in CFB page | Ablation-driven |
| 🟡 | Goals page | See Goals section below |
| 🔵 | All pages — superseded by Next.js rebuild | Do not invest further in Streamlit |

---

## Goals Page — Current Deficiencies

### What's wrong
- Binary goals show `in_progress` instead of meaningful status
- Finance goals show 0% — no data pipeline for actuals
- Habit goals show >100% — target set as `1` (binary) vs cumulative actuals
- Goal keys display as raw snake_case
- No visual differentiation between on-track / at-risk / behind
- No pace indicator

### Planned fixes (will be addressed in Next.js rebuild)
| Status | Item |
|--------|------|
| 🔵 | Split numeric vs binary goals into distinct display components |
| 🔵 | Fix habit goals — change targets in 2026.yaml to annual totals |
| 🔵 | Add status color logic: green ≥ pace, amber 10% behind, red >20% behind |
| 🔵 | Format goal labels — remove underscores, title case, clean units |
| 🔵 | Add pace indicator — where should you be today to hit annual target? |
| 🔵 | Plaid integration for Finance goals actuals |
| ⚪ | Manual override input for goals with no pipeline source |
| ⚪ | Year-over-year comparison panel |

---

## Shows Page

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | Denver concerts — AEG + Ticketmaster | Daily, artist matching |
| 🔵 | Venue map | Denver map with show pins |
| 🔵 | Artist similarity radar | show_radar.py exists but dormant |
| 🔵 | Calendar integration | One-click add to calendar |
| 🔵 | Personal attendance log | Mark attended, rate shows |
| ⚪ | Setlist integration | setlist.fm API |
| ⚪ | Pre-show playlist | Auto-generate Spotify playlist before a show |

---

## Data & Pipelines

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | Strava (running) | Daily, OAuth |
| 🟢 | Hardcover (reading) | Daily, GraphQL |
| 🟢 | Habits (local JSONL) | Daily |
| 🟢 | Google Calendar | Mon/Thu |
| 🟢 | SugarWOD CSV (CrossFit) | Manual import |
| 🟢 | Spotify streaming + Daily 10 | Daily |
| 🟢 | AEG + Ticketmaster (Denver shows) | Daily |
| 🟢 | CFBD (CFB historical 2021-2025) | Annual + weekly during season |
| 🟢 | WOD scraper (Park Hill CrossFit) | Daily, Playwright |
| 🟡 | Insights pipeline | Built but dormant |
| 🔵 | Apple Health | Steps, sleep, HRV, weight |
| 🔵 | Letterboxd | RSS feed letterboxd.com/{user}/rss/ |
| 🔵 | Plaid (Finance) | Transaction data for savings/spending goals |
| 🔵 | The Odds API (NFL/MLB) | Historical + live lines |
| ⚪ | Sleep tracking (Oura/Garmin/Whoop) | API varies by device |
| ⚪ | Weather integration | OpenWeatherMap — Denver forecast |

---

## Infrastructure

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | Mac mini daily sync via launchd | 9am daily |
| 🟢 | GitHub repo (cnvertbleweathr/life-os-2026) | Branch: main |
| 🟡 | DuckDB single-file backup | Highest priority unaddressed risk |
| 🔵 | Remote access — Tailscale or Cloudflare Tunnel | Required for Next.js rebuild |
| 🔵 | FastAPI + Next.js on Mac mini | Replaces Streamlit |
| 🔵 | capuchin.cyou DNS | Point to production app |
| 🔵 | Spotify headless auth fix | Non-interactive token refresh |
| 🔵 | Fix 2026 hardcoded in 10+ locations | Shared constant |
| ⚪ | Push notifications (ntfy.sh) | Morning digest |
| ⚪ | Year-in-review generator | December target |
| ⚪ | 2027 goals planning UI | December target |

---

## Nice-to-Haves (Someday)

- Natural language DuckDB queries ("how many miles did I run in April?")
- Spotify Wrapped-style monthly recap auto-generated on 1st of month
- Concert ticket price drop alerts
- Financial goals via Plaid
- Cowork integration for export + insights pipeline scheduling
