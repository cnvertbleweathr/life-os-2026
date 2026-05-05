select
    year,
    domain,
    goal_key,
    goal_value,
    goal_value_type,

    case
        when goal_value_type in ('int', 'float') then try_cast(goal_value as double)
        when goal_value_type = 'bool' and goal_value = 'true' then 1.0
        when goal_value_type = 'bool' and goal_value = 'false' then 0.0
        else null
    end as target_numeric

from {{ ref('stg_goals__annual_goals') }}
order by domain, goal_key