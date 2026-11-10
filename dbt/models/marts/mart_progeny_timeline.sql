-- Mart: every Progeny event (quotes, firsts, milestones observed, learning path
-- evidence) in one feed, with the kid's age on the day.
-- A view: small, and it stays in step with kids.yaml edits (e.g. a birthdate added).

{{ config(materialized='view') }}

with kids as (
    select kid_id, display_name, birthdate from {{ ref('stg_progeny__kids') }}
),

events as (
    select quote_id as event_id, kid_id, quote_date as event_date, 'quote' as event_type,
           quote as title, context as detail, logged_at
    from {{ ref('stg_progeny__quotes') }}

    union all
    select first_id, kid_id, first_date, 'first', title, notes, logged_at
    from {{ ref('stg_progeny__firsts') }}

    union all
    select o.observation_id, o.kid_id, o.observed_date, 'milestone',
           coalesce(r.milestone, o.milestone_id),
           concat_ws(' · ', r.band_label || ' · ' || r.domain_label, nullif(o.notes, '')),
           o.logged_at
    from {{ ref('stg_progeny__milestone_observations') }} o
    left join {{ ref('stg_progeny__milestone_ref') }} r using (milestone_id)

    union all
    select e.evidence_id, e.kid_id, e.evidence_date, 'path',
           coalesce(l.path_name || ': ' || l.level_name, e.path_key || ': ' || e.level_key),
           e.notes, e.logged_at
    from {{ ref('stg_progeny__path_evidence') }} e
    left join {{ ref('stg_progeny__path_levels') }} l
           on l.path_key = e.path_key and l.level_key = e.level_key
)

select
    e.event_id,
    e.kid_id,
    k.display_name,
    e.event_date,
    e.event_type,
    e.title,
    e.detail,
    date_sub('month', k.birthdate, e.event_date)                as age_months_at_event,
    coalesce({{ age_label('k.birthdate', 'e.event_date') }},
             case when e.event_date < k.birthdate or k.birthdate is null then 'before birth' end)
                                                                 as age_at_event,
    e.logged_at
from events e
left join kids k using (kid_id)
order by e.event_date desc, e.logged_at desc
