-- Staging: NHL goalie game lines (nhl.goalie_games, NHL API boxscores, 2019-20 on)
-- One row per (game, goalie). starter is the actual starter; treat it as known
-- pregame, but report goalie-based edges without it too (see the nba-nhl-ats skill).
-- nhl_game_id matches stg_nhl__moneypuck_team_games. season is the end year,
-- from the game id (2023020001 -> 2024). toi converted from MM:SS to seconds.

select
    g.game_id                                                    as nhl_game_id,
    cast(left(g.game_id, 4) as integer) + 1                      as season,
    case substr(g.game_id, 5, 2) when '02' then 2 when '03' then 3 end as season_type,
    cast(g.game_date as date)                                    as game_date,
    t.team_code,
    o.team_code                                                  as opp_code,
    g.is_home,
    g.player_id,
    g.name                                                       as goalie_name,
    coalesce(g.starter, false)                                   as starter,
    try_cast(split_part(g.toi, ':', 1) as integer) * 60
      + try_cast(split_part(g.toi, ':', 2) as integer)           as toi_seconds,
    g.shots_against,
    g.saves,
    g.goals_against,
    g.save_pct,
    g.decision
from {{ source('nhl', 'goalie_games') }} g
join {{ ref('nhl_team_crosswalk') }} t
  on {{ team_xwalk_join('t', 'nhl_api', 'g.team', 'cast(left(g.game_id, 4) as integer) + 1') }}
join {{ ref('nhl_team_crosswalk') }} o
  on {{ team_xwalk_join('o', 'nhl_api', 'g.opponent', 'cast(left(g.game_id, 4) as integer) + 1') }}
