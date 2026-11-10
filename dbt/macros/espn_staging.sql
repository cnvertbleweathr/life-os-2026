{#
  ESPN staging shared by NBA and NHL (stg_nba__games / stg_nhl__games,
  stg_nba__odds / stg_nhl__odds). The two leagues' raw tables have the same
  shape; only the crosswalk seed and the provider rows differ.
#}

{#
  espn_games(league)

  One row per ESPN game between two franchises, with canonical team codes.
  Exhibition sides (All-Star teams, 4 Nations countries) aren't in the
  crosswalk, so the inner joins drop those games. Unplayed games (postponed,
  canceled, not yet played) are kept with completed = false; a postponed game
  is replayed under a new game_id.
#}
{% macro espn_games(league) %}
select
    g.game_id,
    cast(g.season as integer)                  as season,
    cast(g.season_type as integer)             as season_type,      -- 2 regular, 3 playoffs
    cast(g.game_date as date)                  as game_date,        -- US/Eastern
    g.start_time,
    h.team_code                                as home_team,
    a.team_code                                as away_team,
    g.home_id                                  as home_espn_id,
    g.away_id                                  as away_espn_id,
    cast(g.home_score as integer)              as home_score,
    cast(g.away_score as integer)              as away_score,
    coalesce(g.completed, false)               as completed,
    g.status,
    coalesce(g.went_ot, false)                 as went_ot,
    {% if league == 'nhl' -%}
    coalesce(g.shootout, false)                as shootout,
    {% endif -%}
    coalesce(g.neutral_site, false)            as neutral_site,
    g.venue
from {{ source(league, 'games') }} g
join {{ ref(league ~ '_team_crosswalk') }} h
  on {{ team_xwalk_join('h', 'espn_id', 'g.home_id', 'g.season') }}
join {{ ref(league ~ '_team_crosswalk') }} a
  on {{ team_xwalk_join('a', 'espn_id', 'g.away_id', 'g.season') }}
{% endmacro %}


