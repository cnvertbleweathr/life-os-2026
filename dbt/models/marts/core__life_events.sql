-- Mart: core life events
-- A universal event timeline across domains. This is the foundation for
-- OpenClaw context (Phase 3/4 of the roadmap) — anything that needs "what
-- happened recently, across every domain" should read from here instead of
-- querying each raw schema separately.
--
-- Currently unions: running activities (Strava), habit completions, and
-- books finished (Hardcover). Add a new CTE + union branch per domain as
-- more sources come online (e.g. CrossFit sessions once sugarwod.workouts
-- exists — see scripts/load_sugarwod_to_duckdb.py — or calendar events once
-- calendar exports land in DuckDB instead of CSV).

with runs as (

    select
        try_cast(start_date as date) as event_date,
        'fitness' as domain,
        'run' as event_type,
        coalesce(nullif(name, ''), 'Run') as title,
        distance_miles as value,
        'miles' as value_unit,
        cast(strava_id as varchar) as source_id,
        'strava' as source
    from strava.activities
    where is_run = true
        and try_cast(start_date as date) is not null

),

habit_completions as (

    select
        try_cast(log_date as date) as event_date,
        'habits' as domain,
        'habit_completed' as event_type,
        habit as title,
        1.0 as value,
        'count' as value_unit,
        habit || '_' || cast(log_date as varchar) as source_id,
        'habits' as source
    from {{ ref('stg_habits__log') }}
    where completed = 1
        and try_cast(log_date as date) is not null

),

books as (

    select
        try_cast(marked_read_at as date) as event_date,
        'reading' as domain,
        'book_finished' as event_type,
        title,
        1.0 as value,
        'count' as value_unit,
        cast(book_id as varchar) as source_id,
        'hardcover' as source
    from hardcover.books_read
    where try_cast(marked_read_at as date) is not null

)

select * from runs
union all
select * from habit_completions
union all
select * from books

order by event_date desc
