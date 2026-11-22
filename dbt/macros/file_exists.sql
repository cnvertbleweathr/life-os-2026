{#
  True when `path` exists, checked by DuckDB at run time. Lets a model that reads a
  file directly (read_csv / read_json) fall back to an empty result instead of
  failing the whole dbt run when the file is missing.
#}
{% macro file_exists(path) %}
  {% if not execute %}{{ return(true) }}{% endif %}
  {% set result = run_query("select count(*) from glob('" ~ path ~ "')") %}
  {{ return(result.columns[0].values()[0] > 0) }}
{% endmacro %}
