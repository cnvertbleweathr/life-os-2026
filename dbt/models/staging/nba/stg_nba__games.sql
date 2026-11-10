-- Staging: ESPN NBA games (nba.games, pipelines/espn_odds_pipeline.py)
-- One row per game between two NBA franchises, 2013-14 on, canonical team codes
-- (dbt/seeds/nba_team_crosswalk.csv), Eastern game_date. Exhibitions (All-Star,
-- Rising Stars, World v USA) drop out; unplayed games stay with completed = false.
-- The NBA Cup final is a real game here but isn't in nba_api's regular season.
-- Logic shared with NHL: macros/espn_staging.sql.

{{ espn_games('nba') }}
