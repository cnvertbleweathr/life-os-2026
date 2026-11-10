-- Mart: CDC milestone checklist per kid for the current age band (the latest
-- band at or below their age) and the next one, with observed / not yet.
-- No "behind" scoring by design. A view: the bands move as the kid ages.

{{ config(materialized='view') }}

with kids as (
    select kid_id, display_name, age_months
    from {{ ref('mart_progeny_kids') }}
    where is_born
),

ref as (
    select * from {{ ref('stg_progeny__milestone_ref') }}
),

bands as (
    select distinct band_months from ref
),

kid_bands as (
    select
        k.kid_id,
        k.display_name,
        k.age_months,
        (select max(band_months) from bands where band_months <= k.age_months) as current_band,
        (select min(band_months) from bands where band_months >  k.age_months) as next_band
    from kids k
),

kid_band_rows as (
    select kid_id, display_name, age_months, 'current' as band_role, current_band as band_months
    from kid_bands where current_band is not null
    union all
    select kid_id, display_name, age_months, 'next', next_band
    from kid_bands where next_band is not null
),

observed as (
    select kid_id, milestone_id, min(observed_date) as observed_date,
           string_agg(nullif(notes, ''), ' · ' order by observed_date) as notes
    from {{ ref('stg_progeny__milestone_observations') }}
    group by kid_id, milestone_id
)

select
    b.kid_id,
    b.display_name,
    b.age_months,
    b.band_role,
    r.band_months,
    r.band_label,
    r.domain,
    r.domain_label,
    r.sort_order,
    r.milestone_id,
    r.milestone,
    o.observed_date is not null as is_observed,
    o.observed_date,
    o.notes,
    r.source_url
from kid_band_rows b
join ref r using (band_months)
left join observed o on o.kid_id = b.kid_id and o.milestone_id = r.milestone_id
order by b.kid_id, b.band_role, r.domain, r.sort_order
