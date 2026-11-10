-- Staging: milestones observed (data/progeny/milestones.jsonl). Deleted entries dropped.

with src as (
    {{ select_or_empty('progeny', 'milestone_observations', [
        ['id', 'varchar'], ['kid', 'varchar'], ['milestone_id', 'varchar'],
        ['observed_date', 'date'], ['notes', 'varchar'], ['deleted', 'boolean'],
        ['logged_at', 'varchar'],
    ]) }}
)

select id as observation_id, kid as kid_id, milestone_id, observed_date, notes, logged_at
from src
where not coalesce(deleted, false)
