-- Staging: kids config (data/progeny/kids.yaml, loaded by pipelines/progeny_pipeline.py)
-- One row per kid. No ages here: marts compute them from birthdate at query time.

with src as (
    {{ select_or_empty('progeny', 'kids', [
        ['kid_id', 'varchar'], ['display_name', 'varchar'], ['birthdate', 'date'],
        ['due_date', 'date'], ['kindergarten_start', 'date'],
    ]) }}
)

select
    kid_id,
    display_name,
    birthdate,
    due_date,
    birthdate is not null as is_born,
    -- 1,000 Books Before Kindergarten target: explicit date, else the first
    -- August 15 on or after the 5th birthday.
    case
        when kindergarten_start is not null then kindergarten_start
        when birthdate is null then null
        when make_date(year(birthdate) + 5, 8, 15) >= cast(birthdate + interval 5 year as date)
            then make_date(year(birthdate) + 5, 8, 15)
        else make_date(year(birthdate) + 6, 8, 15)
    end as kindergarten_target
from src
