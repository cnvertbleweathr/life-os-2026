-- Intermediate: NBA schedule features, one row per (game_key, team) from
-- int_nba__game_spine: days rest, back-to-back, 3-in-4, games in the previous
-- 7 days, road-trip game number, travel miles from the previous game's site, and
-- ATS record / average ATS margin over the previous 10 games of the season.
-- All use only earlier games (lag / windows ending at 1 PRECEDING).
-- Definitions: macros/nba_nhl_features.sql -> team_schedule.

{{ team_schedule('nba') }}
