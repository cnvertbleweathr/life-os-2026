-- Staging: template dates (data/secretary/templates/*.yaml, expanded by secretary/config.py).
-- One row per template per year (last year, this year, next year).

with src as (
    {{ select_or_empty('secretary', 'template_occurrences', [
        ['template_key', 'varchar'], ['template_name', 'varchar'], ['tier', 'varchar'],
        ['person', 'varchar'], ['occurs_on', 'date'], ['match_titles', 'varchar[]'],
    ]) }}
)

select
    'tpl:' || template_key || ':' || cast(occurs_on as varchar) as event_key,
    template_key,
    template_name,
    tier,
    person,
    occurs_on,
    match_titles
from src
