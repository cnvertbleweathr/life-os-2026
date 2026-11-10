-- Staging: CDC milestone checklist (progeny/reference/cdc_milestones.yaml)

select *
from (
    {{ select_or_empty('progeny', 'milestone_ref', [
        ['milestone_id', 'varchar'], ['band_months', 'integer'], ['band_label', 'varchar'],
        ['domain', 'varchar'], ['domain_label', 'varchar'], ['sort_order', 'integer'],
        ['milestone', 'varchar'], ['source_url', 'varchar'],
    ]) }}
)
