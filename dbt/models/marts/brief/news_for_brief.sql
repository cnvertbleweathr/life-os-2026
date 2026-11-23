-- news_for_brief.sql
--
-- Good News and Science stories from the last 7 days that the morning brief may
-- use, with whether (and when) a brief already ran them.
--
-- Sources: news.articles (pipelines/news_pipeline.py) and brief.featured_news
-- (written by agents/morning_brief/featured.py after each brief is saved).
--
-- Grain: one row per article. "Last 7 days" is by published_at, falling back to
-- when the pipeline first saw it (some feeds omit dates).
-- Recurring filler columns from the feeds (horoscopes, "Good News in History")
-- are dropped here rather than at ingest, so the raw table stays complete.

with articles as (
    select
        article_id,
        url,
        title,
        summary,
        source,
        category,
        published_at,
        first_seen_at,
        cast(coalesce(published_at, first_seen_at) as date) as story_date
    from news.articles
    where coalesce(published_at, first_seen_at) >= current_date - interval 6 day
),

filtered as (
    select *
    from articles
    where not regexp_matches(
        title,
        '(?i)horoscope|astrology|good news in history|^this day in history|^on this day'
    )
),

featured as (
    select
        article_id,
        max(featured_on) as featured_on,
        count(*)         as times_featured
    from brief.featured_news
    group by 1
)

select
    a.article_id,
    a.category,
    a.source,
    a.title,
    a.summary,
    a.url,
    a.published_at,
    a.story_date,
    f.article_id is not null       as already_featured,
    f.featured_on,
    coalesce(f.times_featured, 0)  as times_featured
from filtered a
left join featured f using (article_id)
order by a.category, a.story_date desc, a.title
