-- dbt/models/marts/mart_film_watches.sql
--
-- One row per film per watch date, from Letterboxd and Plex.
--   source = 'letterboxd' | 'plex' | 'both'
--   rating, liked come from Letterboxd when present.
--
-- Film identity (film_key):
--   'tmdb:<id>' when a TMDB id is known. A Plex play whose film has left the
--   library has no GUID any more; it borrows the TMDB id from a Letterboxd
--   entry with the same title + year if there is one, otherwise it falls
--   back to 'title:<lower title>:<year>'.
--
-- Date matching:
--   Letterboxd's date is the one you logged; Plex's is when playback ended,
--   in America/Denver. A film finished after midnight, or logged the next
--   day, lands a day apart. So a Plex day within ±1 day of a Letterboxd
--   entry for the same film joins it (nearest wins) and takes Letterboxd's
--   date. Several Plex plays that collapse into one watch are counted in
--   plex_plays.

with lb_raw as (
    select
        *,
        case
            when tmdb_id is not null then 'tmdb:' || tmdb_id
            else 'title:' || lower(trim(title)) || ':' || coalesce(cast(film_year as varchar), '')
        end as film_key
    from {{ ref('stg_letterboxd__diary') }}
),

lb as (
    select
        film_key,
        watched_date,
        any_value(tmdb_id)          as tmdb_id,
        any_value(title)            as title,
        any_value(film_year)        as film_year,
        max(rating)                 as rating,
        bool_or(liked)              as liked,
        bool_or(is_rewatch)         as letterboxd_rewatch,
        min(entry_id)               as letterboxd_entry_id,
        max(film_url)               as letterboxd_url,
        bool_or(entry_type = 'review') as has_review
    from lb_raw
    group by film_key, watched_date
),

lb_titles as (
    select lower(trim(title)) as title_norm, film_year, min(tmdb_id) as tmdb_id
    from lb_raw
    where tmdb_id is not null
    group by 1, 2
),

px_raw as (
    select
        p.*,
        coalesce(p.tmdb_id, t.tmdb_id) as tmdb_id_resolved
    from {{ ref('stg_plex__history') }} p
    left join lb_titles t
      on p.tmdb_id is null
     and t.title_norm = lower(trim(p.title))
     and t.film_year = p.film_year
),

px_days as (
    select
        case
            when tmdb_id_resolved is not null then 'tmdb:' || tmdb_id_resolved
            else 'title:' || lower(trim(title)) || ':' || coalesce(cast(film_year as varchar), '')
        end                         as film_key,
        watched_date,
        any_value(tmdb_id_resolved) as tmdb_id,
        any_value(title)            as title,
        any_value(film_year)        as film_year,
        count(*)                    as plex_plays,
        min(viewed_at_utc)          as plex_first_viewed_at_utc,
        max(viewed_at_utc)          as plex_last_viewed_at_utc
    from px_raw
    group by 1, 2
),

px_matched as (
    select
        pd.*,
        lb.watched_date as lb_date,
        row_number() over (
            partition by pd.film_key, pd.watched_date
            order by abs(date_diff('day', lb.watched_date, pd.watched_date)) nulls last, lb.watched_date
        ) as rn
    from px_days pd
    left join lb
      on lb.film_key = pd.film_key
     and abs(date_diff('day', lb.watched_date, pd.watched_date)) <= 1
),

px as (
    select
        film_key,
        coalesce(lb_date, watched_date) as watch_date,
        any_value(tmdb_id)              as tmdb_id,
        any_value(title)                as title,
        any_value(film_year)            as film_year,
        sum(plex_plays)                 as plex_plays,
        min(plex_first_viewed_at_utc)   as plex_first_viewed_at_utc,
        max(plex_last_viewed_at_utc)    as plex_last_viewed_at_utc
    from px_matched
    where rn = 1
    group by 1, 2
),

joined as (
    select
        coalesce(lb.film_key, px.film_key)          as film_key,
        coalesce(lb.watched_date, px.watch_date)    as watch_date,
        coalesce(lb.tmdb_id, px.tmdb_id)            as tmdb_id,
        coalesce(lb.title, px.title)                as title,
        coalesce(lb.film_year, px.film_year)        as film_year,
        case
            when lb.film_key is not null and px.film_key is not null then 'both'
            when lb.film_key is not null then 'letterboxd'
            else 'plex'
        end                                         as source,
        lb.rating,
        coalesce(lb.liked, false)                   as liked,
        coalesce(lb.has_review, false)              as has_review,
        coalesce(lb.letterboxd_rewatch, false)      as letterboxd_rewatch,
        lb.letterboxd_entry_id,
        lb.letterboxd_url,
        cast(coalesce(px.plex_plays, 0) as integer) as plex_plays,
        px.plex_first_viewed_at_utc,
        px.plex_last_viewed_at_utc
    from lb
    full outer join px
      on px.film_key = lb.film_key
     and px.watch_date = lb.watched_date
)

select
    md5(film_key || '|' || cast(watch_date as varchar))     as watch_id,
    film_key,
    tmdb_id,
    title,
    film_year,
    watch_date,
    cast(year(watch_date) as integer)                       as watch_year,
    source,
    rating,
    liked,
    has_review,
    -- a rewatch if Letterboxd says so, or ONS has an earlier watch of the same film
    letterboxd_rewatch
        or row_number() over (partition by film_key order by watch_date) > 1
                                                            as is_rewatch,
    row_number() over (partition by film_key order by watch_date)
                                                            as watch_number,
    letterboxd_entry_id,
    letterboxd_url,
    plex_plays,
    plex_first_viewed_at_utc,
    plex_last_viewed_at_utc
from joined
