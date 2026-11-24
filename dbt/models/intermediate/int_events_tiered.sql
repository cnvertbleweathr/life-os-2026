-- Every dated thing the secretary knows about, with an importance tier.
--
-- Rows come from the calendar (stg_calendar__events) and from templates
-- (stg_secretary__template_occurrences). A calendar event a template covers on
-- the same day (the holiday calendar's "Thanksgiving Day", a contact's birthday
-- that has a birthday template) is dropped in favour of the template row, which
-- carries the heads-up milestones. "!" events are never absorbed.
--
-- Life-project milestones (stg_secretary__project_milestones) join as a third source:
-- open milestones of active projects only, titled "<project>: <milestone>".
--
-- Tier, first match wins:
--   1. title starts with "!"                  → critical  ("!" stripped from display_title)
--   2. birthday of a critical person          → critical
--   3. any other birthday                     → important
--   4. template row                           → the template's tier
--   5. project milestone                      → the project's tier
--   6. everything else                        → nice_to_know

with cal as (
    select *, replace(lower(title), '’', '''') as title_norm
    from {{ ref('stg_calendar__events') }}
),

tpl as (
    select * from {{ ref('stg_secretary__template_occurrences') }}
),

people as (
    select * from {{ ref('stg_secretary__critical_people') }}
),

prj as (
    select * from {{ ref('stg_secretary__project_milestones') }}
    where project_status = 'active' and status = 'open'
),

absorbed as (
    select distinct c.event_key
    from cal c
    join tpl t on t.occurs_on = c.start_date
    where c.title not like '!%'
      and (
          list_contains(t.match_titles, c.title_norm)
          or (c.calendar_kind = 'birthdays' and t.person is not null
              and contains(c.title_norm, lower(t.person)))
      )
),

events as (
    select
        c.event_key,
        'calendar'                              as source,
        c.calendar_kind,
        c.calendar_name,
        c.start_date                            as event_date,
        c.start_at,
        c.end_at,
        c.all_day,
        c.title                                 as raw_title,
        c.calendar_kind = 'birthdays'           as is_birthday,
        cast(null as varchar)                   as template_key,
        cast(null as varchar)                   as template_tier,
        cast(null as varchar)                   as person,
        c.location
    from cal c
    where c.event_key not in (select event_key from absorbed)

    union all

    select
        t.event_key,
        'template',
        case when t.person is not null then 'birthdays' else 'template' end,
        cast(null as varchar),
        t.occurs_on,
        cast(null as timestamptz),
        cast(null as timestamptz),
        true,
        t.template_name,
        t.person is not null,
        t.template_key,
        t.tier,
        t.person,
        cast(null as varchar)
    from tpl t

    union all

    select
        p.event_key,
        'project',
        'project',
        p.project_name,
        p.due_date,
        p.due_at,
        cast(null as timestamptz),
        p.due_at is null,
        p.project_name || ': ' || p.title || case when p.is_deadline then ' (deadline)' else '' end,
        false,
        cast(null as varchar),
        p.tier,                                 -- template_tier carries the declared tier for projects too
        cast(null as varchar),
        cast(null as varchar)
    from prj p
),

flagged as (
    select
        e.*,
        exists (
            select 1 from people p
            where (e.person is not null and lower(e.person) = p.match_name)
               or (e.person is null and contains(replace(lower(e.raw_title), '’', ''''), p.match_name))
        ) as is_critical_person
    from events e
)

select
    event_key,
    source,
    calendar_kind,
    calendar_name,
    event_date,
    start_at,
    end_at,
    all_day,
    raw_title,
    trim(ltrim(raw_title, '!'))                 as display_title,
    is_birthday,
    person,
    template_key,
    case
        when raw_title like '!%'                    then 'critical'
        when is_birthday and is_critical_person     then 'critical'
        when is_birthday                            then 'important'
        when template_key is not null               then template_tier
        when source = 'project'                     then template_tier
        else 'nice_to_know'
    end                                         as tier,
    case
        when raw_title like '!%'                    then 'bang'
        when is_birthday and is_critical_person     then 'critical_person_birthday'
        when is_birthday                            then 'birthday'
        when template_key is not null               then 'template'
        when source = 'project'                     then 'project'
        else 'default'
    end                                         as tier_rule,
    location
from flagged
