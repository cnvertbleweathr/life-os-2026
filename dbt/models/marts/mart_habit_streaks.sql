-- Mart: habit streaks
-- Current and longest streak per habit for the current year.
-- Uses window functions to detect consecutive completed days.

with log as (
    select *
    from {{ ref('stg_habits__log') }}
    where year = year(current_date)
      and completed = 1
),

-- Assign a "group" to consecutive dates using the classic gap-and-island technique
gaps as (
    select
        habit,
        log_date,
        row_number() over (partition by habit order by log_date) as rn,
        -- Subtract row number from date to get a constant "island id" for consecutive days
        (cast(log_date as date) - interval (row_number() over (partition by habit order by log_date)) day)::date as island_id
    from log
),

islands as (
    select
        habit,
        island_id,
        min(log_date) as streak_start,
        max(log_date) as streak_end,
        count(*) as streak_length
    from gaps
    group by habit, island_id
),

-- Current streak: island that includes today or yesterday (to handle not-yet-logged today)
current_streaks as (
    select
        habit,
        streak_length as current_streak
    from islands
    where streak_end >= cast(current_date - interval 1 day as varchar)
),

longest_streaks as (
    select
        habit,
        max(streak_length) as longest_streak
    from islands
    group by habit
)

select
    l.habit,
    coalesce(c.current_streak, 0) as current_streak,
    ls.longest_streak
from (select distinct habit from log) l
left join current_streaks c using (habit)
left join longest_streaks ls using (habit)
order by habit
