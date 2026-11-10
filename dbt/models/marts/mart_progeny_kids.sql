-- Mart: one row per kid with age and countdowns.
-- A view, so ages are computed from birthdate every time it's read (never stored).

{{ config(materialized='view') }}

with kids as (
    select *, date_sub('year', birthdate, current_date) as age_years_whole
    from {{ ref('stg_progeny__kids') }}
),

birthdays as (
    select
        *,
        -- Today's birthday counts as "next" (0 days away)
        case
            when birthdate is null then null
            when cast(birthdate + to_years(cast(age_years_whole as integer)) as date) = current_date
                then current_date
            else cast(birthdate + to_years(cast(age_years_whole + 1 as integer)) as date)
        end as next_birthday
    from kids
)

select
    kid_id,
    display_name,
    birthdate,
    due_date,
    is_born,
    date_diff('day', birthdate, current_date)              as age_days,
    date_sub('month', birthdate, current_date)             as age_months,
    age_years_whole                                         as age_years,
    {{ age_label('birthdate', 'current_date') }}            as age_label,
    next_birthday,
    date_diff('day', current_date, next_birthday)           as days_to_birthday,
    date_sub('year', birthdate, next_birthday)              as turning_age,
    case when not is_born then date_diff('day', current_date, due_date) end as days_to_due,
    kindergarten_target
from birthdays
order by coalesce(birthdate, due_date), kid_id
