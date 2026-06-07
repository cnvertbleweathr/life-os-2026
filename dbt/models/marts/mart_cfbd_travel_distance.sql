-- mart_cfbd_travel_distance
--
-- Computes away team travel distance for every game using haversine formula.
-- venue_id lives in cfbd.weather (extended pipeline) joined to cfbd.venues.
-- Away team home venue = most common venue they hosted home games at (last 3 seasons).
--
-- Distance buckets:
--   local:         < 200 miles
--   regional:      200-500 miles
--   far:           500-1000 miles
--   very_far:      1000-1500 miles
--   cross_country: > 1500 miles

with game_venues as (
    -- cfbd.weather has venue_id; join to cfbd.venues for lat/long
    -- then pull spread/result from mart_cfbd_line_accuracy
    select
        l.game_id,
        l.season,
        l.week,
        l.home_team,
        l.away_team,
        l.home_conference,
        l.away_conference,
        l.spread,
        l.spread_covered,
        l.ou_result,
        l.home_score,
        l.away_score,
        v.latitude      as game_lat,
        v.longitude     as game_lon,
        v.dome          as game_indoors,
        v.city          as game_city,
        v.state         as game_state,
        w.venue_id
    from main_marts.mart_cfbd_line_accuracy l
    left join cfbd.weather w
        on w.game_id = l.game_id
    left join cfbd.venues v
        on v.venue_id = w.venue_id
    where v.latitude  is not null
      and v.longitude is not null
),

-- Each team's home venue = most common venue_id across their home games
-- Use cfbd.weather as the source since it has venue_id per game
team_home_venues as (
    select
        w.home_team as team,
        w.venue_id,
        count(*)    as games_there
    from cfbd.weather w
    where w.venue_id is not null
      and w.season   >= 2022
    group by w.home_team, w.venue_id
    qualify row_number() over (
        partition by w.home_team
        order by count(*) desc
    ) = 1
),

team_home_locations as (
    select
        t.team,
        v.latitude  as home_lat,
        v.longitude as home_lon,
        v.city      as home_city,
        v.state     as home_state,
        v.dome      as home_dome
    from team_home_venues t
    join cfbd.venues v
        on v.venue_id = t.venue_id
    where v.latitude  is not null
      and v.longitude is not null
),

-- Haversine formula: distance in miles between two lat/long points
with_distance as (
    select
        gv.*,
        ahl.home_lat   as away_home_lat,
        ahl.home_lon   as away_home_lon,
        ahl.home_city  as away_home_city,
        ahl.home_state as away_home_state,

        case
            when ahl.home_lat is null or ahl.home_lon is null then null
            else round(
                3958.8 * 2 * asin(
                    sqrt(
                        power(sin(radians(gv.game_lat - ahl.home_lat) / 2), 2) +
                        cos(radians(ahl.home_lat)) *
                        cos(radians(gv.game_lat)) *
                        power(sin(radians(gv.game_lon - ahl.home_lon) / 2), 2)
                    )
                ), 1
            )
        end as travel_miles

    from game_venues gv
    left join team_home_locations ahl
        on ahl.team = gv.away_team
),

with_buckets as (
    select
        *,
        case
            when travel_miles is null  then 'unknown'
            when travel_miles < 200    then 'local'
            when travel_miles < 500    then 'regional'
            when travel_miles < 1000   then 'far'
            when travel_miles < 1500   then 'very_far'
            else                            'cross_country'
        end as travel_bucket,

        travel_miles >= 1000 as long_haul,
        travel_miles >= 1500 as cross_country,

        -- Neutral site flag: game not in away team's home state
        game_state != away_home_state as possible_neutral_site

    from with_distance
)

select
    game_id,
    season,
    week,
    home_team,
    away_team,
    home_conference,
    away_conference,
    spread,
    spread_covered,
    ou_result,
    game_lat,
    game_lon,
    game_city,
    game_state,
    game_indoors,
    away_home_lat,
    away_home_lon,
    away_home_city,
    away_home_state,
    travel_miles,
    travel_bucket,
    long_haul,
    cross_country,
    possible_neutral_site

from with_buckets
order by season desc, week desc, travel_miles desc nulls last
