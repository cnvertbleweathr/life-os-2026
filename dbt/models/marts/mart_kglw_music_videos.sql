-- dbt/models/marts/mart_kglw_music_videos.sql
--
-- Official music videos for the King Gizzard page's MUSIC VIDEOS tab.
--
-- Source of truth is the band's own music-videos playlist
-- (PLjEpdah_kOgfhdncO5YfjdQY9hFzPq-2r), ingested by
-- pipelines/kglw_youtube_pipeline.py into
-- kglw_youtube.music_video_playlist. Anything in that playlist is a
-- music video; nothing outside it is. This replaced a title-regex
-- classifier (2026-10-15) that missed videos without "(Official Video)"
-- in the title.
--
-- release_date is videoPublishedAt — when the video went public — not
-- the date it was added to the playlist.

with playlist as (

    select
        video_id,
        title,
        cast(published_at as timestamp)                     as published_at,
        cast(cast(published_at as timestamp) as date)       as release_date,
        try_cast(view_count as bigint)                      as view_count,
        duration,
        playlist_position,
        regexp_replace(title, chr(8203), '', 'g')           as clean_title,
        -- A playlist can hold the same video twice; keep one row.
        row_number() over (partition by video_id order by playlist_position) as rn
    from kglw_youtube.music_video_playlist

)

select
    video_id,
    title,
    -- "King Gizzard & The Lizard Wizard - Some of Us (Official Video)"
    --   -> "Some of Us". Strips the band prefix and any trailing
    --   parenthetical/bracketed tags; falls back to the full title when
    --   there's no " - " separator.
    trim(regexp_replace(
        coalesce(nullif(regexp_extract(clean_title, '^.*? - (.*)$', 1), ''), clean_title),
        '(\s*[\(\[][^\)\]]*[\)\]])+\s*$', ''
    )) as song_title,
    published_at,
    release_date,
    view_count,
    duration,
    playlist_position
from playlist
where rn = 1
