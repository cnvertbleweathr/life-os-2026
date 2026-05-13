-- Staging: habits log from DLT-loaded habits schema
-- Source: habits.habit_log (loaded by pipelines/habits_pipeline.py)

select
    log_date,
    habit,
    completed,
    logged_at,

    -- Convenience derived fields
    cast(substr(log_date, 1, 4) as integer) as year,
    cast(substr(log_date, 6, 2) as integer) as month,

from habits.habit_log
