-- mart_nba_team_profiles
--
-- Walk-forward NBA team ATS profiles: one row per (team, season the profile applies
-- to), built only from the team's games in the four seasons before it. Overall and
-- home / away x favourite / underdog ATS at the actual price, seasons positive, O/U
-- lean, and a CFB-style tier. Descriptive only: no team-level rule has been validated.
-- Logic and tier rules: macros/team_profiles.sql.

{{ team_profiles('nba') }}
