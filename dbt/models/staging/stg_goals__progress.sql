select
    year,
    domain,
    goal_key,
    try_cast(current_value as double) as current_value,
    status,
    updated_at,
    notes
from raw.raw_goal_progress