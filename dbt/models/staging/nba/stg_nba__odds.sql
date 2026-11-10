-- Staging: one chosen ESPN line per NBA game (nba.odds)
--
-- Choice rule (full text in macros/espn_staging.sql -> espn_odds):
--   books only (dbt/seeds/nba_nhl_odds_providers.csv, keyed on league + provider_id);
--   per market, the close snapshot when present (2023-24 on), else the item-level
--   final pregame line; prices from the same snapshot;
--   rows whose spread agrees with the ML favourite first, then seed priority
--   (DraftKings > ESPN BET > MGM > Caesars ... ; 5Dimes > Pinnacle > BetOnline >
--   Bovada ... in 2013-14 to 2016-17).
-- line_source = 'espn:<book>:<close|final>'. home_spread < 0 when home is favoured.

{{ espn_odds('nba') }}
