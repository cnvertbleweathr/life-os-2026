-- Staging: ESPN NHL games (nhl.games, pipelines/espn_odds_pipeline.py)
-- One row per game between two NHL franchises, 2019-20 on, canonical team codes
-- (dbt/seeds/nhl_team_crosswalk.csv), Eastern game_date, went_ot and shootout.
-- A shootout win counts as one goal in ESPN's score. Exhibitions (All-Star 3-on-3,
-- 4 Nations Face-Off) drop out; unplayed games stay with completed = false.
-- Logic shared with NBA: macros/espn_staging.sql.

{{ espn_games('nhl') }}
