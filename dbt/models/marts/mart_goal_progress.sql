with goals as (

    select *
    from {{ ref('mart_goal_detail') }}

),

progress as (

    select *
    from {{ ref('stg_goals__progress') }}

)

select
    goals.year,
    goals.domain,
    goals.goal_key,
    goals.goal_value,
    goals.goal_value_type,
    goals.target_numeric,
    progress.current_value,
    progress.updated_at,
    progress.notes,

    case
        when goals.target_numeric is null then null
        when goals.target_numeric = 0 then null
        when progress.current_value is null then 0
        else round(progress.current_value / goals.target_numeric, 4)
    end as progress_ratio,

    case
        when goals.target_numeric is null then null
        when goals.target_numeric = 0 then null
        when progress.current_value is null then 0
        else round(100 * progress.current_value / goals.target_numeric, 1)
    end as progress_percent

from goals
left join progress
    on goals.year = progress.year
    and lower(goals.domain) = lower(progress.domain)
    and lower(goals.goal_key) = lower(progress.goal_key)

order by goals.domain, goals.goal_key
