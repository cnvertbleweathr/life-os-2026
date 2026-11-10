{#
  team_xwalk_join(alias, source, key, season)

  Join condition onto an NBA / NHL team crosswalk seed: the row for this source
  and key whose valid_from / valid_to seasons cover `season` (blank = open-ended).

    left join {{ ref('nba_team_crosswalk') }} h
      on {{ team_xwalk_join('h', 'espn_id', 'g.home_id', 'g.season') }}

  Seeds are built from the raw keys by scripts/nba_nhl_build_crosswalks.py.
  Never string-match team names in a model; add the key to the seed instead.
#}
{% macro team_xwalk_join(alias, source, key, season) %}
    {{ alias }}.source = '{{ source }}'
    and {{ alias }}.source_key = cast({{ key }} as varchar)
    and {{ season }} between coalesce({{ alias }}.valid_from_season, 0)
                         and coalesce({{ alias }}.valid_to_season, 9999)
{% endmacro %}
