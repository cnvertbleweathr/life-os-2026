-- Staging: MoneyPuck team-game stats (nhl.moneypuck_team_games)
-- One row per (game, team, situation) for all / 5on5 / 5on4 / 4on5, 2008-09 on.
-- Data from MoneyPuck.com (free for non-commercial use, credit MoneyPuck).
--
-- season is the END year (MoneyPuck's raw season is the start year).
-- nhl_game_id is the NHL game id, the same key as nhl.goalie_games.
-- Teams carry canonical codes (dbt/seeds/nhl_team_crosswalk.csv; L.A -> LAK,
-- ATL -> WPG, ARI -> UTA ...).
--
-- Home side: MoneyPuck labels 115 Phoenix home games in 2011-12 to 2013-14 as AWAY
-- for both teams (every one involves ARI; ARI otherwise has no HOME rows in those
-- seasons). When a game has no single HOME side, the ARI side is home. Any other
-- game without one gets a null is_home, which the not_null test catches.
-- icetime is seconds; > 3600 means overtime. The shootout goal isn't in goals.

with src as (
    select * from {{ source('nhl', 'moneypuck_team_games') }}
),

home_count as (
    select gameid, count(*) filter (where home_or_away = 'HOME') as n_home
    from src
    where situation = 'all'
    group by 1
)

select
    s.gameid                                           as nhl_game_id,
    cast(s.season_end as integer)                      as season,
    case when s.playoffgame = 1 then 3 else 2 end      as season_type,
    cast(s.game_date as date)                          as game_date,
    t.team_code,
    o.team_code                                        as opp_code,
    case
        when hc.n_home = 1 then s.home_or_away = 'HOME'
        when hc.n_home = 0 and 'ARI' in (s.playerteam, s.opposingteam) then s.playerteam = 'ARI'
    end                                                as is_home,
    s.situation,
    s.* exclude (gameid, season, season_end, playoffgame, game_date, gamedate, team, name,
                 playerteam, opposingteam, home_or_away, position, situation, loaded_at,
                 _dlt_load_id, _dlt_id)
from src s
join home_count hc using (gameid)
join {{ ref('nhl_team_crosswalk') }} t
  on {{ team_xwalk_join('t', 'moneypuck', 's.playerteam', 's.season_end') }}
join {{ ref('nhl_team_crosswalk') }} o
  on {{ team_xwalk_join('o', 'moneypuck', 's.opposingteam', 's.season_end') }}
