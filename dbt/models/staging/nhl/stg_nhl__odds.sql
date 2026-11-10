-- Staging: one chosen ESPN line per NHL game (nhl.odds)
--
-- home_spread is the puck line (+-1.5; < 0 when home is favoured).
-- Choice rule (full text in macros/espn_staging.sql -> espn_odds):
--   books only (dbt/seeds/nba_nhl_odds_providers.csv, keyed on league + provider_id);
--   per market, the close snapshot when present (2023-24 on), else the item-level
--   final pregame line; prices from the same snapshot;
--   rows whose puck line agrees with the ML favourite first (about 2% of NHL rows
--   put -1.5 on the ML underdog), then seed priority (DraftKings > ESPN BET > MGM >
--   Caesars > Bet365 ...).
-- line_source = 'espn:<book>:<close|final>'.

{{ espn_odds('nhl') }}
