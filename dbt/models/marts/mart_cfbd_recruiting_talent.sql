-- mart_cfbd_recruiting_talent
--
-- 4-year weighted recruiting composite per team per season.
-- Reflects actual roster talent better than single-year class ranking.
--
-- Weights by class year (contribution to current roster):
--   Freshmen  (recruited year N):   10%
--   Sophomores (recruited year N-1): 20%
--   Juniors    (recruited year N-2): 30%
--   Seniors    (recruited year N-3): 40%
--
-- A team with consistent top-10 recruiting will score higher than
-- a team that had one great class. Portal/transfer effects are not
-- captured but the 4-year blend smooths single-year noise.

with recruiting as (
    select year, team, points, rank
    from cfbd.recruiting_rankings
    where points is not null
),

weighted as (
    select
        curr.team,
        curr.year                                           as season,

        -- Raw class points each year
        curr.points                                         as class_points_yr0,
        coalesce(yr1.points, curr.points)                   as class_points_yr1,
        coalesce(yr2.points, curr.points)                   as class_points_yr2,
        coalesce(yr3.points, curr.points)                   as class_points_yr3,

        -- 4-year weighted composite
        -- Seniors(40%) + Juniors(30%) + Sophomores(20%) + Freshmen(10%)
        round(
            0.10 * curr.points +
            0.20 * coalesce(yr1.points, curr.points) +
            0.30 * coalesce(yr2.points, curr.points) +
            0.40 * coalesce(yr3.points, curr.points),
            2
        )                                                   as weighted_talent,

        -- Single-year for comparison
        curr.points                                         as single_year_points,
        curr.rank                                           as single_year_rank

    from recruiting curr
    left join recruiting yr1
        on yr1.team = curr.team and yr1.year = curr.year - 1
    left join recruiting yr2
        on yr2.team = curr.team and yr2.year = curr.year - 2
    left join recruiting yr3
        on yr3.team = curr.team and yr3.year = curr.year - 3
),

-- Rank teams by weighted talent within each season
ranked as (
    select
        *,
        rank() over (
            partition by season
            order by weighted_talent desc
        ) as weighted_rank,

        -- Percentile within season (0-100, 100 = best)
        round(
            percent_rank() over (
                partition by season
                order by weighted_talent asc
            ) * 100, 1
        ) as talent_percentile

    from weighted
)

select * from ranked
order by season desc, weighted_rank asc
