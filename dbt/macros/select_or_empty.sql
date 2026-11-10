{#
  select_or_empty(schema, identifier, columns)

  Selects `columns` (a list of [name, type] pairs) from a raw table a pipeline
  loads, casting each one. If the table doesn't exist yet (the pipeline has
  never loaded a row), returns a typed empty select with the same columns
  instead, so downstream models build on an empty warehouse.

  The table version of the stg_plex__history pattern, for sources with many
  columns. Column names are quoted, so reserved words (date, repeat) are fine.
#}
{% macro select_or_empty(schema, identifier, columns) %}
    {%- set src = relation_if_exists(schema, identifier) -%}
    select
    {%- for col in columns %}
        {% if src is not none -%}
        cast("{{ col[0] }}" as {{ col[1] }}) as "{{ col[0] }}"
        {%- else -%}
        cast(null as {{ col[1] }}) as "{{ col[0] }}"
        {%- endif %}{{ "," if not loop.last }}
    {%- endfor %}
    {% if src is not none -%}
    from {{ src }}
    {%- else -%}
    where false
    {%- endif %}
{% endmacro %}


{#
  age_label(birthdate, at_date)

  Human age at a date: "12 days", "7 months", "3y 10m". Null before birth.
  Ages are always computed at query time from the birthdate, never stored.
#}
{% macro age_label(birthdate, at_date) %}
    case
        when {{ birthdate }} is null or {{ at_date }} < {{ birthdate }} then null
        when date_sub('month', {{ birthdate }}, {{ at_date }}) < 1
            then cast(date_diff('day', {{ birthdate }}, {{ at_date }}) as varchar) || ' days'
        when date_sub('month', {{ birthdate }}, {{ at_date }}) < 24
            then cast(date_sub('month', {{ birthdate }}, {{ at_date }}) as varchar) || ' months'
        else cast(date_sub('year', {{ birthdate }}, {{ at_date }}) as varchar) || 'y '
             || cast(date_sub('month', {{ birthdate }}, {{ at_date }}) % 12 as varchar) || 'm'
    end
{% endmacro %}
