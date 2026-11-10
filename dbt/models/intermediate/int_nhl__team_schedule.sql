-- Intermediate: NHL schedule features, one row per (game_key, team) from
-- int_nhl__game_spine: days rest, back-to-back, 3-in-4, games in the previous
-- 7 days, road-trip game number, travel miles from the previous game's site, and
-- puck-line record / average margin vs the puck line over the previous 10 games
-- (2019-20 on; no lines before). All use only earlier games.
-- Definitions: macros/nba_nhl_features.sql -> team_schedule.

{{ team_schedule('nhl') }}
