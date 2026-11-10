-- Intermediate: the starting goalie for each (nhl_game_id, team), 2019-20 on, with
-- his form going into the game: goals saved above expected (GSAx) and save% over
-- his previous 10 starts and his previous starts this season.
--
-- The starter is the actual starter (stg_nhl__goalie_games.starter). Usually known
-- before puck drop, not always when the line is set: report goalie-based edges with
-- and without these columns (see the nba-nhl-ats skill).
--
-- GSAx per start is approximate: MoneyPuck has team xG, not goalie xG, so a goalie
-- is charged his share of the team's all-situations xG against by ice time
--   gsax = team_xga * (his toi / all goalies' toi that game) - goals_against.
-- Team xGA includes empty-net chances while the boxscore's goals against does not
-- count empty-net goals, which nudges GSAx up for teams that pull the goalie a lot.
-- Windows run over his starts only, end at 1 PRECEDING, and follow him across teams.

with goalies as (
    select
        g.*,
        sum(g.toi_seconds) over (partition by g.nhl_game_id, g.team_code)    as team_goalie_toi
    from {{ ref('stg_nhl__goalie_games') }} g
),

team_xga as (
    select nhl_game_id, team_code, xgoalsagainst as xga_all
    from {{ ref('stg_nhl__moneypuck_team_games') }}
    where situation = 'all'
),

starts as (
    select
        g.nhl_game_id,
        g.team_code,
        g.season,
        g.game_date,
        g.player_id,
        g.goalie_name,
        g.shots_against,
        g.saves,
        g.goals_against,
        x.xga_all * g.toi_seconds / nullif(g.team_goalie_toi, 0) - g.goals_against as gsax
    from goalies g
    left join team_xga x using (nhl_game_id, team_code)
    where g.starter
)

select
    nhl_game_id,
    team_code,
    season,
    game_date,
    player_id                                                    as starter_id,
    goalie_name                                                  as starter_name,
    count(*)            over w10                                 as starter_starts_l10,
    sum(gsax)           over w10                                 as starter_gsax_l10,
    sum(saves) over w10 / nullif(sum(shots_against) over w10, 0) as starter_sv_pct_l10,
    count(*)            over wstd                                as starter_starts_std,
    sum(gsax)           over wstd                                as starter_gsax_std,
    sum(saves) over wstd / nullif(sum(shots_against) over wstd, 0) as starter_sv_pct_std
from starts
window
    w10  as (partition by player_id order by game_date, nhl_game_id
             rows between 10 preceding and 1 preceding),
    wstd as (partition by player_id, season order by game_date, nhl_game_id
             rows between unbounded preceding and 1 preceding)
