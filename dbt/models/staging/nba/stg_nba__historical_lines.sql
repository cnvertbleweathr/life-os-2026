-- Staging: NBA historical closing lines (nba.historical_lines)
-- SBR via kyleskom, 2007-08 to January 2026, one line per game, no spread prices
-- (backtests price these at a flat -110). The loader rebuilt the spread sign from
-- the moneyline favourite: home_spread < 0 when home is favoured.
-- Full team names map through dbt/seeds/nba_team_crosswalk.csv (source
-- 'historical_lines'); the source keeps "Charlotte Bobcats" through 2021-22 and
-- uses "New Orleans Pelicans" for the Hornets years.

select
    cast(l.season as integer)          as season,
    cast(l.game_date as date)          as game_date,
    h.team_code                        as home_team,
    a.team_code                        as away_team,
    l.home_spread,
    l.total,
    l.home_ml,
    l.away_ml,
    cast(l.home_margin as integer)     as home_margin,
    cast(l.total_points as integer)    as total_points,
    l.home_ats_margin,
    cast(l.home_days_rest as integer)  as home_days_rest,
    cast(l.away_days_rest as integer)  as away_days_rest,
    l.source
from {{ source('nba', 'historical_lines') }} l
join {{ ref('nba_team_crosswalk') }} h
  on {{ team_xwalk_join('h', 'historical_lines', 'l.home_team', 'l.season') }}
join {{ ref('nba_team_crosswalk') }} a
  on {{ team_xwalk_join('a', 'historical_lines', 'l.away_team', 'l.season') }}
