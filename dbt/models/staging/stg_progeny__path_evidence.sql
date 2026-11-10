-- Staging: learning path evidence (data/progeny/path_evidence.jsonl). Deleted entries dropped.

with src as (
    {{ select_or_empty('progeny', 'path_evidence', [
        ['id', 'varchar'], ['kid', 'varchar'], ['path', 'varchar'], ['level', 'varchar'],
        ['date', 'date'], ['notes', 'varchar'], ['deleted', 'boolean'], ['logged_at', 'varchar'],
    ]) }}
)

select id as evidence_id, kid as kid_id, path as path_key, level as level_key,
       "date" as evidence_date, notes, logged_at
from src
where not coalesce(deleted, false)
