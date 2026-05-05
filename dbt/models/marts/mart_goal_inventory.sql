select
    year,
    domain,
    count(*) as goal_count
from {{ ref('stg_goals__annual_goals') }}
group by 1, 2
order by 1, 2
