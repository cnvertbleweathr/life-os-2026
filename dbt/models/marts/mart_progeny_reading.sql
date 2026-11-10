-- Mart: books read to each kid, toward 1,000 Books Before Kindergarten.
-- Every reading counts, re-reads included (the program counts repeats).
-- A view: pace and days left depend on today.

{{ config(materialized='view') }}

with kids as (
    select kid_id, display_name, is_born, kindergarten_target
    from {{ ref('mart_progeny_kids') }}
),

reads as (
    select * from {{ ref('stg_progeny__books') }}
),

per_kid as (
    select
        kid_id,
        count(*)                                   as total_reads,
        count(distinct title_key)                  as unique_titles,
        count(*) filter (where read_date >= current_date - 29)  as reads_last_30d,
        min(read_date)                             as first_read_date,
        max(read_date)                             as last_read_date
    from reads
    group by kid_id
),

top_title as (
    select kid_id, arg_max(title, n) as most_read_title, max(n) as most_read_count
    from (select kid_id, title_key, any_value(title) as title, count(*) as n
          from reads group by kid_id, title_key)
    group by kid_id
)

select
    k.kid_id,
    k.display_name,
    1000                                                    as goal_reads,
    coalesce(p.total_reads, 0)                              as total_reads,
    coalesce(p.unique_titles, 0)                            as unique_titles,
    coalesce(p.total_reads, 0) - coalesce(p.unique_titles, 0) as repeat_reads,
    round(100.0 * least(coalesce(p.total_reads, 0), 1000) / 1000, 1) as pct_to_goal,
    greatest(1000 - coalesce(p.total_reads, 0), 0)          as reads_remaining,
    coalesce(p.reads_last_30d, 0)                           as reads_last_30d,
    round(coalesce(p.reads_last_30d, 0) / 30.0, 2)          as pace_per_day_30d,
    k.kindergarten_target,
    date_diff('day', current_date, k.kindergarten_target)   as days_to_kindergarten,
    case when date_diff('day', current_date, k.kindergarten_target) > 0
         then round(greatest(1000 - coalesce(p.total_reads, 0), 0)
                    / date_diff('day', current_date, k.kindergarten_target), 2)
    end                                                     as needed_per_day,
    p.first_read_date,
    p.last_read_date,
    t.most_read_title,
    t.most_read_count
from kids k
left join per_kid p using (kid_id)
left join top_title t using (kid_id)
where k.is_born or p.total_reads is not null
order by k.kid_id
