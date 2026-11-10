-- Intermediate: NHL pregame xG features, one row per (nhl_game_id, team).
--
-- Built on MoneyPuck (stg_nhl__moneypuck_team_games), pivoting its situations into
-- one team-game row: 5v5 xGF / xGA, shot attempts (Corsi), high-danger shots;
-- 5on4 xGF and ice time (power play); 4on5 xGA and ice time (penalty kill);
-- all-situations goals and xG. Windows:
--   _l10  previous 10 games of the season,
--   _std  all previous games of the season (regular season + playoffs),
--   _prior the whole previous season.
-- Windows end at 1 PRECEDING. Formulas: macros/nba_nhl_features.sql -> nhl_xg_metrics.

with mp as (
    select * from {{ ref('stg_nhl__moneypuck_team_games') }}
),

team_games as (
    select
        nhl_game_id,
        team_code,
        any_value(season)                                                   as season,
        any_value(game_date)                                                as game_date,
        max(xgoalsfor)          filter (where situation = '5on5')           as xgf_5v5,
        max(xgoalsagainst)      filter (where situation = '5on5')           as xga_5v5,
        max(shotattemptsfor)    filter (where situation = '5on5')           as cf_5v5,
        max(shotattemptsagainst) filter (where situation = '5on5')          as ca_5v5,
        max(highdangershotsfor) filter (where situation = '5on5')           as hdf_5v5,
        max(highdangershotsagainst) filter (where situation = '5on5')       as hda_5v5,
        max(xgoalsfor)          filter (where situation = '5on4')           as xgf_pp,
        max(icetime)            filter (where situation = '5on4')           as toi_pp,
        max(xgoalsagainst)      filter (where situation = '4on5')           as xga_pk,
        max(icetime)            filter (where situation = '4on5')           as toi_pk,
        max(goalsfor)           filter (where situation = 'all')            as gf_all,
        max(xgoalsfor)          filter (where situation = 'all')            as xgf_all,
        max(xgoalsagainst)      filter (where situation = 'all')            as xga_all
    from mp
    group by nhl_game_id, team_code
),

prior as (
    select
        team_code,
        season + 1                                                          as season,
        {{ nhl_xg_metrics('', 'prior') }}
    from team_games
    group by team_code, season
)

select
    tg.nhl_game_id,
    tg.team_code,
    tg.season,
    tg.game_date,
    {{ nhl_xg_metrics('over w10', 'l10') }},
    {{ nhl_xg_metrics('over wstd', 'std') }},
    {% for m in nhl_xg_metric_names() -%}
    p.{{ m }}_prior{{ "," if not loop.last }}
    {% endfor %}
from team_games tg
left join prior p
  on p.team_code = tg.team_code
 and p.season = tg.season
window
    w10  as (partition by tg.team_code, tg.season order by tg.game_date, tg.nhl_game_id
             rows between 10 preceding and 1 preceding),
    wstd as (partition by tg.team_code, tg.season order by tg.game_date, tg.nhl_game_id
             rows between unbounded preceding and 1 preceding)
