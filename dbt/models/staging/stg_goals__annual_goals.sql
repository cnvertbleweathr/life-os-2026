-- Unnest raw_goals JSON blobs into one row per actual goal key.
--
-- raw.raw_goals stores each YAML sub-section as a JSON dict, e.g.:
--   domain=professional, goal_key=outcomes, goal_value={"migrations_completed":100,...}
--
-- We explode those into individual rows:
--   domain=professional, goal_key=migrations_completed, goal_value=100
--
-- Habits are stored one level deeper (dict of dicts) so we extract
-- just the `target` field as the goal value.

with raw as (
    select year, domain, goal_key as section, goal_value
    from raw.raw_goals
    -- skip data_sources and systems rows — not trackable goals
    where goal_key not in ('data_sources', 'systems')
),

-- Unnest outcomes sections (flat key→scalar dicts)
flat_goals as (
    select
        r.year,
        r.domain,
        kv.key   as goal_key,
        kv.value as goal_value_raw
    from raw r,
    lateral (
        select key, value
        from json_each(r.goal_value)
    ) kv
    where r.section = 'outcomes'
),

-- Unnest habits section (dict of dicts — pull target as the numeric goal)
habit_goals as (
    select
        r.year,
        r.domain,
        kv.key as goal_key,
        json_extract_string(kv.value, '$.target') as goal_value_raw
    from raw r,
    lateral (
        select key, value
        from json_each(r.goal_value)
    ) kv
    where r.section = 'habits'
),

combined as (
    select * from flat_goals
    union all
    select * from habit_goals
),

typed as (
    select
        year,
        domain,
        goal_key,
        -- strip surrounding quotes from JSON strings
        regexp_replace(goal_value_raw::varchar, '^"|"$', '') as goal_value,

        case
            when goal_value_raw::varchar ~ '^-?[0-9]+$'            then 'int'
            when goal_value_raw::varchar ~ '^-?[0-9]+\.[0-9]+$'    then 'float'
            when lower(goal_value_raw::varchar) in ('true','false') then 'bool'
            else 'str'
        end as goal_value_type

    from combined
)

select * from typed
order by domain, goal_key