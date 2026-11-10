-- Every season of the NBA spine matches at least 98% of its ESPN games to an
-- nba_api box score (nba_game_id). Seasons built from nba_api itself match by
-- construction. Returns the failing seasons.

select
    season,
    count(*)                                     as espn_games,
    count(nba_game_id)                           as matched,
    count(nba_game_id) * 1.0 / count(*)          as match_rate
from {{ ref('int_nba__game_spine') }}
where game_source = 'espn'
group by season
having count(nba_game_id) * 1.0 / count(*) < 0.98
