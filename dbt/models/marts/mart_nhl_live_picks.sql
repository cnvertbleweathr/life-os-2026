-- mart_nhl_live_picks
--
-- Season summary of nhl.live_picks: games logged and graded, bets (none until a rule
-- is validated) and the paper forward test's record, ROI and CLV.
-- Logic: macros/nba_nhl_live_picks.sql. Source: pipelines/nba_nhl_live_picks_pipeline.py.

{{ nba_nhl_live_picks('nhl') }}
