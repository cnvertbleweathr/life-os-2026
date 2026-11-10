-- A crosswalk key resolves to at most one franchise in any season: no two rows
-- for the same (source, source_key) have overlapping season ranges.

with x as (
    select 'nba' as league, * from {{ ref('nba_team_crosswalk') }}
    union all
    select 'nhl', * from {{ ref('nhl_team_crosswalk') }}
)

select a.league, a.source, a.source_key, a.team_code, b.team_code as other_team_code
from x a
join x b
  on a.league = b.league
 and a.source = b.source
 and a.source_key = b.source_key
 and a.team_code < b.team_code
 and coalesce(a.valid_from_season, 0) <= coalesce(b.valid_to_season, 9999)
 and coalesce(b.valid_from_season, 0) <= coalesce(a.valid_to_season, 9999)
