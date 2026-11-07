-- Staging: Letterboxd diary (watches + reviews)
-- Source: letterboxd.diary_entries (loaded by pipelines/letterboxd_pipeline.py)
-- One row per diary entry. tmdb_id is the join key for mart_film_watches.

{% set src = relation_if_exists('letterboxd', 'diary_entries') %}

{% if src is not none %}
select
    entry_id,
    entry_type,
    film_title                          as title,
    cast(film_year as integer)          as film_year,
    cast(tmdb_id as bigint)             as tmdb_id,
    try_cast(watched_date as date)      as watched_date,
    cast(rating as double)              as rating,
    coalesce(liked, false)              as liked,
    coalesce(is_rewatch, false)         as is_rewatch,
    review,
    film_url,
    letterboxd_user,
    ingested_at
from {{ src }}
where try_cast(watched_date as date) is not null
  and coalesce(entry_type, 'watch') in ('watch', 'review')
{% else %}
select
    cast(null as varchar)   as entry_id,
    cast(null as varchar)   as entry_type,
    cast(null as varchar)   as title,
    cast(null as integer)   as film_year,
    cast(null as bigint)    as tmdb_id,
    cast(null as date)      as watched_date,
    cast(null as double)    as rating,
    cast(null as boolean)   as liked,
    cast(null as boolean)   as is_rewatch,
    cast(null as varchar)   as review,
    cast(null as varchar)   as film_url,
    cast(null as varchar)   as letterboxd_user,
    cast(null as varchar)   as ingested_at
where false
{% endif %}
