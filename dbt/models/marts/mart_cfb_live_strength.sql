-- mart_cfb_live_strength.sql
--
-- Phase C of the Quality-of-Win/SOS system (design v5).
-- One row per (team, season, week) -- the pregame rating entering that week.
--
-- TWO PERMANENTLY SEPARATE TIME SERIES, per design v5 core principle:
--
-- 1. live_off_strength / live_def_strength
--    Updates from FOOTBALL performance only: per-game PPA from cfbd.ppa_games.
--    The betting market line never enters this series update rule.
--    Initializes at preseason_off_rating_z / preseason_def_rating_z (Phase A v1).
--
-- 2. market_outperformance_ema
--    Updates from MARKET SURPRISE only: spread_residual from Phase B mart.
--    Football stats never enter this series update rule.
--    Initializes at 0 (measures only in-season market-relative performance).
--
-- Parameters: rho=0.85 (decay per game), k=0.10 (learning rate).
-- Decay is per-game not per-calendar-week: bye weeks carry prior rating
-- forward unchanged since no new information arrived.

with

-- Deduplicate Phase B market residuals to one row per (team, game_id).
-- mart_cfb_game_market_residual has one row per provider per game per team,
-- causing 3-4x multiplication when joined. Take the average spread_residual
-- across providers as the consensus value for each game.
market_residual_dedup as (
    select
        team,
        season,
        week,
        avg(spread_residual) as spread_residual
    from main_marts.mart_cfb_game_market_residual
    group by team, season, week
),

game_sequence as (
    -- Ordered game sequence per team-season with residuals attached
    select
        p.team,
        p.season,
        p.week,
        p.game_id,
        row_number() over (
            partition by p.team, p.season
            order by p.week
        ) as game_num,

        -- Football residual: game PPA vs prior-season baseline (z-scored)
        -- Positive = outperformed prior-season average this game
        case when s.season_off_std > 0 then
            (coalesce(p.off_ppa, 0) - coalesce(a_prior.off_ppa, 0))
            / s.season_off_std
        else 0 end as off_residual_z,

        -- Defense: sign-reversed (lower def_ppa allowed = better performance)
        case when s.season_def_std > 0 then
            (coalesce(a_prior.def_ppa, 0) - coalesce(p.def_ppa, 0))
            / s.season_def_std
        else 0 end as def_residual_z,

        -- Market residual: spread_residual from Phase B mart (standardized)
        coalesce(mr.spread_residual, 0)
            / nullif(season_mr.season_spread_std, 0) as market_residual_z

    from cfbd.ppa_games p

    -- Prior-season baseline for football residual
    left join cfbd.advanced_stats a_prior
        on a_prior.team   = p.team
        and a_prior.season = p.season - 1

    -- Season-level standardization for football residuals
    left join (
        select
            season,
            stddev(off_ppa) as season_off_std,
            stddev(def_ppa) as season_def_std
        from cfbd.ppa_games
        where season_type = 'regular'
          and off_ppa is not null
          and def_ppa is not null
        group by season
    ) s on s.season = p.season

    -- Market residual from Phase B (deduplicated to one row per team/game)
    left join market_residual_dedup mr
        on mr.team   = p.team
        and mr.season = p.season
        and mr.week   = p.week

    -- Season-level standardization for market residuals (from dedup CTE)
    left join (
        select
            season,
            stddev(spread_residual) as season_spread_std
        from market_residual_dedup
        group by season
    ) season_mr on season_mr.season = p.season

    where p.season_type = 'regular'
      and p.season between 2021 and 2025
),

-- Pre-aggregate the exponential decay contributions.
-- For each game (at_game_num), sum all prior games' weighted contributions.
-- contribution from game i at time t = k * residual_i * rho^(t - i)
-- This avoids the GROUP BY issue with window functions over joined tables.
off_deltas as (
    select
        current_g.team,
        current_g.season,
        current_g.game_num as at_game_num,
        sum(
            0.10 * past_g.off_residual_z
            * pow(0.85, current_g.game_num - past_g.game_num)
        ) as off_delta
    from game_sequence current_g
    join game_sequence past_g
        on past_g.team   = current_g.team
        and past_g.season = current_g.season
        and past_g.game_num < current_g.game_num
    group by current_g.team, current_g.season, current_g.game_num
),

def_deltas as (
    select
        current_g.team,
        current_g.season,
        current_g.game_num as at_game_num,
        sum(
            0.10 * past_g.def_residual_z
            * pow(0.85, current_g.game_num - past_g.game_num)
        ) as def_delta
    from game_sequence current_g
    join game_sequence past_g
        on past_g.team   = current_g.team
        and past_g.season = current_g.season
        and past_g.game_num < current_g.game_num
    group by current_g.team, current_g.season, current_g.game_num
),

market_deltas as (
    select
        current_g.team,
        current_g.season,
        current_g.game_num as at_game_num,
        sum(
            0.10 * past_g.market_residual_z
            * pow(0.85, current_g.game_num - past_g.game_num)
        ) as market_delta
    from game_sequence current_g
    join game_sequence past_g
        on past_g.team   = current_g.team
        and past_g.season = current_g.season
        and past_g.game_num < current_g.game_num
    group by current_g.team, current_g.season, current_g.game_num
),

live_ratings as (
    select
        gs.team,
        gs.season,
        gs.week,
        gs.game_num,
        -- Initialize from Phase A preseason anchor, then add accumulated delta
        coalesce(pa.preseason_off_rating_z, 0) + coalesce(od.off_delta, 0)
            as live_off_strength,
        coalesce(pa.preseason_def_rating_z, 0) + coalesce(dd.def_delta, 0)
            as live_def_strength,
        -- Market EMA initializes at 0 (no preseason anchor)
        coalesce(md.market_delta, 0)
            as market_outperformance_ema,
        coalesce(pa.preseason_off_rating_z, 0) as preseason_off,
        coalesce(pa.preseason_def_rating_z, 0) as preseason_def
    from game_sequence gs
    left join main_marts.mart_cfb_preseason_quality pa
        on pa.team   = gs.team
        and pa.season = gs.season
    left join off_deltas od
        on od.team   = gs.team
        and od.season = gs.season
        and od.at_game_num = gs.game_num
    left join def_deltas dd
        on dd.team   = gs.team
        and dd.season = gs.season
        and dd.at_game_num = gs.game_num
    left join market_deltas md
        on md.team   = gs.team
        and md.season = gs.season
        and md.at_game_num = gs.game_num
)

select
    team,
    season,
    week,
    round(live_off_strength, 4)         as live_off_strength,
    round(live_def_strength, 4)         as live_def_strength,
    round(market_outperformance_ema, 4) as market_outperformance_ema,
    round(live_off_strength - preseason_off, 4) as off_vs_preseason,
    round(live_def_strength - preseason_def, 4) as def_vs_preseason,
    round(
        percent_rank() over (partition by season, week order by live_off_strength) * 100,
        1
    ) as live_off_percentile,
    round(
        percent_rank() over (partition by season, week order by live_def_strength) * 100,
        1
    ) as live_def_percentile

from live_ratings
order by season, team, week
