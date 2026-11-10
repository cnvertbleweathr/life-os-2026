-- No game appears twice in either spine: one row per (date, home, away), and the
-- pre-ESPN and ESPN eras don't overlap. Returns the duplicated games.

select 'nba' as league, game_date, home_team, away_team, count(*) as n
from {{ ref('int_nba__game_spine') }}
group by all
having count(*) > 1

union all

select 'nhl', game_date, home_team, away_team, count(*)
from {{ ref('int_nhl__game_spine') }}
group by all
having count(*) > 1

union all

select league, null, null, null, count(distinct game_source)
from (
    select 'nba' as league, season, game_source from {{ ref('int_nba__game_spine') }}
    union all
    select 'nhl', season, game_source from {{ ref('int_nhl__game_spine') }}
)
group by league, season
having count(distinct game_source) > 1
