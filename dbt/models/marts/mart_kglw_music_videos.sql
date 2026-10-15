-- dbt/models/marts/mart_kglw_music_videos.sql
--
-- Official music videos from the KGLW YouTube channel
-- (kglw_youtube.videos), for the King Gizzard page's MUSIC VIDEOS tab.
--
-- Sibling of mart_kglw_youtube_matches: that model keeps the
-- "Live in/at ..." uploads and pins them to shows; this one keeps the
-- official videos and drops everything else (live sets, documentaries,
-- visualisers, lyric videos, Shorts).
--
-- Title pattern confirmed from real uploads (2026-10-15):
--   "King Gizzard & The Lizard Wizard - Some of Us (Official Video)"
--   "King Gizzard & The Lizard Wizard - Intrasport (Official Video)"
-- Tolerated variants: "(Official Music Video)", "(Official Animated
-- Video)", square brackets instead of parens, and a bare "Music Video".
--
-- release_date is the YouTube publish date (videoPublishedAt from the
-- pipeline) — for music videos that IS the release date, unlike live
-- uploads where the tour year in the title differs from upload date.

with videos as (

    select
        video_id,
        title,
        cast(published_at as timestamp)          as published_at,
        cast(cast(published_at as timestamp) as date) as release_date,
        try_cast(view_count as bigint)           as view_count,
        duration,
        -- Same zero-width-space strip as the live-matches model.
        regexp_replace(title, chr(8203), '', 'g') as clean_title
    from kglw_youtube.videos

),

classified as (

    select
        *,
        -- Official video marker: "(Official Video)", "[Official Music Video]",
        -- "(Official Animated Video)", or plain "Music Video" anywhere.
        (
            regexp_matches(clean_title, '[\(\[]\s*official[^\)\]]*video', 'i')
            or regexp_matches(clean_title, '\bmusic video\b', 'i')
        )
        and not regexp_matches(clean_title, 'lyric|visuali[sz]er', 'i')
        -- Live uploads belong to mart_kglw_youtube_matches, never here.
        and not regexp_matches(clean_title, ' - live (in|at) ', 'i')
        -- YouTube Shorts / teasers: ISO-8601 duration under one minute
        -- ("PT45S" has no M or H component).
        and not regexp_matches(coalesce(duration, ''), '^PT\d+S$')
            as is_music_video
    from videos

)

select
    video_id,
    title,
    -- "King Gizzard & The Lizard Wizard - Some of Us (Official Video)"
    --   -> "Some of Us". Falls back to the whole title when the channel
    --   prefix is missing.
    trim(regexp_replace(
        coalesce(nullif(regexp_extract(clean_title, '^.*? - (.*)$', 1), ''), clean_title),
        '\s*[\(\[][^\)\]]*[\)\]]\s*$', ''
    )) as song_title,
    published_at,
    release_date,
    view_count,
    duration
from classified
where is_music_video
