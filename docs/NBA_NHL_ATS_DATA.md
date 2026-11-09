# NBA / NHL ATS — data layer

Goal: the same metrics-first approach as CFB (find validated edges, then hard rules),
for NBA spreads and NHL puck lines / moneylines.

## Sources → tables

| Table | Source | Coverage | Grain |
|---|---|---|---|
| `nba.historical_lines` | SBR closing lines via kyleskom/NBA-Machine-Learning-Sports-Betting (GitHub) | 2007-08 → Jan 2026 | game |
| `nba.games`, `nba.odds` | ESPN site scoreboard + core odds API | games any season; **lines 2013-14 (season 2014) → live** | game; game × provider |
| `nba.team_game_logs` | stats.nba.com LeagueGameLog (`nba_api`) | 1996-97 → live | game × team |
| `nhl.games`, `nhl.odds` | ESPN (puck line = "spread") | games any season; **lines 2019-20 (season 2020) → live** | game; game × provider |
| `nhl.moneypuck_team_games` | MoneyPuck all_teams.csv (credit MoneyPuck, non-commercial) | 2008-09 → live | game × team × situation |
| `nhl.goalie_games` | NHL API gamecenter boxscore | any season → live | game × goalie (starter flag) |

Season convention everywhere: **season = year the season ends** (2025-26 → 2026).
`home_spread` is **negative when home is favored**. `home_ats_margin = home_margin + home_spread`.

## Gotchas (found on day one)

- kyleskom `Spread` is **unsigned before 2022-23** — sign must come from the moneyline favorite. Raw, it made home teams look like 44% ATS. Fixed in the loader.
- ESPN odds eras and snapshot quality: see **ESPN odds coverage** below. Raw JSON is kept in `odds.raw_json` and on disk in `data/raw/espn/` so the parser can be fixed without re-fetching.
- NHL puck line is ±1.5 at varying juice — compute ROI from the actual price, never flat -110. Moneyline is the more natural NHL "side" market; model both.
- Team keys differ across sources (ESPN `LA`/`NJ`/`SJ`/`TB`/`UTAH` vs NHL `LAK`/`NJD`/`SJS`/`TBL`/`UTA`; kyleskom uses full names). Needs a dbt seed for crosswalks.

## ESPN odds coverage (Phase 0 probes, 2026-11-09)

Sampled one or more dates per season with `--probe` and a full parse of every game ×
provider on each date (NBA: 20 dates 2007–2026, NHL: 15 dates 2016–2026).
Earliest season with lines, used as START for the Phase 1 backfill:

| League | No lines | First lines | START |
|---|---|---|---|
| NBA | Jan 2007, 2008, 2009, 2011 | Jan 2013: projection sites only (numberfire, teamrankings, consensus). Nov 2013: real books | **2014** |
| NHL | Jan 2016, Jan 2018, Jan + Apr 2019 | 2019-10-05 (opening week of 2019-20) | **2020** |

NBA before 2014 has `nba.historical_lines` (SBR closes, 2008+), so ESPN isn't needed there.
NHL has **no line source before 2019-20**: NHL edges get 7 seasons (2020–2026), and 2020/2021
are the bubble and short no-crowd seasons.

### Eras

| Era (season) | Providers seen | Snapshots | Opening line |
|---|---|---|---|
| NBA 2014 → ~2018 | Offshore: 5Dimes, BetOnline, Bovada, SportsBetting.ag, BetUS, Westgate, Fantasy911, + `Opening`, `consensus` | `current` only | item-level `initialSpread` / `initialOverUnder` (home-signed, the `Opening` book's line, same on every provider) → parsed into `open_*` |
| NBA 2019 → 2023, NHL 2020 → 2023 | US books: Caesars (several states), Westgate, Wynn, DraftKings, MGM, Unibet, SugarHouse, PointsBet, Bet365, BetStars, CG Technology, Holland Casino, Titanbets, `* - Live Odds` | `current` only until 2022-23; then ESPN BET gets a `close` that is **often junk** (the price "-115" in `pointSpread` and `total`; now nulled by the parser) | none |
| 2024 (2023-24) | Same multi-book set, from Oct 2023 | **Real** `open` / `close` / `current` on nearly every book (some opens hold only the moneyline) | `open_*` |
| 2025 → 2026 | One partner book: `ESPN BET` (2024-25), `Draft Kings` (id 100, 2025-26; not the same provider as `DraftKings` id 40) | Real `open` / `close` | `open_*` |

Are open/close real? From 2024 (2023-24) on, yes. Across all cached non-live items, the
spread favorite matches the moneyline favorite on 234/234 NBA closes beyond ±1.5 and 137/138
opens. Before 2023-24 there is no close snapshot. The item-level number (which equals
`current`) is the final line, and the `initialSpread` open covers 2014–~2018 only.

### Not books: exclude from line selection

`numberfire`, `teamrankings`, `accuscore`, `betegy` (projection sites: their "spreadOdds" are
probabilities like 63.13 or 102), `consensus` (no total or ML), and every `* - Live Odds`
provider (in-game numbers; their `open` is a live line). `Opening` is the opening line, not a book.

### Parser fixes made in Phase 0

- `game_date` is the **US/Eastern** date (ESPN's `?dates=` day); `start_time` stays UTC.
  Before, every 7pm+ ET tip landed on the next day.
- `initialSpread` / `initialOverUnder` fill `open_*` when there's no `open` snapshot (2014–~2018).
- American prices with |odds| < 100 are nulled: ESPN posts a missing moneyline as `0`.
- Lines outside ±40 (NBA) / ±4 (NHL) and totals outside 150–300 (NBA) / 3–12 (NHL) are nulled.

Still in the data, for Phase 2 line selection to handle:
- About 2% of NHL items put −1.5 on the moneyline underdog. Most are near pick'em, where ESPN's
  own `favorite` flag says so. A few are junk (both MLs positive; Unibet 2023 at −124/+265
  with a −560 puck line). Screen ML pairs that don't make a two-sided market.
- One 2024 ESPN BET open (CHI @ CLE, 2024-01-15) has the spread sign flipped against its own
  moneyline (`+8.5` with ML −190). Cross-check open spread vs open ML.
- Provider names drift (`Caesar's` / `Caesars` / `Caesars Sportsbook`, `DraftKings` / `Draft Kings`).
  Key priority rules on `provider_id`.

## First run (Mac mini — stop FastAPI first)

With Claude Code, use the phase prompts in `docs/NBA_NHL_PROMPTS.md` instead of running these by hand.

```bash
uv sync                                                    # picks up nba_api
python pipelines/espn_odds_pipeline.py --probe nba --date 2024-01-15   # paste output
python pipelines/espn_odds_pipeline.py --probe nhl --date 2024-01-15
python pipelines/espn_odds_pipeline.py --probe nba --date 2019-01-15   # how deep does ESPN go?
python pipelines/nba_stats_pipeline.py --lines-bootstrap
python scripts/nba_ats_scan.py
python pipelines/nba_stats_pipeline.py --season 2008 --end-season 2026
python pipelines/nhl_stats_pipeline.py --season 2009 --end-season 2026
python pipelines/nhl_stats_pipeline.py --season 2020 --end-season 2026 --goalies   # boxscores, cached
python pipelines/espn_odds_pipeline.py --league nba --season 2014 --end-season 2026
python pipelines/espn_odds_pipeline.py --league nhl --season 2020 --end-season 2026
```

Daily sync: `espn_odds_nba_nhl` (daily, last 3 + next 2 days), `nba_stats_pipeline` (daily),
`nhl_stats_pipeline --goalies` (Mon/Thu).

## Baseline NBA scan (2007-08 → Jan 2026, flat -110, pushes dropped)

Market is efficient on simple splits — home ATS 49.5%, 0/19 seasons profitable.
One lead worth testing with efficiency features, **not validated**:

| Split | n | Win% | ROI | Seasons + |
|---|---|---|---|---|
| Away team has 2+ more days rest → bet away | 850 | 55.1% | +5.1% | 13/19 |
| Home on B2B vs rested away → bet away | 1,832 | 53.2% | +1.6% | 10/19 |
| Home ATS (all) | 22,956 | 49.5% | −5.5% | 0/19 |

## Next

1. dbt staging + team crosswalk seeds; join ESPN ↔ NBA stats ↔ historical lines, ESPN ↔ MoneyPuck ↔ goalies.
2. Rolling pregame features with no lookahead: NBA net rating / four factors (last 10, season-to-date), rest, travel; NHL xG% 5v5, PP/PK xG, starter GSAx, rest.
3. Efficiency-gap vs line edges (the PPA-gap analogue), validated cross-season like `cfb_edge_validation.py`.
