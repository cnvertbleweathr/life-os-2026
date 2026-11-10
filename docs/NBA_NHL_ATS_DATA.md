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

## Coverage (Phase 1 backfill, 2026-11-09)

Loaded: `nba.team_game_logs` 2008–2026, `nhl.moneypuck_team_games` 2009–2026,
`nhl.goalie_games` 2020–2026, ESPN `nba.games`/`nba.odds` 2014–2026 and
`nhl.games`/`nhl.odds` 2020–2026. The in-progress 2026-27 season (2027) comes from daily sync.
Re-run with `uv run python scripts/nba_nhl_data_profile.py [--providers]` (read-only, safe with the API up).

```
NBA  ESPN games and lines
  reg/post = completed real games; exh = exhibitions (All-Star etc.); n/p = listed, never played (canceled / postponed).
  Line columns: book providers only (projection sites, consensus and live feeds excluded), on completed real games; % of reg+post.
  null% is per odds row. 'all-prov' = games with any provider row, exhibitions and unplayed included.
season  reg  post exh  n/p | exp   flag              | any line   %  open   %  close   % | books  odds rows | null%: spread price  ML  total close | all-prov
2014  1230   89   1    2 | 1230                    |  1314  100  1314  100     0    0 |     5      6552 |          0     0    7    0   100 | 1321
2015  1230   81   1    2 | 1230                    |  1271   97  1271   97     0    0 |     5      6290 |          0     0    9    0   100 | 1313
2016  1230   86   1    2 | 1230                    |  1316  100  1316  100     0    0 |    12      8279 |          0     0    7    0   100 | 1318
2017  1230   79   1    3 | 1230                    |  1274   97  1274   97     0    0 |     9     11385 |          0     0    2    0   100 | 1312
2018  1230   82   2    1 | 1230                    |  1312  100     0    0     0    0 |     7      8290 |          6     6   10    6   100 | 1313
2019  1230   82   2    0 | 1230                    |  1312  100     0    0     0    0 |     7      8008 |          0     0    5    0   100 | 1312
2020  1059   83   2   12 | 1059  COVID pause + bub |  1142  100     0    0     0    0 |    12      7687 |          0     0    0    1   100 | 1154
2021  1080   85   1   32 | 1080  72 games          |  1165  100     0    0     0    0 |    11     11492 |          0     0    0    0   100 | 1197
2022  1230   87   1   11 | 1230                    |  1317  100     0    0     0    0 |    13     15111 |          1     1    0    0   100 | 1329
2023  1230   84   1    1 | 1230                    |  1314  100     0    0     1    0 |    14     16141 |          0     0    0    0   100 | 1316
2024  1231   82   1    2 | 1230                    |  1313  100  1308  100  1313  100 |    12     12822 |          0     0    0    0     0 | 1315
2025  1231   84   3    5 | 1230                    |  1315  100  1314  100  1314  100 |     1      1315 |          0     0    0    0     0 | 1321
2026  1231   85   4    4 | 1230                    |  1316  100  1316  100  1315  100 |     2      1364 |          0     0    0    0     1 | 1320

NBA  stats tables
season | team_game_logs: rows  games reg  games post | historical_lines: rows  null% spread  total  ML
2008   |                2632   1230     86       |              1294     0.0    0.0    0.0
2009   |                2630   1230     85       |              1302     0.0    0.0    0.0
2010   |                2624   1230     82       |              1309     0.0    0.0    0.0
2011   |                2622   1230     81       |              1305     0.0    0.0    0.0
2012   |                2148    990     84       |              1072     0.0    0.0    0.0  (lockout, 66 games)
2013   |                2630   1230     85       |              1305     0.0    0.0    0.0
2014   |                2638   1230     89       |              1308     0.0    0.0    0.0
2015   |                2622   1230     81       |              1307     0.0    0.0    0.0
2016   |                2632   1230     86       |              1302     0.0    0.0    0.0
2017   |                2618   1230     79       |              1291     0.0    0.0    0.0
2018   |                2624   1230     82       |              1300     0.0    0.0    0.0
2019   |                2624   1230     82       |              1294     0.0    0.0    0.0
2020   |                2284   1059     83       |              1122     0.0    0.0    0.0  (COVID pause + bubble)
2021   |                2330   1080     85       |              1153     0.0    0.0    0.0  (72 games)
2022   |                2634   1230     87       |              1302     0.0    0.0    0.0
2023   |                2628   1230     84       |              1314     0.0    0.0    0.0
2024   |                2624   1230     82       |              1193     0.0    0.0    0.0
2025   |                2628   1230     84       |              1323     0.0    0.0    0.0
2026   |                2630   1230     85       |               549     0.0    0.0    0.0

NHL  ESPN games and lines
  reg/post = completed real games; exh = exhibitions (All-Star etc.); n/p = listed, never played (canceled / postponed).
  Line columns: book providers only (projection sites, consensus and live feeds excluded), on completed real games; % of reg+post.
  null% is per odds row. 'all-prov' = games with any provider row, exhibitions and unplayed included.
season  reg  post exh  n/p | exp   flag              | any line   %  open   %  close   % | books  odds rows | null%: spread price  ML  total close | all-prov
2020  1082  130   3  193 | 1082  COVID pause       |  1211  100     0    0     0    0 |    13      8195 |          0     0    0    5   100 | 1230
2021   868   84   0   56 |  868  56 games, divisio |   951  100     0    0     0    0 |    13     10894 |          0     0    0    3   100 | 972
2022  1312   89   3   99 | 1312  32 teams (Seattle |  1401  100     0    0     0    0 |    15     17787 |          1     1    0    1   100 | 1425
2023  1312   88   3    5 | 1312  32 teams (Seattle |  1400  100     0    0     1    0 |    16     17463 |          8     8    0    1   100 | 1404
2024  1312   88   3    1 | 1312  32 teams (Seattle |  1398  100  1389   99  1398  100 |    14     15114 |          3     3    0    8     3 | 1401
2025  1312   86   7    2 | 1312  32 teams (Seattle |  1398  100  1398  100  1398  100 |     1      1398 |          0     0    0    0     0 | 1406
2026  1312   82   0    1 | 1312  32 teams (Seattle |  1394  100  1394  100  1394  100 |     2      1428 |          0     0    0    0     1 | 1395

NHL  stats tables
season | moneypuck: rows    reg  post   all  5on5  5on4  4on5 | null% xgoalsfor corsi | goalie_games: rows  games  starters/game
2009   |   10512  1227    87  2628  2628  2628  2628 |    0.0    0.0  |                 -
2010   |   10544  1229    89  2636  2636  2636  2636 |    0.0    0.0  |                 -
2011   |   10544  1230    88  2636  2636  2636  2636 |    0.0    0.0  |                 -
2012   |   10528  1230    86  2632  2632  2632  2632 |    0.0    0.0  |                 -
2013   |    6448   720    86  1612  1612  1612  1612 |    0.0    0.0  |                 -  (lockout, 48 games)
2014   |   10584  1230    93  2646  2646  2646  2646 |    0.0    0.0  |                 -
2015   |   10552  1230    89  2638  2638  2638  2638 |    0.0    0.0  |                 -
2016   |   10568  1230    91  2642  2642  2642  2642 |    0.0    0.0  |                 -
2017   |   10536  1230    87  2634  2634  2634  2634 |    0.0    0.0  |                 -
2018   |   10840  1271    84  2710  2710  2710  2710 |    0.0    0.0  |                 -  (31 teams (Vegas))
2019   |   10864  1271    87  2716  2716  2716  2716 |    0.0    0.0  |                 -  (31 teams (Vegas))
2020   |    9696  1082   130  2424  2424  2424  2424 |    0.0    0.0  |              4850   1212   2.00  (COVID pause)
2021   |    7616   868    84  1904  1904  1904  1904 |    0.0    0.0  |              3808    952   2.00  (56 games, divisional)
2022   |   11208  1312    89  2802  2802  2802  2802 |    0.0    0.0  |              5605   1401   2.00  (32 teams (Seattle))
2023   |   11200  1312    88  2800  2800  2800  2800 |    0.0    0.0  |              5599   1400   2.00  (32 teams (Seattle))
2024   |   11200  1312    88  2800  2800  2800  2800 |    0.0    0.0  |              5599   1400   2.00  (32 teams (Seattle))
2025   |   11184  1312    86  2796  2796  2796  2796 |    0.0    0.0  |              5592   1398   2.00  (32 teams (Seattle))
2026   |   11152  1312    82  2788  2788  2788  2788 |    0.0    0.0  |              5575   1394   2.00  (32 teams (Seattle))
```

What the profile shows:

- **No season is off its schedule** once exhibitions and unplayed games are set aside. The short
  seasons match exactly: NBA 2012 (990), 2020 (1,059), 2021 (1,080); NHL 2013 (720),
  2020 (1,082), 2021 (868). NBA ESPN has 1,231 in 2024–26: the NBA Cup final, a real game with
  lines that `nba_api` leaves out of `team_game_logs` because it doesn't count in the standings.
  MoneyPuck is short 3 games in 2009 and 1 in 2010.
- **ESPN lines cover every completed real game** in every season loaded, except NBA 2015 and
  2017 (97%, about 40 games each with only projection sites). Open lines: NBA 2014–2017
  (`initialSpread`) and 2024 on. Close snapshots: 2024 on only.
- **`nba.historical_lines` has gaps**: 2024 has 1,193 games, about 119 short, and 2026 stops in
  January (549). ESPN covers both, so the Phase 2 spine should prefer ESPN from 2014 and use
  `historical_lines` for 2008–2013.
- **Goalies**: exactly 2 starters per game in every NHL season.

Data issues for Phase 2 (staging and the game spine):

- **ESPN files exhibitions as regular season** (`season_type = 2`): NBA All-Star, Rising Stars
  and World v USA (1–4 a season), NHL All-Star 3-on-3 (division or captain teams) and the
  2025 4 Nations Face-Off (7 games, CAN/USA/SWE/FIN). Several have odds. Drop any game where
  a side isn't a franchise; the crosswalk seed does this naturally.
- **Unplayed games are listed**: NHL 2020 has 189 `STATUS_CANCELED` (the COVID pause), and
  `STATUS_POSTPONED` rows exist in both leagues (NBA 77, NHL 168). The same matchup was played
  later under a new `game_id` for 75/77 NBA and 168/168 NHL postponements. Keep `completed` only.
- **Provider ids are league-specific**: Bet365 is 2000 in NBA and 1001 in NHL; 1005 is betegy
  (NBA) but FanDuel (NHL). BOVADA appears as 20 and 24 in 2016. Key provider priority on
  `(league, provider_id)`.
- **Utah's ESPN abbreviation changed**: `UTAH` in 2025, `UTA` in 2026, same team id 129764.

## dbt foundation (Phase 2, 2026-11-09)

```
seeds (main_seeds)            staging (main_staging, views)        intermediate (main_intermediate)
nba_team_crosswalk ─┐         stg_nba__games, stg_nba__odds,       int_nba__game_spine
nhl_team_crosswalk ─┼──────▶  stg_nba__historical_lines,     ───▶  int_nhl__game_spine
nba_nhl_odds_providers┘       stg_nba__team_game_logs,
                              stg_nhl__games, stg_nhl__odds,
                              stg_nhl__moneypuck_team_games, stg_nhl__goalie_games
```

`uv run dbt build --profiles-dir profiles --select +int_nba__game_spine +int_nhl__game_spine`
(from `dbt/`, API stopped). The daily sync now runs `dbt seed` before `dbt run`.

**Team crosswalks** are generated, not hand-written: `scripts/nba_nhl_build_crosswalks.py` reads the
distinct team keys in every raw table and writes `dbt/seeds/{nba,nhl}_team_crosswalk.csv`
(one row per franchise code, source, key, valid-from/to season; blank = open-ended). Canonical codes
are franchises: nba_api abbreviations (`SEA`→`OKC`, `NJN`→`BKN`, `NOH`→`NOP`) and NHL API codes
(MoneyPuck `L.A`→`LAK`, `ATL`→`WPG`; `ARI`→`UTA` in every source). historical_lines full names map
through the names nba_api and ESPN report. Rerun the script after loading a new season; the test
`assert_nba_nhl_staging_keeps_franchise_rows` fails if a key goes missing. The only unmapped keys are
exhibition sides (All-Star teams, 4 Nations countries: 28 NBA, 24 NHL keys).

**One line per game** (`stg_*__odds`, rule in `dbt/macros/espn_odds.sql`, priorities in
`dbt/seeds/nba_nhl_odds_providers.csv` keyed on `(league, provider_id)`):
1. books only (projection sites, consensus, Opening and live feeds are `is_book = false`);
2. per market, the close snapshot when present (2023-24 on), else the item-level final line;
   prices from the same snapshot;
3. spread: agrees with its own ML favourite → within 3 pts (NHL 1 goal) of the median of all books
   on the game (≥ 3 books) → NHL standard ±1.5 → seed priority (DraftKings, ESPN BET, MGM, Caesars …;
   5Dimes, Pinnacle, BetOnline, Bovada … for 2013-17);
4. moneyline from the spread's book when it has one, total picked separately (agreeing with the
   median, spread's book first). `line_source = 'espn:<book>:<close|final>'`, plus `ml_book` /
   `total_book`.

The spine falls back to `historical_lines` (flat -110, no prices) for NBA games with no ESPN line,
and uses it alone for 2008–2013. NHL has no lines before 2019-20.

### Spine coverage

| | NBA | NHL |
|---|---|---|
| Games | 24,404 (2008–2026) | 23,222 (2009–2026) |
| Games source | nba_api 2008–13, ESPN 2014+ | MoneyPuck 2009–19, ESPN 2020+ |
| Stats match, ESPN seasons | 99.9–100% per season; 3 unmatched = the NBA Cup finals (not in LeagueGameLog) | 100% every season |
| Line coverage | 98–100% every season (ESPN 2014+; SBR before, and for 79 ESPN gaps in 2014/15/17/25) | 99.8–100% 2020+ |
| Close snapshot | 2024–2026 | 2024–2026 |

Full per-season output: `uv run python scripts/nba_nhl_spine_report.py` (read-only; rerun after `dbt build`).

### Findings from building it

- **Late tips**: ESPN's Eastern date is one day after stats.nba.com's local date when a West-coast
  game tips at 9 pm PT (4 games, Feb 2020). The spine matches stats rows within ±1 day.
- **Neutral sites**: nba_api lists *both* teams as away for NBA Cup knockouts and the Paris /
  Mexico City games (10 games, 2024-25 on). The spine matches on the unordered team pair and
  keeps ESPN's home side.
- **MoneyPuck home flag**: 115 Phoenix home games in 2011-12 to 2013-14 are labelled AWAY for both
  teams. Staging treats the ARI side as home when a game has no HOME row.
- **historical_lines names**: "Charlotte Bobcats" through 2021-22, "New Orleans Pelicans" back to
  2007-08. Harmless with franchise codes.
- **Noisy books**: Caesars Sportsbook (id 31), Unibet and SugarHouse are > 3 pts off the other
  books on ~4% of NBA games (others < 0.5%); Westgate posts 0 / -110 / -110 placeholders (1.2% of
  rows). All four sit at the bottom of the priority list.
- **DraftKings NHL quotes no total on 29% of rows**, hence the separate total pick.
- **ESPN BET alternates**: 18 NHL games in 2024-25, when ESPN BET is the only book, carry only a
  ±2.5 line, and the suspended ANA–STL game (2020-03-11) has 0.0 (`is_standard_puck_line = false`
  on all 19). 31 NHL chosen lines still disagree with their ML favourite (`line_consistent = false`).
  Filter both in backtests.
- **ESPN vs SBR**: spreads agree within 0.3–1.4 pts mean absolute difference per season;
  1–11 games a season (< 1%) have opposite signs with |SBR| ≥ 2.
- **Scores**: ESPN and nba_api agree on all 16,748 comparable games. ESPN NHL scores count the
  shootout goal (628 games differ from MoneyPuck for that reason); 5 more differ, ESPN is used.

## Pregame features (Phase 3, 2026-11-09)

`main_marts.mart_nba_game_features` (24,404 games, 225 columns) and `mart_nhl_game_features`
(23,222 games, 165 columns): one row per spine game with `home_*`, `away_*` and `gap_*`
(home − away) features, the market line, and the results as labels.
`uv run dbt build --profiles-dir profiles --select +mart_nba_game_features +mart_nhl_game_features`.

| | NBA | NHL |
|---|---|---|
| Team form (stats source) | ORtg, DRtg, net, pace, eFG%, TOV%, ORB%, FT rate, for and against — last 5, last 10, season to date, prior season (`int_nba__team_box_features`) | 5v5 xGF%, Corsi%, high-danger share, PP xGF/60, PK xGA/60, finishing (goals − xG per game), all-situations xGF% — last 10, season to date, prior season (`int_nhl__team_xg_features`) |
| Schedule (spine) | days rest, back-to-back, 3-in-4, games in last 7 days, road-trip game, travel miles, last-10 ATS record and margin (`int_*__team_schedule`) | same, with puck-line form |
| Goalie | – | starter's GSAx and save% over his last 10 starts and season to date (`int_nhl__goalie_form`, 2019-20 on) |
| Model vs market | ratings-implied spread: blended net rating gap × pace + a home-court constant fitted on earlier seasons only (3.75 pts in 2009 drifting to 2.69 in 2026); `home_spread_edge = home_spread − implied_home_spread`, > 0 = ratings like home more than the market | xG-implied win probability: log5 of blended xGF% + home-ice log-odds fitted on earlier seasons only; `home_prob_edge` vs the no-vig moneyline probability |

**No lookahead.** Every window ends at `1 PRECEDING` (or uses `lag`); prior-season values come from
the whole previous season; the home-court / home-ice constants pool earlier seasons only.
"Blended" = season to date with the prior season weighted as 10 games. Checks:
- `assert_nba_rolling_feature_recomputes_from_raw` / `assert_nhl_…`: 20 random games, one rolling
  feature rebuilt from `nba.team_game_logs` / `nhl.moneypuck_team_games` without window functions.
- `scripts/feature_lookahead_check.py`: pandas reimplementation from the raw tables for 300 games per
  league (10 NBA + 4 NHL features, including rest / back-to-back from raw `nba.games` and goalie
  save%): 0 mismatches. It also computes each feature *with* the game included; that canary agrees
  with the marts on 0–7 rows per feature (coincidences, e.g. a game with no power-play time).

**Notes**
- Rolling windows reset each season (regular season and playoffs together); early-season rows lean
  on `_prior`. Rest and travel are null for a team's first game of a season.
- Box-score windows count games with a box score, so the three NBA Cup finals (no LeagueGameLog row)
  have null box features but keep schedule features.
- Travel uses the ESPN venue (`dbt/seeds/nba_nhl_venues.csv`, city-level coordinates; covers neutral
  sites, the 2020 bubbles, outdoor games), else the home team's city
  (`dbt/seeds/nba_nhl_team_cities.csv`) for pre-ESPN seasons. Pre-ESPN neutral-site games (London,
  Mexico City, NHL Global Series) are placed in the home team's city.
- NHL GSAx is approximate: the goalie is charged his ice-time share of the team's xG against.
  Team xGA includes empty-net chances while goals against doesn't, so GSAx runs +0.03 to +0.28 per
  start league-wide (2020–2026). The bias is shared, so home − away goalie gaps cancel it.
- How the simple models fare against the market (not edges, just calibration): NBA ratings margin
  correlates 0.405 with the result vs 0.466 for the closing spread; NHL Brier 0.238–0.246 vs the
  no-vig moneyline's 0.225–0.244 (2020–2026). Phase 4 tests where the gaps disagree with the market.

## Edge validation (Phase 4, 2026-11-09): nothing ships

`scripts/nba_edge_validation.py` and `scripts/nhl_edge_validation.py` (engine:
`scripts/nba_nhl_edges.py`) read only the feature marts. For each candidate and season S they
choose the threshold on seasons < S, bet S, and report only those out-of-sample bets. Each
candidate is placed at the close (the spine's line and price) or at the open (opening line and
price, 2023-24 on). The scripts write `data/betting/{league}_edges.csv` and append every
evaluation to `data/betting/{league}_trials.jsonl`.

**The bar:**
- n ≥ 200 (NBA) / 150 (NHL);
- bootstrap 95% ROI interval above 0;
- Bonferroni p_adj < 0.05, counting every candidate and every logged scan split;
- at least 5 seasons with ≥ 20 bets, positive in ≥ 60% of the seasons tested.

**Verdicts.** The `ats-edge-validator` agent reviewed both scripts in three rounds for the NBA and
two for the NHL. Its final verdict is REJECT for every candidate.

| League | Candidate | Out of sample | Verdict |
|---|---|---|---|
| NBA | total_model_open (predicted total vs the opening total, bet at the open) | 175 bets, +16.8%, CI [+2.6, +30.0], p_adj 0.40, 139 of the bets in 2024 | REJECT. Designed after seeing 2024-26, and playoff picks ride a model bias. Paper forward test only (below) |
| NBA | total_model (vs the close) | 675, +6.3%, CI [−0.8, +13.4] | REJECT. The line moves 2.25 pts against its picks, toward them only 21% of the time |
| NBA | rest_away_2plus (the Phase 0 lead) | 726, +1.6%, 7/16 seasons | REJECT. Found in the full-sample scan; the ESPN-era part is about +1% |
| NBA | big_dog, home_b2b_vs_rested_away, away_long_travel, three_in_four_fade, b2b_vs_rested, model_spread_follow / _fade / _follow_open | −2% to −17% | REJECT |
| NBA | rest_diff_more_rested, away_long_road_trip, ats_form_fade, total_b2b_under | no bets: training ROI never above 0 | REJECT |
| NHL | b2b_vs_rested_ml (rested team's ML vs an opponent on a back-to-back) | 933, +4.1%, CI [−1.8, +10.0], 4/5 seasons | REJECT. Closest NHL call. The open-priced variant (50 bets) was found in-sample |
| NHL | puck_dog_band, ml_dog_band | −4.7%, −19.5% | REJECT |
| NHL | xG model vs moneyline (follow / fade / puck line / open), goalie GSAx and save%, xG + goalie, puck_fav_band, both totals signals | no bets: training ROI never above 0 | REJECT |

Baselines (bet every side) lose 3–6% in every market, as they should. The simple models don't
beat the closing market. The ratings and xG features are inputs for later work, not bets.

**Problems the review found and fixed** (all in this PR):
- **NHL moneyline prices.** Most books before 2024-25 put 3-way regulation prices in ESPN's
  moneyline field. The two legs sum to about 0.85 implied (e.g. MIN +120 / away +175). The first
  run therefore showed every NHL moneyline strategy at +10–20% ROI. `dbt/macros/espn_odds.sql`
  now keeps only valid 2-way price pairs (implied sum 1.00–1.12) for moneylines, spreads and totals.
- **Fake opening lines.** ESPN BET posted alternate opening totals and spreads at −425 / +290 in
  2024-25. Opening pairs must now sit in a main-market band: NBA −135..+115, NHL totals −160..+140.
- **Open prices.** Opening prices now reach the marts. The opening moneyline comes from the
  moneyline's own book, and the opening total from the total's book.
- **Neutral sites.** Every game from July 2020 (the bubbles) is neutral, as is any game more than
  50 miles from the home team's city (e.g. the Raptors in Tampa in 2021). This feeds the
  home-court and home-ice fits.
- **Bias fit.** The totals-model bias is now fitted separately for regular season and playoffs.
- **CLV.** Bets placed at the close have no CLV, so close-placed candidates report open→close
  movement instead.
- **Trial counting.** The Phase 0 scan splits and a reviewer's exploratory open-line tries are
  logged and counted in Bonferroni m: NBA m = 42, NHL m = 14. The NHL run on broken prices is
  marked invalid in the trials log.
- **Bootstrap.** Deterministic, with 10,000 resamples.

**Paper forward test: NBA totals at the open (not a lead).** Recorded under the validator's
conditions:
- **Rule:** regular season only. Bet the over or under when the predicted total (bias code frozen
  at commit d56fbcd) differs from the opening total by ≥ 12 points.
- **Price:** both legs within −135..+115, from the spine's book priority as of d56fbcd.
- **Capture:** a timestamped price captured by our own pipeline after both teams' earlier games are
  final. Not ESPN's after-the-fact open field, whose timing is unverified.
- **Log:** picks written to an append-only log before tip-off, with the book.
- **Start:** counts from the day the capture is built. 2026-27 games already played don't count.
- **Pass:** ≥ 200 forward bets (2–3 seasons), bootstrap ROI interval above 0 at the actual price,
  median CLV above 0.

The evidence so far is one season. Regular-season results at t = 12:

| Season | Bets | ROI |
|---|---|---|
| 2024 | 99 | +17.6% |
| 2025 | 13 | +0.3% |
| 2026 | 27 | −15.4% |

Playoff totals stay out: since 2024 the model's playoff gap to the market has shifted by 6–12
points, so any correction designed now would itself be tuned on these seasons. The test can't
start until the pipelines load 2026-27: `nba.games` currently ends 2026-06-13.

## 2026-27 rules, team profiles, pregame lookup (Phase 5, 2026-11-09)

**Rules: none.** Only edges marked SHIP become rules, and Phase 4 shipped none.

| Rule group | NBA | NHL |
|---|---|---|
| BET WHEN | none | none |
| AUTO BET | none | none |
| NEVER BET | none | none |
| Totals | none (the regular-season open-totals model is a paper forward test only, see Phase 4) | none |

**Team profiles:** `main_marts.mart_nba_team_profiles` and `mart_nhl_team_profiles`.
- **Grain:** one row per (team, season the profile applies to). Each row uses only that team's
  games in the four seasons before, so it is safe to join to any game of that season.
- **Market:** ATS is the spread (NBA) or the standard ±1.5 puck line (NHL), at the actual price,
  with `historical_lines` at −110.
- **Columns:** overall and home/away × favourite/underdog cover% and ROI, seasons positive, an O/U
  lean (≥ 55% over or ≤ 45%), NHL moneyline win% and ROI, and a tier.
- **Tiers:** CFB's walk-forward v3 rules (macro `dbt/macros/team_profiles.sql`). Directional
  tiers need 2+ seasons in the window.
- **Tiers have no predictive value.** Betting each tier's team in the season the tier applies to
  (out of sample) loses roughly the vig. They are descriptive and are not a rule.

| Tier | NBA bets | NBA ROI | NHL bets | NHL ROI |
|---|---|---|---|---|
| STRONG | 274 | −4.0% | 102 | +3.2% (1 season) |
| NEUTRAL | 38,640 | −4.1% | 13,720 | −4.5% |
| FADE | 6,182 | −4.5% | 1,882 | −2.0% |
| STRONG_FADE | 314 | −8.2% | – | – |

Few teams reach a directional tier in any season: NBA 2027 has 3 FADE, the rest NEUTRAL; NHL 2027
has 5 FADE.

**Pregame lookups:** `scripts/nba_pregame_lookup.py` and `scripts/nhl_pregame_lookup.py`, modeled
on `scripts/pregame_lookup.py`.
- **Usage:** `--home --away [--date] [--spread | --puckline] [--total] [--ml HOME AWAY]`; NHL also
  takes `--home-goalie` / `--away-goalie`. Teams are given by code or name.
- **Report:** team form over the last 5 / last 10 / season / prior season, starting goalies
  (NHL), schedule spots, team profiles, and the ratings or xG model vs the market. Then the rules
  section (none fire) and the bottom line, which is NO BET.
- **NBA paper test:** a game that meets the paper forward test is shown as a paper entry, never a bet.
- **Shared code:** `scripts/nba_nhl_lookup_common.py`.
- **As-of date:** every value is computed from games before the game date with the mart's
  definitions. For a past game the lookup cross-checks itself against
  `mart_*_game_features` and prints the result.
- **Tested on 5 past games each:** NBA 2025-03-08 GSW-DET, 2025-01-15 MIL-ORL and DEN-HOU,
  2025-01-23 IND-SAS (Paris, neutral), 2012-02-15 BOS-DET (`historical_lines`); NHL 2025 STL-CHI
  (shootout), STL-CBJ, VAN-TOR, CGY-SEA (OT), MIN-BUF. Every report matched the mart (13 NBA /
  10 NHL values each). An upcoming game has no mart row and uses each team's most recent starter,
  marked PROBABLE.

## Daily picks and grading (Phase 6, 2026-11-09)

**2026-27 loaded:** NBA 154 and NHL 284 completed games through 2026-11-09, all with lines;
stats match 154/154 and 282/284. The daily sync's NBA/NHL steps were added to the main
checkout on 2026-11-09, after that day's 09:00 run, so the loads ran by hand once:
`espn_odds_pipeline.py --league {nba,nhl} --season 2027`, `nba_stats_pipeline.py --season 2027`,
`nhl_stats_pipeline.py --season 2027 --goalies`. Crosswalks were unchanged.

**Flow** (same as CFB: picks JSON → graded in place → DLT → DuckDB → mart):

| Step (daily_sync) | What it does |
|---|---|
| `espn_odds_nba_nhl`, `nba_stats_pipeline`, `nhl_stats_pipeline` | finals and closing lines for the last 3 days, current lines for the next 2, team stats |
| `nba_nhl_grade_picks` | `scripts/nba_nhl_grade_picks.py`: fills in the final score, status and closing line for every logged game; for a bet or paper entry, outcome, P&L at the captured price, and CLV (close vs captured line, points toward the bet). Idempotent; canceled / postponed games are marked, never graded |
| `nba_nhl_generate_picks` | `scripts/nba_nhl_generate_picks.py`: writes `data/bets/{nba,nhl}/history/<date>.json` with the line, price, book and capture time of every game. Verdict NO_BET (no validated rule); NBA games also carry the paper totals test. Append-only: a game keeps its first capture. Games already started are flagged `captured_after_start` and never paper-eligible |
| `nba_nhl_live_picks_pipeline` | `pipelines/nba_nhl_live_picks_pipeline.py` → `nba.live_picks`, `nhl.live_picks` (merge on game_id) |
| `notify_nba_nhl` | `scripts/notify.py nba-nhl`: ntfy push listing the day's bets and paper entries; quiet when there are none |
| `dbt` | `mart_nba_live_picks`, `mart_nhl_live_picks`: per season, games logged and graded, bets, paper entries, record, ROI and CLV |

The paper test (`nba_totals_open_v1`) uses the line our own run captures at about 09:00 ET,
after the previous night's games are final, as the validator required. It fires on a 12-point
gap with both prices within −135..+115, regular season only.
On 2026-11-10 the gaps were +1.6 to +8.5, so there were no entries.

## Degenerates Corner slate (Phase 7, 2026-11-10)

`/nba` and `/nhl` in the web app (sidebar → Degenerates Corner) render one shared component,
`web/components/ProSlate.tsx`, from two API routes in `api/routers/nba_nhl.py`:

| Route | Returns |
|---|---|
| `GET /api/nba-nhl/{league}/slate?date=YYYY-MM-DD` | one day's logged games (default: today, Eastern): line, prices and book as captured, verdict and `rules_fired`, the NBA paper entry, and once graded the final and closing line; plus `previous_date` / `next_date` |
| `GET /api/nba-nhl/{league}/record?season=` | season to date (default: latest logged): games logged and graded, bets, paper record, ROI, CLV, beat-close %, and one row per day |
| `GET /api/nba-nhl/{league}/dates` | every logged date |

The routes read `data/bets/{league}/history/*.json` directly, not the DuckDB tables, so the page is
current right after the morning generate and grade steps (the API keeps a read-only connection
opened at startup). The record uses the same definitions as `mart_{league}_live_picks`.
`ONS_BETS_DIR` points them at another folder (tests; dev servers on scratch picks). The page takes
`?date=` for a past slate. Times are Mountain, as on the CFB slate.

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

1. ~~dbt staging + team crosswalk seeds; join ESPN ↔ NBA stats ↔ historical lines, ESPN ↔ MoneyPuck ↔ goalies.~~ Done in Phase 2 (above).
2. ~~Rolling pregame features with no lookahead: NBA net rating / four factors (last 10, season-to-date), rest, travel; NHL xG% 5v5, PP/PK xG, starter GSAx, rest.~~ Done in Phase 3 (above).
3. ~~Efficiency-gap vs line edges (the PPA-gap analogue), validated cross-season like `cfb_edge_validation.py`.~~ Done in Phase 4 (above): no edge survived.
