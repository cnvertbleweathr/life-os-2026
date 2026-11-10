-- Intermediate: NBA pregame box-score features, one row per (nba_game_id, team).
--
-- Built on the stats source (stg_nba__team_game_logs), so the windows count the
-- team's games that have a box score, whatever ESPN has. Each team-game carries the
-- team's possessions-based ratings, pace and four factors (for and against) over:
--   _l5 / _l10  the previous 5 / 10 games of the same season,
--   _std        all previous games of the season (regular season + playoffs),
--   _prior      the whole previous season (null in a franchise's first loaded season).
-- Windows end at 1 PRECEDING, so a game never sees itself. Formulas:
-- macros/nba_nhl_features.sql -> nba_box_metrics. games_* = games in the window.

with logs as (
    select * from {{ ref('stg_nba__team_game_logs') }}
),

team_games as (
    select
        t.nba_game_id,
        t.season,
        t.game_date,
        t.team_code,
        t.pts, t.fgm, t.fga, t.fg3m, t.fta, t.ftm, t.oreb, t.dreb, t.tov,
        t.minutes                                               as team_minutes,
        o.pts as opp_pts, o.fgm as opp_fgm, o.fga as opp_fga, o.fg3m as opp_fg3m,
        o.fta as opp_fta, o.ftm as opp_ftm, o.oreb as opp_oreb, o.dreb as opp_dreb,
        o.tov as opp_tov,
        0.5 * ((t.fga - t.oreb + t.tov + 0.44 * t.fta)
             + (o.fga - o.oreb + o.tov + 0.44 * o.fta))         as poss
    from logs t
    join logs o
      on o.nba_game_id = t.nba_game_id
     and o.team_code <> t.team_code
),

prior as (
    select
        team_code,
        season + 1                                              as season,
        {{ nba_box_metrics('', 'prior') }}
    from team_games
    group by team_code, season
)

select
    tg.nba_game_id,
    tg.team_code,
    tg.season,
    tg.game_date,
    {{ nba_box_metrics('over w5', 'l5') }},
    {{ nba_box_metrics('over w10', 'l10') }},
    {{ nba_box_metrics('over wstd', 'std') }},
    {% for m in nba_box_metric_names() -%}
    p.{{ m }}_prior{{ "," if not loop.last }}
    {% endfor %}
from team_games tg
left join prior p
  on p.team_code = tg.team_code
 and p.season = tg.season
window
    w5   as (partition by tg.team_code, tg.season order by tg.game_date, tg.nba_game_id
             rows between 5 preceding and 1 preceding),
    w10  as (partition by tg.team_code, tg.season order by tg.game_date, tg.nba_game_id
             rows between 10 preceding and 1 preceding),
    wstd as (partition by tg.team_code, tg.season order by tg.game_date, tg.nba_game_id
             rows between unbounded preceding and 1 preceding)
