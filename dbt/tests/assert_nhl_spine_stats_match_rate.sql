-- Every season of the NHL spine matches at least 98% of its ESPN games to a
-- MoneyPuck game (nhl_game_id, also the goalie_games key). Seasons built from
-- MoneyPuck itself match by construction. Returns the failing seasons.

select
    season,
    count(*)                                     as espn_games,
    count(nhl_game_id)                           as matched,
    count(nhl_game_id) * 1.0 / count(*)          as match_rate
from {{ ref('int_nhl__game_spine') }}
where game_source = 'espn'
group by season
having count(nhl_game_id) * 1.0 / count(*) < 0.98
