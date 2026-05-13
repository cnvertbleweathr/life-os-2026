-- Staging: habits summary from DLT-loaded habits schema
-- Source: habits.habit_summary (loaded by pipelines/habits_pipeline.py)

select
    year,
    habit,
    done_days,
    days_observed,
    completion_rate_pct

from habits.habit_summary
