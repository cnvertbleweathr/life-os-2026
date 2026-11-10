-- Staging: learning path levels (progeny/reference/learning_paths.yaml)
-- activities is newline-separated text.

select *
from (
    {{ select_or_empty('progeny', 'path_levels', [
        ['path_key', 'varchar'], ['path_name', 'varchar'], ['path_order', 'integer'],
        ['min_age_months', 'integer'], ['level_num', 'integer'], ['total_levels', 'integer'],
        ['level_key', 'varchar'], ['level_name', 'varchar'], ['description', 'varchar'],
        ['activities', 'varchar'],
    ]) }}
)
