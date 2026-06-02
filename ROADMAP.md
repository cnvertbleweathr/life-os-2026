# ONS Product Roadmap

Last updated: 2026-06-01

---

## Status Legend
- 🟢 **Done** — shipped and working
- 🟡 **In Progress** — partially built or needs wiring
- 🔵 **Planned** — scoped, not started
- ⚪ **Idea** — not yet scoped

---

## Dashboard & UI

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | New color palette (charcoal-olive / forest green) | Space Grotesk font |
| 🟢 | Single-screen Home (no scroll, 1080p) | Calendar + Daily 10 + WOD + Streams + Goals |
| 🟢 | Sports page redesign | Stream cards matching Home style |
| 🟢 | Habits 50/50 layout + motivational quote | zenquotes.io with local fallback |
| 🟡 | Goals page overhaul | See Goals section below |
| 🔵 | Shows page improvements | See Shows section below |
| 🔵 | Mobile-responsive layout | Currently desktop-only |
| ⚪ | Dark/light mode toggle | Low priority |

---

## Goals Page — Current State & Roadmap

### What's wrong right now
- **Progress tracking is broken for non-numeric goals** — binary goals (Marathon Completed, Promotion, Roth IRA, HSA) show `in_progress` as the value instead of a meaningful status. These need a separate display path.
- **No progress data source for Finance goals** — Monthly Savings, Roth IRA, HSA all show 0% because there's no data pipeline feeding actuals. Needs Plaid integration or manual CSV input.
- **Habits goals (Fiction Pages, Nonfiction Pages, Meditation, Pushups) show >100%** — because the target is set as `1` (binary daily flag) but actuals are cumulative counts. The goal YAML and mart logic need to align on whether these are daily or annual targets.
- **Goal keys are snake_case ugly** — `fiction_pages_10`, `ps_revenue_usd`, `crossfit_classes` showing raw instead of formatted labels.
- **No visual differentiation between on-track / at-risk / behind** — everything is the same orange bar. Should be green/amber/red by status.
- **No year-over-year context** — no way to see last year's actuals or compare progress pace.

### Planned fixes
| Status | Item |
|--------|------|
| 🔵 | Split numeric vs binary goals into distinct display components |
| 🔵 | Fix habit goals — change targets in `2026.yaml` to annual totals (e.g. 365 for daily meditation) |
| 🔵 | Add status color logic: green ≥ pace, amber 10% behind pace, red >20% behind |
| 🔵 | Format goal labels — remove underscores, title case, clean units |
| 🔵 | Add "pace" indicator — where should you be on this date to hit the annual target? |
| 🔵 | Plaid integration for Finance goals actuals |
| ⚪ | Manual override input — let user enter actuals for goals with no pipeline source |
| ⚪ | Year-over-year comparison panel |
| ⚪ | Goal completion celebration (confetti, sound) on 100% |

---

## CFB Betting & Degenerates Corner

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | 5-season historical validation (2021-2025) | PPA gap edge confirmed 5/5 seasons |
| 🟢 | 263 FBS team ATS profiles in DuckDB | Tier system: ELITE/STRONG/NEUTRAL/FADE/STRONG_FADE |
| 🟢 | Edge Matrix tab | All situational factors ranked by ATS/O/U edge |
| 🟢 | Team Intel tab | Profile card + situational ROI + season trend |
| 🟢 | Matchup analysis + similar opponent engine | SP+/PPA similarity matching |
| 🟢 | Signal stack verdict (BET / LEAN / PASS) | |
| 🟡 | Degenerates Corner pick cards | Structure exists, pick generation not wired |
| 🔵 | Wire `pregame_lookup.py` → `todays_picks.json` → Sports page | Seasonal weekly run |
| 🔵 | Game Scout — weekly matchup browser | Auto-pull that week's games + lines during season |
| 🔵 | 2026 season live tracking | Weekly pipeline run, real-time model validation |
| 🔵 | Refresh team profiles at 2026 season start (Week 4) | `cfb_build_team_profiles.py --min-games 8` |
| 🔵 | Conference-level edge filtering in Team Intel | Filter matchups by conference ATS trends |
| 🔵 | Returning production gap signal | Currently in game_context, not wired into verdict |
| 🔵 | Coach matchup history | `cfbd.coaches` table — record vs specific opponents |
| 🔵 | Line movement signal | `spread_open` vs `spread` — sharp money indicator |
| 🔵 | NFL betting pipeline | The Odds API — same dbt mart pattern |
| 🔵 | MLB betting pipeline | The Odds API + Statcast for advanced metrics |
| ⚪ | Injury proxy via player usage drops | `cfbd.player_usage` — currently skipped |
| ⚪ | Travel distance calculation | `cfbd.venues` lat/long + haversine |
| ⚪ | 4-year weighted recruiting talent model | Better than single-year recruiting rank |
| ⚪ | Push alert for qualifying bets | ntfy.sh / Pushover notification |

---

## Shows Page

### Current state
Shows the list of upcoming Denver concerts from AEG + Ticketmaster with artist matching against Tewnidge/Deeds playlists. Stars on artist matches. Ticket links.

### What it needs
| Status | Item | Notes |
|--------|------|-------|
| 🔵 | Venue map | Plot upcoming shows on a Denver map with st.map or Places API |
| 🔵 | Price tracking | Monitor ticket prices, alert on drops |
| 🔵 | Artist similarity radar | "If you like X who's playing, you might also like Y who's also playing" |
| 🔵 | Calendar integration | One-click "Add to Calendar" for shows you want to attend |
| 🔵 | Personal attendance log | Mark shows you've been to, rate them |
| 🔵 | Show radar (similar artists) | `scripts/show_radar.py` exists but is dormant — wire it in |
| ⚪ | Setlist integration | setlist.fm API — what did they play last time they toured? |
| ⚪ | Pre-show playlist | Auto-generate a Spotify playlist with that artist's top tracks before a show |

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
| 🟢 | CFBD (CFB historical 2021-2025) | Annual |
| 🟢 | WOD scraper (Park Hill CrossFit) | Daily, Playwright |
| 🟡 | Insights pipeline | Built but dormant — `export_for_insights.py`, `generate_insights.py`, `weekly_reflection.py` |
| 🔵 | Apple Health | Steps, sleep, HRV, weight — export XML periodically |
| 🔵 | Letterboxd | Apply for API or use RSS feed (`letterboxd.com/{user}/rss/`) |
| 🔵 | Plaid (Finance) | Transaction data for savings/spending goals |
| 🔵 | The Odds API (NFL/MLB) | Historical + live lines for sports betting expansion |
| ⚪ | Sleep tracking (Oura/Garmin/Whoop) | API varies by device |
| ⚪ | Weather integration | OpenWeatherMap — Denver daily forecast on Home |

---

## Infrastructure & Deployment

| Status | Item | Notes |
|--------|------|-------|
| 🟢 | Mac mini daily sync via launchd | 9am daily |
| 🟢 | GitHub repo (`cnvertbleweathr/ons-2026`) | Branch: main |
| 🟡 | Hetzner VPS provisioned | IP: 46.62.140.109 — setup pending |
| 🔵 | Deploy to VPS | Nginx + SSL + systemd |
| 🔵 | Point `capuchin.cyou` DNS to VPS | Porkbun A record |
| 🔵 | Streamlit on VPS with persistent DuckDB | Volume mount for data/ |
| 🔵 | Automated daily sync on VPS | systemd timer replacing launchd |
| 🔵 | Spotify headless auth fix | Non-interactive token refresh for launchd |
| 🔵 | Fix `2026` hardcoded in 10+ locations | Use `datetime.now().year` or shared constant |
| ⚪ | Push notifications (ntfy.sh) | Morning digest: WOD + games today + calendar alerts |
| ⚪ | Year-in-review generator | December target |
| ⚪ | 2027 goals planning UI | December target |

---

## Nice-to-Haves (Someday)

- Natural language DuckDB queries ("how many miles did I run in April?")
- Spotify Wrapped-style monthly recap auto-generated on 1st of month
- Concert ticket price drop alerts
- Financial goals via Plaid
- Cowork integration for export + insights pipeline scheduling
