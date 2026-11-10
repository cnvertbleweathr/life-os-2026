-- Staging: baby prep checklist (data/progeny/prep_tasks.jsonl). Latest line per id
-- wins upstream, so checking a task off is a new line with done_date set.

with src as (
    {{ select_or_empty('progeny', 'prep_tasks', [
        ['id', 'varchar'], ['task', 'varchar'], ['category', 'varchar'], ['due_date', 'date'],
        ['done_date', 'date'], ['created_date', 'date'], ['deleted', 'boolean'],
        ['logged_at', 'varchar'],
    ]) }}
)

select
    id as task_id,
    task,
    coalesce(nullif(trim(category), ''), 'Other') as category,
    due_date,
    done_date,
    coalesce(created_date, cast(substr(logged_at, 1, 10) as date)) as created_date,
    logged_at
from src
where not coalesce(deleted, false)
