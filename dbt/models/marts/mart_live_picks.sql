-- mart_live_picks.sql
--
-- Aggregates cfbd.live_picks (loaded by pipelines/live_picks_pipeline.py
-- from data/bets/history/*.json) into the season-level summary the CFB
-- page's Live Tracker banner needs: graded picks, record, win rate, ROI.
--
-- Mirrors mart_cfbd_edge_factors' cover-rate math (push games excluded
-- from win-rate %, included in games-count) so live and backtest numbers
-- stay comparable -- same convention, two tables, not two formulas.
--
-- Grain: one row per season. A per-week breakdown is a straightforward
-- follow-up (group by week instead of season) once there's enough graded
-- history to make a week-by-week view worth looking at.

with qualifying as (
    -- Only meets_publish_bar=true picks count toward the Live Tracker --
    -- that band describes "how is the model's actual betting record,"
    -- which is the published picks, not every game it merely scored.
    select *
    from cfbd.live_picks
    where meets_publish_bar = true
),

graded as (
    select *
    from qualifying
    where coalesce(outcome, 'pending') in ('win', 'loss', 'push')
),

by_season as (
    select
        season,
        count(*) as graded_picks,
        sum(case when outcome = 'win'  then 1 else 0 end) as wins,
        sum(case when outcome = 'loss' then 1 else 0 end) as losses,
        sum(case when outcome = 'push' then 1 else 0 end) as pushes,
        round(
            avg(case when outcome != 'push' then case when outcome = 'win' then 1.0 else 0.0 end end) * 100,
            1
        ) as win_rate_pct,
        round(sum(pnl), 3) as total_pnl,
        round(sum(pnl) / nullif(count(*) filter (where outcome != 'push'), 0) * 100, 1) as roi_pct,
    from graded
    group by season
),

pending_counts as (
    select
        season,
        count(*) as pending_picks
    from qualifying
    where outcome is null or outcome = 'pending'
    group by season
)

select
    coalesce(g.season, p.season)            as season,
    coalesce(g.graded_picks, 0)              as graded_picks,
    coalesce(g.wins, 0)                      as wins,
    coalesce(g.losses, 0)                    as losses,
    coalesce(g.pushes, 0)                    as pushes,
    g.win_rate_pct,
    g.total_pnl,
    g.roi_pct,
    coalesce(p.pending_picks, 0)             as pending_picks,
from by_season g
full outer join pending_counts p using (season)
order by season desc
