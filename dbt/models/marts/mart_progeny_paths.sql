-- Mart: per kid per learning path — the highest level with evidence ("reached"),
-- % complete, the focus level (next one up) with its activities, latest evidence.
-- Paths are hidden for kids younger than the path's min_age_months.

{{ config(materialized='view') }}

with kids as (
    select kid_id, display_name, age_months
    from {{ ref('mart_progeny_kids') }}
    where is_born
),

levels as (
    select * from {{ ref('stg_progeny__path_levels') }}
),

paths as (
    select distinct path_key, path_name, path_order, min_age_months, total_levels from levels
),

evidence as (
    select e.*, l.level_num, l.level_name
    from {{ ref('stg_progeny__path_evidence') }} e
    join levels l on l.path_key = e.path_key and l.level_key = e.level_key
),

per_kid_path as (
    select
        k.kid_id,
        k.display_name,
        p.path_key,
        p.path_name,
        p.path_order,
        p.total_levels,
        coalesce(max(e.level_num), 0)  as reached_level,
        count(e.evidence_id)            as evidence_count,
        max(e.evidence_date)            as latest_evidence_date,
        arg_max(e.level_name, e.evidence_date) as latest_evidence_level,
        arg_max(e.notes, e.evidence_date)      as latest_evidence_notes
    from kids k
    join paths p on k.age_months >= p.min_age_months
    left join evidence e on e.kid_id = k.kid_id and e.path_key = p.path_key
    group by all
)

select
    x.kid_id,
    x.display_name,
    x.path_key,
    x.path_name,
    x.path_order,
    x.total_levels,
    x.reached_level,
    r.level_name                                   as reached_level_name,
    round(100.0 * x.reached_level / x.total_levels, 1) as pct_complete,
    x.reached_level = x.total_levels               as is_complete,
    f.level_num                                    as focus_level,
    f.level_key                                    as focus_level_key,
    f.level_name                                   as focus_level_name,
    f.description                                  as focus_description,
    f.activities                                   as focus_activities,
    x.evidence_count,
    x.latest_evidence_date,
    x.latest_evidence_level,
    x.latest_evidence_notes
from per_kid_path x
left join levels r on r.path_key = x.path_key and r.level_num = x.reached_level
-- Focus: the next level up; the last level once the path is complete
left join levels f on f.path_key = x.path_key
                  and f.level_num = least(x.reached_level + 1, x.total_levels)
order by x.kid_id, x.path_order
