-- Staging: firsts (data/progeny/firsts.jsonl). Deleted entries dropped.

with src as (
    {{ select_or_empty('progeny', 'firsts', [
        ['id', 'varchar'], ['kid', 'varchar'], ['date', 'date'], ['title', 'varchar'],
        ['notes', 'varchar'], ['deleted', 'boolean'], ['logged_at', 'varchar'],
    ]) }}
)

select id as first_id, kid as kid_id, "date" as first_date, title, notes, logged_at
from src
where not coalesce(deleted, false)
