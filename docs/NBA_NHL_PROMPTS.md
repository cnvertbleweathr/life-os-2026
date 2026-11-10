# NBA / NHL ATS — Claude Code prompts

Paste one phase per Claude Code session, run from `/Users/kg/life-os-2026`.
Each prompt stands alone. The `nba-nhl-ats` skill and the `ats-edge-validator`
agent (both in `.claude/`) carry the conventions, so the prompts stay short.

Every phase ends with a PR you merge. Don't start the next phase until the
previous one is merged.

| Phase | Output | Branch |
|---|---|---|
| 0 | Data layer landed, ESPN probe results recorded | `feat/nba-nhl-data` |
| 1 | Historical backfill loaded and profiled | `feat/nba-nhl-backfill` |
| 2 | dbt sources, team crosswalk seeds, game spine | `feat/nba-nhl-dbt-spine` |
| 3 | Pregame feature marts (no lookahead) | `feat/nba-nhl-features` |
| 4 | Edge discovery + walk-forward validation | `feat/nba-nhl-edges` |
| 5 | Rules, team profiles, pregame lookup | `feat/nba-nhl-rules` |
| 6 | Daily picks + grading | `feat/nba-nhl-live-picks` |
| 7 | Degenerates Corner NBA/NHL slate (UI) | `feat/nba-nhl-ui` |

---

## Phase 0 — Land the data layer

```
Use the nba-nhl-ats skill.

Land the NBA/NHL data layer from the patch at ~/Downloads/nba-nhl-ats-kit.patch.

1. Create branch feat/nba-nhl-data from an up-to-date main and apply the patch with
   `git am`. If it doesn't apply cleanly, stop and show me the conflict.
2. `uv sync`, then `uv run --with pytest pytest -q tests/test_nba_nhl_pipelines.py`.
3. Stop the API on :8000 if it's running. Run the ESPN probes and show me the full output:
     uv run python pipelines/espn_odds_pipeline.py --probe nba --date 2024-01-15
     uv run python pipelines/espn_odds_pipeline.py --probe nhl --date 2024-01-15
     uv run python pipelines/espn_odds_pipeline.py --probe nba --date 2019-01-15
     uv run python pipelines/espn_odds_pipeline.py --probe nhl --date 2019-01-15
     uv run python pipelines/espn_odds_pipeline.py --probe nba --date 2015-01-15
4. Compare each raw odds item with its parsed row. The parser was written without seeing
   live ESPN responses. If any field parses wrong (spread sign, open/close snapshots,
   prices, totals), fix parse_odds_item, add a test using the real JSON as a fixture
   (trim it), and re-probe.
5. Record in docs/NBA_NHL_ATS_DATA.md: the earliest season ESPN has lines for each
   league, which providers appear in each era, and whether open/close snapshots are real.
6. Run `uv run python pipelines/nba_stats_pipeline.py --lines-bootstrap` and
   `uv run python scripts/nba_ats_scan.py`. Home ATS should be about 49.5%.
7. Push the branch and open a PR. Restart the API.
```

## Phase 1 — Backfill and profile

```
Use the nba-nhl-ats skill. Branch feat/nba-nhl-backfill from main.

Backfill historical data. Stop the API first; restart it at the end.
Use the earliest ESPN line season recorded in docs/NBA_NHL_ATS_DATA.md as START.

  uv run python pipelines/nba_stats_pipeline.py --season 2008 --end-season 2026
  uv run python pipelines/nhl_stats_pipeline.py --season 2009 --end-season 2026
  uv run python pipelines/nhl_stats_pipeline.py --season START --end-season 2026 --goalies
  uv run python pipelines/espn_odds_pipeline.py --league nba --season START --end-season 2026
  uv run python pipelines/espn_odds_pipeline.py --league nhl --season START --end-season 2026

Run them one at a time and show me the tail of each. These are long; run each in the
background, check on it, and resume after a failure (the raw caches make reruns cheap).

Then write scripts/nba_nhl_data_profile.py (read-only DuckDB) that prints, per league
and season: games, games with any line, games with a close snapshot, providers seen,
null rates for key columns, and row counts for every stats table. Flag any season
whose game count is off (shortened 2012, 2013 NHL lockout, 2020 bubble, 2021).
Run it, paste the output into docs/NBA_NHL_ATS_DATA.md under "Coverage", and open a PR.
```

## Phase 2 — dbt sources, crosswalks, game spine

```
Use the nba-nhl-ats skill. Branch feat/nba-nhl-dbt-spine from main.

Build the dbt foundation for NBA and NHL. Read dbt/dbt_project.yml and two existing
CFB staging models first so the style matches.

1. dbt/models/staging/nba/_sources.yml and nhl/_sources.yml declaring every raw table,
   with unique/not_null tests on their keys.
2. Seeds (add `seed-paths: ["seeds"]` to dbt_project.yml): dbt/seeds/nba_team_crosswalk.csv
   and nhl_team_crosswalk.csv. One row per (canonical team code, source, source key,
   valid_from_season, valid_to_season), covering ESPN ids and abbreviations, nba_api
   abbreviations, historical_lines full names, NHL/MoneyPuck codes, and every relocation
   and rename listed in the skill. Build them by querying the distinct keys in each raw
   table, not from memory, and report any key that doesn't map.
3. Staging views: stg_nba__games, stg_nba__odds (one chosen line per game, with the rule
   for provider and snapshot documented in the model and a `line_source` column),
   stg_nba__historical_lines, stg_nba__team_game_logs, and the NHL equivalents. All
   carry canonical team codes and an Eastern-time game_date.
4. int_nba__game_spine and int_nhl__game_spine: one row per game with canonical teams,
   scores, the chosen closing line (ESPN where available, historical_lines before that
   for NBA), prices, and keys to the stats rows. Add tests: unique game, match rate to
   stats ≥ 98% per season (write it as a singular test), no duplicated games.
5. `dbt build --select +int_nba__game_spine +int_nhl__game_spine` and show me the output,
   plus match rates per season. Open a PR.
```

## Phase 3 — Pregame features (no lookahead)

```
Use the nba-nhl-ats skill. Branch feat/nba-nhl-features from main.

Build mart_nba_game_features and mart_nhl_game_features: one row per game, home and
away features computed only from games strictly before that game.

NBA, per team: possessions-based offensive/defensive/net rating (last 5, last 10,
season to date, prior season), four factors (eFG%, TOV%, ORB%, FT rate) for and
against, pace, days rest, back-to-back, 3-in-4, games in last 7, road-trip length,
travel distance from the previous game's arena (add an arena lat/lng seed), and ATS
record and average ATS margin over the last 10. Game-level: home-minus-away gaps for
each, a ratings-implied spread (net rating gap + a home-court constant fitted on
prior seasons only), and the difference from the market line.

NHL, per team: 5v5 xGF%, Corsi%, high-danger share, PP xGF/60 and PK xGA/60
(last 10, season to date, prior season), goals vs xG (finishing luck), rest and
back-to-back, and the starting goalie's GSAx and save% over his last 10 starts and
season to date. Game-level: gaps, an xG-implied win probability, and its difference
from the moneyline's no-vig probability.

Use window frames ending at 1 PRECEDING. Add a singular test that recomputes one
rolling feature for 20 random games from raw tables and compares. Write
scripts/feature_lookahead_check.py to do the same in Python and run it.
`dbt build --select +mart_nba_game_features +mart_nhl_game_features`. Open a PR.
```

## Phase 4 — Edge discovery and walk-forward validation

```
Use the nba-nhl-ats skill. Branch feat/nba-nhl-edges from main.

Write scripts/nba_edge_validation.py and scripts/nhl_edge_validation.py, modeled on
scripts/backtest_walk_forward.py and scripts/cfb_edge_validation.py (read both first).

- Read only from mart_nba_game_features / mart_nhl_game_features (DuckDB read-only).
- Candidate signals: the rating-implied spread vs market gap (the NBA analogue of the
  CFB PPA gap) at several thresholds, rest/travel spots, back-to-back combos, NHL xG
  gap vs moneyline, goalie mismatches, puck line underdogs +1.5 by price band, totals
  by pace/xG, and the early lead from docs/NBA_NHL_ATS_DATA.md (away team with 2+ more
  rest days).
- Walk forward: for each season S, choose thresholds on seasons < S, score on S. Report
  only out-of-sample numbers: n, win%, ROI at actual price (flat -110 only where no
  price exists), seasons positive, pushes, bootstrap 95% ROI interval, and CLV for 2024+.
- Log every split tested to data/betting/{league}_trials.jsonl.
- Print a ranked table and write it to data/betting/{league}_edges.csv.

Run both. Then run the ats-edge-validator agent on each script and its output, apply
its blocking fixes, rerun, and run the agent again until it says SHIP or REJECT for
each candidate. Summarize which edges survived in docs/NBA_NHL_ATS_DATA.md with the
agent's verdicts. Open a PR.
```

## Phase 5 — Rules, team profiles, pregame lookup

```
Use the nba-nhl-ats skill. Branch feat/nba-nhl-rules from main.

Only edges marked SHIP in docs/NBA_NHL_ATS_DATA.md become rules.

1. Write the 2026-27 rules in docs/NBA_NHL_ATS_DATA.md in the CFB format
   (BET WHEN / AUTO BET / NEVER BET / totals), each with out-of-sample n, win%, ROI,
   seasons positive.
2. Team profiles like cfbd.team_profiles: dbt marts mart_nba_team_profiles and
   mart_nhl_team_profiles with overall and situational ATS (home/away × fav/dog),
   ROI, seasons positive, O/U lean, tier (ELITE/STRONG/NEUTRAL/FADE/STRONG_FADE).
   Tiers need 2+ prior seasons, the same as CFB's walk-forward v3.
3. scripts/nba_pregame_lookup.py and scripts/nhl_pregame_lookup.py, modeled on
   scripts/pregame_lookup.py: --home --away --spread/--puckline --ml --total; print
   features, team profiles, which rules fire, and a bottom-line verdict.
4. Test both lookups on 5 past games each and show the output. Open a PR.
```

## Phase 6 — Daily picks and grading

```
Use the nba-nhl-ats skill. Branch feat/nba-nhl-live-picks from main.

Read scripts/generate_picks.py, scripts/grade_picks.py and pipelines/live_picks_pipeline.py
first, and follow the same flow: picks JSON → graded in place → DLT → DuckDB → mart.

- scripts/nba_nhl_generate_picks.py: for today's games (ESPN `current_*` lines from the
  daily sync), score with the rules and write data/bets/{league}/history/<date>.json,
  recording the line and price at pick time.
- Extend grading to NBA/NHL using final scores, and record closing line and CLV.
- Load into nba.live_picks / nhl.live_picks; marts mart_nba_live_picks / mart_nhl_live_picks.
- Add daily_sync steps after espn_odds_nba_nhl, and an ntfy notification with the day's
  picks using scripts/notify.py.
- Dry-run against yesterday and show the output. Open a PR.
```

## Phase 7 — Degenerates Corner slate (UI)

```
Use the nba-nhl-ats skill for data and follow CLAUDE.md's design workflow (impeccable,
Playwright in light and dark at 1440×900 and 390×844).

Branch feat/nba-nhl-ui from main. Add FastAPI routes for today's NBA/NHL slate (games,
lines, fired rules, picks) and season-to-date pick record, then add NBA and NHL to
Degenerates Corner alongside CFB, using existing components. Use scripts/dev.sh for the
dev servers; never touch the production build. Screenshot, `/impeccable audit` the route,
and open a PR with the screenshots.
```
