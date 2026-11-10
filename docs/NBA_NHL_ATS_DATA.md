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
3. Efficiency-gap vs line edges (the PPA-gap analogue), validated cross-season like `cfb_edge_validation.py`.
