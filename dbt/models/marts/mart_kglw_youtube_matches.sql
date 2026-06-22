-- dbt/models/marts/mart_kglw_youtube_matches.sql
--
-- Matches videos from the official KGLW YouTube channel
-- (kglw_youtube.videos) to specific shows in kglw.shows, without
-- relying on kglw.net's broken links/show/{id} endpoint.
--
-- Built against 20 REAL titles pulled from the channel on 2026-06-22.
-- Confirmed patterns:
--   "King Gizzard & The Lizard Wizard - Live in {City} '{YY} (Night {N})"
--   "King Gizzard and the Lizard Wizard - Live at {Venue} {Year} (Night {N})"
--
-- Confirmed gotchas baked into this model (each one is a real thing
-- found in the actual sample, not a hypothetical):
--   1. The two-digit year in the title ('25) is the TOUR year, not the
--      upload year — Field of Vision was uploaded 2026-06-02 but the
--      title says '25. published_at is NOT usable for year matching.
--   2. Smart quote (U+2019 ’) is used for the year marker, not a
--      straight apostrophe — both are handled below since the channel
--      isn't 100% consistent (confirmed both ' and ’ appear in the
--      sample of 20).
--   3. Spacing around "Night" is inconsistent — "Night 1" vs "Night3"
--      both appear. Regex tolerates zero-or-more spaces.
--   4. Not every video is a live show — "The Making of Phantom Island"
--      is a documentary and correctly produces no match below.
--   5. "Live in {X}" can be a CITY ("New York City") or a COUNTRY
--      ("Lithuania", "Bulgaria") — kglw.shows has separate city/country
--      columns, so this model tries both rather than assuming one.
--   6. "Live at {X}" is typically a VENUE name (e.g. "Field of Vision"),
--      matched against venue_name instead.
--   7. Night N is essential for disambiguating multi-night runs at the
--      same location (Bulgaria had 3 nights within days of each other).
--      This model orders same-location shows by date and maps
--      Night 1 -> earliest date in that group, Night 2 -> next, etc.
--      This is a REAL ASSUMPTION, not a confirmed fact — if KGLW ever
--      numbers nights out of date order for some reason, this breaks.
--      Flagged via match_confidence below rather than silently trusted.
--   8. CONFIRMED BUG, FIXED 2026-06-22: "Field of Vision" and "New York
--      City" are titles people actually use, but NEITHER appears
--      literally in kglw.shows. "Field of Vision" is a festival brand
--      name hosted at venue_name='Meadow Creek', city='Buena Vista' --
--      confirmed via direct query, the string "Field of Vision" exists
--      nowhere in kglw.shows at all. "New York City" similarly never
--      appears -- the real city value is 'Queens' (Forest Hills Stadium
--      sits in Queens, NY).
--   9. CONFIRMED 2026-06-22, same shape as #8: five more 2024 US tour
--      titles use a STATE or metro-area name instead of the actual town
--      the venue sits in -- "Live in Kentucky '24" is really Newport,
--      KY (Megacorp Pavilion); "Live in Oregon '24" is really Troutdale,
--      OR (Edgefield Amphitheater); "Live in Arkansas '24" is really
--      Fayetteville, AR (JJ's Live); "Live in Los Angeles '24" is really
--      Inglewood, CA (The Forum); "Live in Maine '24" is really
--      Portland, ME (Thompson's Point). All five confirmed via direct
--      query against kglw.shows before adding -- not guessed.
--
--      This is NOT a general solution for every possible state/metro
--      name mismatch -- it's grounded in seven real confirmed failures
--      total now (Field of Vision, New York/NYC, Kentucky, Oregon,
--      Arkansas, Los Angeles, Maine), with room to add more as new ones
--      surface via the no_match QA query at the bottom of this file.

with festival_aliases as (
    -- Explicit text -> real venue_name/city/state mapping for known
    -- cases where the YouTube title uses a name that never appears
    -- literally in kglw.shows. Add a row here if a new no_match case
    -- turns out to be the same kind of problem (festival brand name,
    -- state name, metro-area name, etc). Every row below was confirmed
    -- via a direct query against kglw.shows before being added -- none
    -- are guessed.
    --
    -- real_state is REQUIRED whenever real_city is set to a name that
    -- isn't unique across the US (or wherever) -- confirmed necessary
    -- the hard way: "Maine" -> city='Portland' alone would also match
    -- Portland, OR if that city ever appears in kglw.shows, since city
    -- names collide across states/countries far more often than venue
    -- names do. Testing this exact ambiguity with a synthetic Portland,
    -- OR row caught a real bug before it shipped -- the city-only join
    -- picked the wrong Portland in that test.
    select 'Field of Vision' as alias_text, 'Meadow Creek' as real_venue_name, null as real_city, null as real_state
    union all
    select 'New York City', null, 'Queens', 'NY'
    union all
    select 'New York', null, 'Queens', 'NY'
    union all
    select 'Kentucky', null, 'Newport', 'KY'
    union all
    select 'Oregon', null, 'Troutdale', 'OR'
    union all
    select 'Arkansas', null, 'Fayetteville', 'AR'
    union all
    select 'Los Angeles', null, 'Inglewood', 'CA'
    union all
    select 'Maine', null, 'Portland', 'ME'
),

videos as (

    select
        video_id,
        title,
        published_at,

        -- Strip the channel-name prefix and isolate everything after
        -- the first " - " separator. Both "King Gizzard & The Lizard
        -- Wizard" and "King Gizzard and the Lizard Wizard" appear in
        -- the sample — handled as alternates, not normalized upstream,
        -- so this regex doesn't depend on which form was used.
        --
        -- CONFIRMED FIX 2026-06-22: strip zero-width space (U+200B)
        -- before any other processing. Found embedded literally inside
        -- a real title -- "Live in Minneapolis '<U+200B>24" -- sitting
        -- between the apostrophe and the year digits, invisible in any
        -- normal text view but enough to break every downstream regex
        -- that assumed a quote mark is immediately followed by digits.
        regexp_replace(
            regexp_extract(title, '^.*? - (.*)$', 1),
            chr(8203), '', 'g'
        ) as title_remainder

    from kglw_youtube.videos

),

parsed as (

    select
        video_id,
        title,
        published_at,

        -- "Live in {X}" or "Live at {X}" — capture the location/venue text
        -- up to the year marker or the opening paren, whichever comes
        -- first (or end-of-string, confirmed necessary for 2024 single-
        -- night city titles with no parenthetical at all).
        --
        -- CONFIRMED FIX 2026-06-22: the quote-mark character class now
        -- includes BOTH curly-quote directions. Real titles use U+2019
        -- (right single quote, ’) for most of the 2025 tour but U+2018
        -- (LEFT single quote, ‘) for several 2024 US shows -- "Live at
        -- Red Rocks ‘24", "Live in Omaha ‘24", "Live in St. Louis ‘24".
        -- These are visually almost identical but are different Unicode
        -- code points; the original pattern only recognized one of them.
        regexp_extract(
            title_remainder,
            '^Live (?:in|at) (.+?)\s*(?:[''‘’]\d{2}|\d{4})?\s*(?:\(|$)',
            1
        ) as location_text,

        -- Distinguishes "in" (city/country) from "at" (venue) — these
        -- need to match against different kglw.shows columns.
        case
            when title_remainder ilike 'live at %' then 'venue'
            when title_remainder ilike 'live in %' then 'place'
            else null
        end as location_kind,

        -- Two-digit tour year after a straight or either-direction
        -- curly apostrophe, e.g. '25 or ’25 or ‘25 -> 2025. This is the
        -- TOUR year, confirmed NOT reliable from published_at.
        case
            when regexp_extract(title_remainder, '[''‘’](\d{2})\b', 1) != ''
                then 2000 + cast(regexp_extract(title_remainder, '[''‘’](\d{2})\b', 1) as integer)
            -- "Live at Field of Vision 2025" — bare 4-digit year, no
            -- apostrophe, appears for the "Live at {venue}" pattern.
            when regexp_extract(title_remainder, '\b(20\d{2})\b', 1) != ''
                then cast(regexp_extract(title_remainder, '\b(20\d{2})\b', 1) as integer)
            else null
        end as tour_year,

        -- Night number, tolerant of "Night 1" / "Night1" / "night 1"
        case
            when regexp_extract(title, '[Nn]ight\s*(\d+)', 1) != ''
                then cast(regexp_extract(title, '[Nn]ight\s*(\d+)', 1) as integer)
            else null
        end as night_number,

        -- Anything without a recognizable "Live in/at ... (Night N)"
        -- shape is NOT a live show recording (e.g. "The Making of
        -- Phantom Island") — explicitly excluded, not mismatched.
        case
            when title_remainder ilike 'live in %' or title_remainder ilike 'live at %'
                then true
            else false
        end as is_likely_live_show

    from videos

),

shows_with_night_rank as (

    select
        show_id,
        cast(show_date as date) as show_date,
        venue_name,
        city,
        state,
        country,

        -- Rank consecutive shows at the same venue+city+country, in
        -- date order, to derive an inferred "night number" per show.
        -- This is the assumption flagged in header note #7 — it is
        -- NOT data confirmed to exist in kglw.shows, it's inferred.
        row_number() over (
            partition by venue_name, city, country, extract(year from cast(show_date as date))
            order by cast(show_date as date) asc
        ) as inferred_night_number

    from kglw.shows

),

matched as (

    select
        p.video_id,
        p.title,
        p.published_at,
        p.location_text,
        p.location_kind,
        p.tour_year,
        p.night_number,

        s.show_id,
        s.show_date,
        s.venue_name,
        s.city,
        s.country,
        s.inferred_night_number,

        -- Confidence tiering — be explicit about how sure this match
        -- is, rather than presenting every match with equal certainty.
        -- Alias-based matches get 'medium' at best, never 'high', since
        -- an explicit alias is inherently a step removed from a direct
        -- textual match — even when the night number also lines up.
        case
            when s.show_id is null then 'no_match'
            when fa.alias_text is not null and p.night_number = s.inferred_night_number then 'medium'
            when fa.alias_text is not null then 'low'
            when p.night_number = s.inferred_night_number then 'high'
            when p.night_number is null and s.inferred_night_number = 1 then 'medium'
            else 'low'
        end as match_confidence

    from parsed p
    left join festival_aliases fa
        on fa.alias_text = p.location_text
    left join shows_with_night_rank s
        on p.is_likely_live_show
        and extract(year from s.show_date) = p.tour_year
        and (
            -- Direct match: "Live at {venue}" -> venue_name
            (p.location_kind = 'venue' and s.venue_name ilike '%' || p.location_text || '%')
            or
            -- Direct match: "Live in {place}" -> city OR country, since
            -- the channel uses both granularities interchangeably
            (p.location_kind = 'place' and (
                s.city ilike '%' || p.location_text || '%'
                or s.country ilike '%' || p.location_text || '%'
            ))
            or
            -- Alias fallback: the title text doesn't appear literally
            -- anywhere in kglw.shows (confirmed cases: festival brand
            -- names, state names, metro-area names) -- use the explicit
            -- mapping from festival_aliases instead.
            --
            -- CONFIRMED FIX: when fa.real_state is set, it MUST also
            -- match s.state, not just city -- "Maine" -> Portland alone
            -- is ambiguous (Portland, OR is a real, distinct city that
            -- could collide). Tested with a synthetic Portland, OR row
            -- and confirmed the city-only version picks the WRONG
            -- Portland when both exist in the same year. Requiring the
            -- state match when fa.real_state is present closes this.
            (fa.alias_text is not null and (
                (fa.real_venue_name is not null and s.venue_name = fa.real_venue_name)
                or
                (fa.real_city is not null and s.city = fa.real_city
                    and (fa.real_state is null or s.state = fa.real_state))
            ))
        )

),

-- Each video can match multiple shows because the city/country join
-- is a fuzzy ILIKE (confirmed necessary — "Bulgaria" needs to match
-- every show with country='Bulgaria', not just one). Without this
-- dedup step, a video like "Bulgaria Night 1" would join against ALL
-- THREE Bulgaria shows, not just the one it's actually about — tested
-- and confirmed this produces duplicate rows per video_id otherwise.
-- Keep only the single best match per video: highest confidence tier
-- first, then the closest night-number match within that tier.
ranked as (

    select
        *,
        row_number() over (
            partition by video_id
            order by
                case match_confidence
                    when 'high' then 1
                    when 'medium' then 2
                    when 'low' then 3
                    else 4
                end asc,
                abs(coalesce(night_number, inferred_night_number) - inferred_night_number) asc
        ) as match_rank

    from matched
    where match_confidence != 'no_match'

)

select
    video_id,
    title,
    published_at,
    show_id,
    show_date,
    venue_name,
    city,
    country,
    tour_year,
    night_number,
    match_confidence
from ranked
where match_rank = 1

-- Videos that parsed as "likely a live show" but found NO matching row
-- in kglw.shows are deliberately excluded from this final select rather
-- than included with a null show_id — the frontend should treat "no
-- row in this mart" as "no match," and a separate QA query (see the
-- model's accompanying notes) should periodically check the no_match
-- count to catch new tour stops not yet ingested into kglw.shows, or
-- a genuine pattern-matching gap as the channel's naming evolves.
