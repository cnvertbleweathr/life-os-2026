-- Staging: movie plays from the Plex server's watch history
-- Source: plex.history (loaded by pipelines/plex_pipeline.py)
-- One row per play. Empty until PLEX_URL / PLEX_TOKEN are configured.

{% set src = relation_if_exists('plex', 'history') %}

{% if src is not none %}
select
    history_key,
    rating_key,
    title,
    cast(film_year as integer)          as film_year,
    cast(tmdb_id as bigint)             as tmdb_id,
    imdb_id,
    to_timestamp(viewed_at)             as viewed_at_utc,
    cast(watched_date as date)          as watched_date,
    cast(account_id as varchar)         as account_id,
    device_id,
    cast(duration_ms as bigint)         as duration_ms,
    file_path,
    in_library,
    ingested_at
from {{ src }}
where viewed_at is not null
{% else %}
select
    cast(null as varchar)                   as history_key,
    cast(null as varchar)                   as rating_key,
    cast(null as varchar)                   as title,
    cast(null as integer)                   as film_year,
    cast(null as bigint)                    as tmdb_id,
    cast(null as varchar)                   as imdb_id,
    cast(null as timestamp with time zone)  as viewed_at_utc,
    cast(null as date)                      as watched_date,
    cast(null as varchar)                   as account_id,
    cast(null as varchar)                   as device_id,
    cast(null as bigint)                    as duration_ms,
    cast(null as varchar)                   as file_path,
    cast(null as boolean)                   as in_library,
    cast(null as varchar)                   as ingested_at
where false
{% endif %}
