-- Mart: training load
-- CTL (Chronic Training Load, 42-day exponential average), ATL (Acute
-- Training Load, 7-day exponential average), TSB (Training Stress Balance
-- = CTL - ATL), and a readiness signal, in the spirit of the standard
-- Banister/TrainingPeaks model.
--
-- PREREQUISITE: this mart reads sugarwod.workouts, which does not exist
-- until scripts/load_sugarwod_to_duckdb.py has been run at least once
-- (SugarWOD currently lands as a CSV, not a DLT-loaded table — see that
-- script's docstring). Run it, then `dbt run --select mart_training_load`.
--
-- Load model (intentionally simple — refine later with heart-rate data):
--   daily_load = running_minutes + (crossfit_sessions * 45)
-- i.e. duration-based load, treating one CrossFit class as ~45 load-minutes.
-- This is a proxy, not a physiological measurement — good enough to see
-- trend direction and relative fatigue, not precise enough for anything
-- more clinical than that.

with running_days as (

    select
        cast(start_date as date) as day,
        sum(moving_time_s) / 60.0 as running_minutes
    from strava.activities
    where is_run = true
    group by 1

),

crossfit_days as (

    select
        cast(date as date) as day,
        count(*) as crossfit_sessions
    from sugarwod.workouts
    group by 1

),

daily_load as (

    select
        coalesce(r.day, c.day) as day,
        coalesce(r.running_minutes, 0) as running_minutes,
        coalesce(c.crossfit_sessions, 0) as crossfit_sessions,
        coalesce(r.running_minutes, 0) + coalesce(c.crossfit_sessions, 0) * 45.0 as load
    from running_days r
    full outer join crossfit_days c on r.day = c.day

),

spine as (

    select unnest(generate_series(
        (select min(day) from daily_load),
        (select max(day) from daily_load),
        interval 1 day
    )) as day

),

loads as (

    select
        s.day,
        coalesce(d.load, 0) as load
    from spine s
    left join daily_load d on s.day = d.day

),

-- Exponentially-weighted rolling average using a bounded self-join window.
-- 120 days back is enough to fully saturate a 42-day-halflife-style decay.
decayed as (

    select
        l1.day,
        sum(l2.load * exp(-1.0 * date_diff('day', l2.day, l1.day) / 42.0))
            / nullif(sum(exp(-1.0 * date_diff('day', l2.day, l1.day) / 42.0)), 0)
            as ctl,
        sum(l2.load * exp(-1.0 * date_diff('day', l2.day, l1.day) / 7.0))
            / nullif(sum(exp(-1.0 * date_diff('day', l2.day, l1.day) / 7.0)), 0)
            as atl
    from loads l1
    inner join loads l2
        on l2.day <= l1.day
        and l2.day >= l1.day - interval '120 days'
    group by l1.day

)

select
    day,
    round(ctl, 2) as ctl,
    round(atl, 2) as atl,
    round(ctl - atl, 2) as tsb,
    case
        when (ctl - atl) >= 5 then 'green'
        when (ctl - atl) >= -10 then 'yellow'
        else 'red'
    end as readiness_signal
from decayed
order by day desc
