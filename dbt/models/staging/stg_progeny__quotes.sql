-- Staging: kid quotes (data/progeny/quotes.jsonl). Deleted entries dropped.

with src as (
    {{ select_or_empty('progeny', 'quotes', [
        ['id', 'varchar'], ['kid', 'varchar'], ['date', 'date'], ['quote', 'varchar'],
        ['context', 'varchar'], ['deleted', 'boolean'], ['logged_at', 'varchar'],
    ]) }}
)

select id as quote_id, kid as kid_id, "date" as quote_date, quote, context, logged_at
from src
where not coalesce(deleted, false)
