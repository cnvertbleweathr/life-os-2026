-- Staging: Letterboxd diary (watches + reviews)
-- Sources:
--   letterboxd.diary_entries  RSS feed, latest ~50 entries (pipelines/letterboxd_pipeline.py)
--   letterboxd.csv_diary      full-history backfill from the data export (scripts/import_letterboxd_csv.py)
-- One row per diary entry. tmdb_id is the join key for mart_film_watches.
--
-- The two sources overlap on recent entries. Every RSS row is kept. A CSV row
-- is dropped when an RSS row has the same film (title + year) and watched date,
-- since the RSS row carries the TMDB id and the liked flag. CSV rows that
-- repeat a film + date among themselves keep only the latest-logged one.
-- A CSV row with no TMDB id borrows one from any RSS row for the same film.

{% set rss_src = relation_if_exists('letterboxd', 'diary_entries') %}
{% set csv_src = relation_if_exists('letterboxd', 'csv_diary') %}

with rss as (
{% if rss_src is not none %}
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
    from {{ rss_src }}
    where try_cast(watched_date as date) is not null
      and coalesce(entry_type, 'watch') in ('watch', 'review')
{% else %}
    select
        cast(null as varchar) as entry_id, cast(null as varchar) as entry_type,
        cast(null as varchar) as title, cast(null as integer) as film_year,
        cast(null as bigint) as tmdb_id, cast(null as date) as watched_date,
        cast(null as double) as rating, cast(null as boolean) as liked,
        cast(null as boolean) as is_rewatch, cast(null as varchar) as review,
        cast(null as varchar) as film_url, cast(null as varchar) as letterboxd_user,
        cast(null as varchar) as ingested_at
    where false
{% endif %}
),

csv_raw as (
{% if csv_src is not none %}
    select
        entry_id,
        'watch'                             as entry_type,
        film_title                          as title,
        cast(film_year as integer)          as film_year,
        cast(tmdb_id as bigint)             as tmdb_id,
        try_cast(watched_date as date)      as watched_date,
        cast(rating as double)              as rating,
        false                               as liked,
        coalesce(is_rewatch, false)         as is_rewatch,
        cast(null as varchar)               as review,
        letterboxd_uri                      as film_url,
        cast(null as varchar)               as letterboxd_user,
        ingested_at,
        logged_date
    from {{ csv_src }}
    where try_cast(watched_date as date) is not null
{% else %}
    select
        cast(null as varchar) as entry_id, cast(null as varchar) as entry_type,
        cast(null as varchar) as title, cast(null as integer) as film_year,
        cast(null as bigint) as tmdb_id, cast(null as date) as watched_date,
        cast(null as double) as rating, cast(null as boolean) as liked,
        cast(null as boolean) as is_rewatch, cast(null as varchar) as review,
        cast(null as varchar) as film_url, cast(null as varchar) as letterboxd_user,
        cast(null as varchar) as ingested_at, cast(null as varchar) as logged_date
    where false
{% endif %}
),

rss_tmdb as (
    select lower(trim(title)) as title_norm, film_year, min(tmdb_id) as tmdb_id
    from rss
    where tmdb_id is not null
    group by 1, 2
),

csv as (
    select
        c.entry_id, c.entry_type, c.title, c.film_year,
        coalesce(c.tmdb_id, t.tmdb_id)      as tmdb_id,
        c.watched_date, c.rating, c.liked, c.is_rewatch, c.review,
        c.film_url, c.letterboxd_user, c.ingested_at
    from csv_raw c
    left join rss_tmdb t
      on t.title_norm = lower(trim(c.title))
     and t.film_year is not distinct from c.film_year
    where not exists (
        select 1 from rss r
        where lower(trim(r.title)) = lower(trim(c.title))
          and r.film_year is not distinct from c.film_year
          and r.watched_date = c.watched_date
    )
    qualify row_number() over (
        partition by lower(trim(c.title)), c.film_year, c.watched_date
        order by c.logged_date desc nulls last, c.entry_id desc
    ) = 1
)

select *, 'rss' as source from rss
union all
select *, 'csv' as source from csv
