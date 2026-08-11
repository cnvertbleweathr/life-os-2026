-- Mart: goal pacing
-- Extends mart_goal_progress with a pace_status by comparing actual progress
-- against the % of the year elapsed. Handles binary (bool) goals separately
-- since they don't have a meaningful "% of target" trajectory.

with progress as (

    select *
    from {{ ref('mart_goal_progress') }}

),

year_calendar as (

    select distinct
        year,
        date_diff('day', make_date(cast(year as integer), 1, 1), current_date) + 1
            as days_elapsed_raw,
        date_diff(
            'day',
            make_date(cast(year as integer), 1, 1),
            make_date(cast(year as integer) + 1, 1, 1)
        ) as days_in_year
    from progress

),

pacing as (

    select
        p.*,
        yc.days_in_year,
        least(greatest(yc.days_elapsed_raw, 0), yc.days_in_year) as days_elapsed,
        round(
            least(greatest(yc.days_elapsed_raw, 0), yc.days_in_year)::double
            / yc.days_in_year,
            4
        ) as expected_progress_ratio
    from progress p
    inner join year_calendar yc on p.year = yc.year

)

select
    *,
    case
        -- Binary goals: either done, or not-yet-done-and-overdue, or still open
        when goal_value_type = 'bool' then
            case
                when current_value >= 1 then 'complete'
                when expected_progress_ratio >= 1.0 then 'behind'
                else 'binary'
            end

        -- Goals with no numeric target to pace against
        when progress_ratio is null then 'binary'

        when progress_ratio >= 1.0 then 'complete'
        when progress_ratio >= expected_progress_ratio + 0.05 then 'ahead'
        when progress_ratio >= expected_progress_ratio - 0.05 then 'on_track'
        when progress_ratio >= expected_progress_ratio - 0.15 then 'at_risk'
        else 'behind'
    end as pace_status

from pacing
order by domain, goal_key
