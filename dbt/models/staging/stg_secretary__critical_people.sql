-- Staging: critical people (data/secretary/secretary.yaml, loaded by secretary/config.py).
-- One row per name a critical person's birthday may appear under.

with src as (
    {{ select_or_empty('secretary', 'critical_people', [
        ['name', 'varchar'], ['match_name', 'varchar'],
    ]) }}
)

select distinct
    name,
    lower(trim(match_name)) as match_name
from src
where coalesce(trim(match_name), '') <> ''
