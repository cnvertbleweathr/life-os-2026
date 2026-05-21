-- Mart: habit performance
-- One row per (date, habit) with completion status.
-- Powers the heatmap / calendar view in the Streamlit dashboard.

with log as (
    select * from {{ ref('stg_habits__log') }}
),

-- Pivot so each habit is a column per date
pivoted as (
    select
        log_date,
        year,
        month,

        max(case when habit = 'meditation'         then completed else 0 end) as meditation,
        max(case when habit = 'pushups_100'        then completed else 0 end) as pushups_100,
        max(case when habit = 'nonfiction_pages_10' then completed else 0 end) as nonfiction_pages_10,
        max(case when habit = 'fiction_pages_10'   then completed else 0 end) as fiction_pages_10,

        -- total habits completed that day (out of 4)
        sum(completed) as habits_completed_count,
        count(distinct habit) as habits_tracked_count

    from log
    group by log_date, year, month
)

select
    *,
    round(habits_completed_count::double / 4.0 * 100, 1) as daily_completion_pct
from pivoted
order by log_date
