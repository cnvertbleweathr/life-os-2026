# NBA / NHL ATS — data layer

Goal: the same metrics-first approach as CFB (find validated edges, then hard rules),
for NBA spreads and NHL puck lines / moneylines.

## Sources → tables

| Table | Source | Coverage | Grain |
|---|---|---|---|
| `nba.historical_lines` | SBR closing lines via kyleskom/NBA-Machine-Learning-Sports-Betting (GitHub) | 2007-08 → Jan 2026 | game |
| `nba.games`, `nba.odds` | ESPN site scoreboard + core odds API | depth TBD by probe (≥2018 expected) → live | game; game × provider |
| `nba.team_game_logs` | stats.nba.com LeagueGameLog (`nba_api`) | 1996-97 → live | game × team |
| `nhl.games`, `nhl.odds` | ESPN (puck line = "spread") | depth TBD → live | game; game × provider |
| `nhl.moneypuck_team_games` | MoneyPuck all_teams.csv (credit MoneyPuck, non-commercial) | 2008-09 → live | game × team × situation |
| `nhl.goalie_games` | NHL API gamecenter boxscore | any season → live | game × goalie (starter flag) |

Season convention everywhere: **season = year the season ends** (2025-26 → 2026).
`home_spread` is **negative when home is favored**. `home_ats_margin = home_margin + home_spread`.

## Gotchas (found on day one)

- kyleskom `Spread` is **unsigned before 2022-23** — sign must come from the moneyline favorite. Raw, it made home teams look like 44% ATS. Fixed in the loader.
- ESPN odds: ≤2023 multi-provider with junk open/close snapshots; 2024+ one partner book with real open/close. Raw JSON is kept in `odds.raw_json` and on disk in `data/raw/espn/` so the parser can be fixed without re-fetching.
- NHL puck line is ±1.5 at varying juice — compute ROI from the actual price, never flat -110. Moneyline is the more natural NHL "side" market; model both.
- Team keys differ across sources (ESPN `LA`/`NJ`/`SJ`/`TB`/`UTAH` vs NHL `LAK`/`NJD`/`SJS`/`TBL`/`UTA`; kyleskom uses full names). Needs a dbt seed for crosswalks.

## First run (Mac mini — stop FastAPI first)

```bash
uv sync                                                    # picks up nba_api
python pipelines/espn_odds_pipeline.py --probe nba --date 2024-01-15   # paste output
python pipelines/espn_odds_pipeline.py --probe nhl --date 2024-01-15
python pipelines/espn_odds_pipeline.py --probe nba --date 2019-01-15   # how deep does ESPN go?
python pipelines/nba_stats_pipeline.py --lines-bootstrap
python scripts/nba_ats_scan.py
python pipelines/nba_stats_pipeline.py --season 2008 --end-season 2026
python pipelines/nhl_stats_pipeline.py --season 2009 --end-season 2026
python pipelines/nhl_stats_pipeline.py --season 2022 --end-season 2026 --goalies   # ~6k boxscores, cached
python pipelines/espn_odds_pipeline.py --league nba --season 2019 --end-season 2026
python pipelines/espn_odds_pipeline.py --league nhl --season 2019 --end-season 2026
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
