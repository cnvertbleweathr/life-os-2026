{#
  relation_if_exists(schema, identifier)

  Returns the warehouse relation for a raw table a pipeline loads, or none
  if that table doesn't exist yet. Staging models over optional sources
  (e.g. plex.history before PLEX_TOKEN is configured) use it to fall back
  to a typed empty select, so the required dbt step doesn't fail on a
  source that simply hasn't loaded yet.

  At parse time (execute = false) it always returns none.
#}
{% macro relation_if_exists(schema, identifier) %}
    {% if not execute %}
        {{ return(none) }}
    {% endif %}
    {{ return(adapter.get_relation(database=target.database, schema=schema, identifier=identifier)) }}
{% endmacro %}
