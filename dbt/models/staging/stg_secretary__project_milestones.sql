-- Staging: life-project milestones (data/secretary/projects.yaml + milestone_log.jsonl,
-- published by secretary/projects.py). One row per milestone, done or open.

with src as (
    {{ select_or_empty('secretary', 'project_milestones', [
        ['project_key', 'varchar'], ['project_name', 'varchar'], ['tier', 'varchar'],
        ['project_status', 'varchar'], ['milestone_key', 'varchar'], ['title', 'varchar'],
        ['due_date', 'date'], ['due_at', 'timestamptz'], ['is_deadline', 'boolean'],
        ['status', 'varchar'], ['done_on', 'date'], ['done_by', 'varchar'], ['is_overdue', 'boolean'],
    ]) }}
)

select
    'prj:' || project_key || ':' || milestone_key as event_key,
    project_key,
    project_name,
    tier,
    project_status,
    milestone_key,
    title,
    due_date,
    due_at,
    coalesce(is_deadline, false) as is_deadline,
    status,
    done_on,
    done_by
from src
