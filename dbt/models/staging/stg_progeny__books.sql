-- Staging: books read to the kids (data/progeny/books.jsonl). One row per reading.
-- title_key normalizes the title so re-reads of the same book group together.

with src as (
    {{ select_or_empty('progeny', 'books', [
        ['id', 'varchar'], ['kid', 'varchar'], ['date', 'date'], ['title', 'varchar'],
        ['author', 'varchar'], ['repeat', 'boolean'], ['deleted', 'boolean'],
        ['logged_at', 'varchar'],
    ]) }}
)

select
    id as reading_id,
    kid as kid_id,
    "date" as read_date,
    title,
    lower(trim(regexp_replace(title, '\s+', ' ', 'g'))) as title_key,
    nullif(trim(author), '') as author,
    coalesce("repeat", false) as is_repeat,
    logged_at
from src
where not coalesce(deleted, false)
