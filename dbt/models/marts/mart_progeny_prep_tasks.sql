-- Mart: baby prep checklist, one row per task, with status.

{{ config(materialized='view') }}

select
    task_id,
    task,
    category,
    due_date,
    done_date,
    created_date,
    case
        when done_date is not null then 'done'
        when due_date < current_date then 'overdue'
        else 'open'
    end as status,
    date_diff('day', current_date, due_date) as days_until_due
from {{ ref('stg_progeny__prep_tasks') }}
order by done_date is not null, due_date nulls last, task
