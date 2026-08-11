-- Mart: weekly scorecard
-- One row per (year, iso_week) rolling up running, habits, and reading
-- activity from core__life_events, plus a snapshot of goal pacing counts.
--
-- Known limitation: the goal-pacing columns reflect pace_status *at the time
-- this mart is built*, not a true point-in-time snapshot for that historical
-- week — ONS doesn't persist historical goal-progress snapshots yet (that's
-- tracked as a separate backlog item). Treat those columns as "current
-- pacing standing," repeated across every week row for the current year,
-- not as a week-by-week pacing history.

with life_events as (

    select
        *,
        date_part('year', event_date) as event_year,
        date_part('week', event_date) as iso_week
    from {{ ref('core__life_events') }}

),

running_weekly as (

    select
        event_year as year,
        iso_week,
        count(*) as runs,
        round(sum(value), 2) as miles
    from life_events
    where event_type = 'run'
    group by 1, 2

),

habits_weekly as (

    select
        event_year as year,
        iso_week,
        count(*) as habit_completions,
        count(distinct title) as distinct_habits_done
    from life_events
    where event_type = 'habit_completed'
    group by 1, 2

),

reading_weekly as (

    select
        event_year as year,
        iso_week,
        count(*) as books_finished
    from life_events
    where event_type = 'book_finished'
    group by 1, 2

),

weeks as (

    select distinct event_year as year, iso_week
    from life_events

),

pacing_snapshot as (

    select
        year,
        count(*) filter (where pace_status = 'ahead') as goals_ahead,
        count(*) filter (where pace_status = 'on_track') as goals_on_track,
        count(*) filter (where pace_status = 'at_risk') as goals_at_risk,
        count(*) filter (where pace_status = 'behind') as goals_behind,
        count(*) filter (where pace_status = 'complete') as goals_complete
    from {{ ref('mart_goal_pacing') }}
    group by year

)

select
    w.year,
    w.iso_week,
    coalesce(r.runs, 0) as runs,
    coalesce(r.miles, 0) as miles,
    coalesce(h.habit_completions, 0) as habit_completions,
    coalesce(h.distinct_habits_done, 0) as distinct_habits_done,
    coalesce(bk.books_finished, 0) as books_finished,
    p.goals_ahead,
    p.goals_on_track,
    p.goals_at_risk,
    p.goals_behind,
    p.goals_complete
from weeks w
left join running_weekly r on w.year = r.year and w.iso_week = r.iso_week
left join habits_weekly h on w.year = h.year and w.iso_week = h.iso_week
left join reading_weekly bk on w.year = bk.year and w.iso_week = bk.iso_week
left join pacing_snapshot p on w.year = p.year
order by w.year desc, w.iso_week desc
