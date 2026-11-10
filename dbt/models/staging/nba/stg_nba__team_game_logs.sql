-- Staging: NBA team box scores (nba.team_game_logs, stats.nba.com LeagueGameLog)
-- One row per (game, team), 2007-08 on, regular season and playoffs.
-- game_date is the stats.nba.com date (US/Eastern). Teams carry canonical codes
-- (dbt/seeds/nba_team_crosswalk.csv); the opponent maps through its nba_api
-- abbreviation. Possessions and ratings are derived downstream.

select
    l.game_id                                       as nba_game_id,
    cast(l.season as integer)                       as season,
    case l.season_type when 'Regular Season' then 2
                       when 'Playoffs' then 3 end   as season_type,
    cast(l.game_date as date)                       as game_date,
    t.team_code,
    o.team_code                                     as opp_code,
    l.team_id                                       as nba_team_id,
    l.is_home,
    l.wl,
    cast(l.min as integer)                          as minutes,
    l.pts, l.fgm, l.fga, l.fg3m, l.fg3a, l.ftm, l.fta,
    l.oreb, l.dreb, l.reb, l.ast, l.stl, l.blk, l.tov, l.pf,
    l.plus_minus
from {{ source('nba', 'team_game_logs') }} l
join {{ ref('nba_team_crosswalk') }} t
  on {{ team_xwalk_join('t', 'nba_api_id', 'l.team_id', 'l.season') }}
join {{ ref('nba_team_crosswalk') }} o
  on {{ team_xwalk_join('o', 'nba_api_abbr', 'l.opp_abbr', 'l.season') }}
