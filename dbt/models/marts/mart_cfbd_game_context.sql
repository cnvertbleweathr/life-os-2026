-- mart_cfbd_game_context.sql
--
-- Master game context table — joins line accuracy with all extended factors:
--   - Weather (temp, wind, rain, dome)
--   - Coach for each team
--   - Returning production % (NIL/transfer portal effect)
--   - Travel distance (home vs away venue distance)
--   - Recruiting talent gap
--   - Draft production (program NFL pipeline)
--   - Rivalry flag
--
-- One row per game per provider (same grain as mart_cfbd_line_accuracy).
-- Use this table for notebook analysis and the extended edge finder.

with lines as (
    select * from {{ ref('mart_cfbd_line_accuracy') }}
    where spread_result in ('covered', 'missed')
),

weather as (
    select
        game_id,
        game_indoors,
        temperature,
        precipitation,
        snowfall,
        wind_speed,
        wind_direction,
        weather_condition,
        humidity,
        -- Derived weather buckets
        case
            when game_indoors then 'dome'
            when temperature < 32 then 'freezing (<32°F)'
            when temperature < 45 then 'cold (32-44°F)'
            when temperature > 85 then 'hot (85°F+)'
            else 'normal'
        end as temp_bucket,
        case
            when game_indoors then false
            when wind_speed >= 20 then true
            else false
        end as high_wind,
        case
            when game_indoors then false
            when precipitation > 0.1 then true
            else false
        end as rain_game,
        case
            when game_indoors then false
            when snowfall > 0 then true
            else false
        end as snow_game,
    from cfbd.weather
    where 1=1
),

-- Home coach this season
home_coaches as (
    select
        school as team,
        year as season,
        full_name as coach_name,
        wins,
        losses,
        games as coach_games_this_season,
    from cfbd.coaches
),

away_coaches as (
    select
        school as team,
        year as season,
        full_name as coach_name,
        wins,
        losses,
    from cfbd.coaches
),

-- Returning production
returning_prod as (
    select
        team,
        season,
        percent_ppa as pct_production_returning,
        percent_rushing_ppa as pct_rushing_returning,
        percent_passing_ppa as pct_passing_returning,
    from cfbd.returning_production
),

-- Venues with lat/long for travel distance
venues as (
    select
        name as venue_name,
        latitude,
        longitude,
        dome,
        grass,
        city,
        state,
    from cfbd.venues
),

-- Recruiting composite by team/year
recruiting as (
    select
        team,
        year as season,
        rank as recruiting_rank,
        points as recruiting_points,
    from cfbd.recruiting_rankings
),

-- PPA team metrics
ppa as (
    select
        team,
        season,
        off_ppa_overall,
        off_ppa_rushing,
        def_ppa_overall,
        def_ppa_rushing,
    from cfbd.ppa_teams
),

-- Advanced stats (defense strength, rushing strength)
adv as (
    select
        team,
        season,
        -- Offense
        off_ppa,
        off_success_rate,
        off_explosiveness,
        off_rush_ppa,
        off_rush_success_rate,
        off_line_yards,
        off_power_success,
        -- Defense
        def_ppa,
        def_success_rate,
        def_explosiveness,
        def_havoc_total,
        def_havoc_front_seven,
        def_rush_ppa,
        def_rush_success_rate,
        def_pass_ppa,
    from cfbd.advanced_stats
),

-- Draft picks per college per season (NFL pipeline)
-- We use a 4-year rolling window — players drafted this year were recruited 4 yrs ago
draft as (
    select
        college_team,
        year,
        count(*) as draft_picks,
        sum(case when round = 1 then 1 else 0 end) as first_round_picks,
        avg(overall) as avg_draft_position,
    from cfbd.draft_production
    group by college_team, year
),

-- Rivalry flag from matchup history
rivalries as (
    select
        team1,
        team2,
        team1_wins,
        team2_wins,
        total_games,
        true as is_rivalry
    from cfbd.matchup_history
),

base as (
    select
        l.*,

        -- Weather
        w.game_indoors,
        w.temperature,
        w.precipitation,
        w.snowfall,
        w.wind_speed,
        w.weather_condition,
        w.temp_bucket,
        w.high_wind,
        w.rain_game,
        w.snow_game,

        -- Coaches
        hc.coach_name as home_coach,
        ac.coach_name as away_coach,

        -- Returning production (prior year returning %)
        hr.pct_production_returning as home_pct_returning,
        hr.pct_rushing_returning    as home_pct_rushing_returning,
        ar.pct_production_returning as away_pct_returning,
        ar.pct_rushing_returning    as away_pct_rushing_returning,

        -- Returning production gap (home advantage)
        hr.pct_production_returning - ar.pct_production_returning as returning_production_gap,

        -- Recruiting
        hrec.recruiting_rank  as home_recruiting_rank,
        arec.recruiting_rank  as away_recruiting_rank,
        hrec.recruiting_points as home_recruiting_points,
        arec.recruiting_points as away_recruiting_points,
        hrec.recruiting_points - arec.recruiting_points as recruiting_gap,

        -- Draft pipeline
        hd.draft_picks       as home_draft_picks_ytd,
        hd.first_round_picks as home_first_round_picks_ytd,
        ad.draft_picks       as away_draft_picks_ytd,
        ad.first_round_picks as away_first_round_picks_ytd,

        -- Advanced stats — offensive efficiency
        hadv.off_ppa            as home_off_ppa,
        hadv.off_success_rate   as home_off_success_rate,
        hadv.off_explosiveness  as home_off_explosiveness,
        aadv.off_ppa            as away_off_ppa,
        aadv.off_success_rate   as away_off_success_rate,

        -- Advanced stats — rushing game strength
        hadv.off_rush_ppa           as home_rush_ppa,
        hadv.off_rush_success_rate  as home_rush_success_rate,
        hadv.off_line_yards         as home_line_yards,
        hadv.off_power_success      as home_power_success,
        aadv.off_rush_ppa           as away_rush_ppa,
        aadv.off_rush_success_rate  as away_rush_success_rate,

        -- Advanced stats — defensive strength
        hadv.def_ppa              as home_def_ppa,
        hadv.def_success_rate     as home_def_success_rate,
        hadv.def_havoc_total      as home_def_havoc,
        hadv.def_rush_ppa         as home_def_rush_ppa,
        aadv.def_ppa              as away_def_ppa,
        aadv.def_success_rate     as away_def_success_rate,
        aadv.def_havoc_total      as away_def_havoc,
        aadv.def_rush_ppa         as away_def_rush_ppa,

        -- Efficiency gaps (home - away)
        hadv.off_ppa - aadv.off_ppa                 as off_ppa_gap,
        hadv.def_ppa - aadv.def_ppa                 as def_ppa_gap,
        hadv.off_rush_ppa - aadv.off_rush_ppa       as rush_ppa_gap,
        hadv.def_havoc_total - aadv.def_havoc_total as havoc_gap,

        -- Rivalry
        coalesce(r1.is_rivalry, r2.is_rivalry, false) as is_rivalry_game,

    from lines l

    -- Weather
    left join weather w on l.game_id = w.game_id

    -- Coaches (match on team + season)
    left join home_coaches hc on l.home_team = hc.team and l.season = hc.season
    left join away_coaches ac on l.away_team = ac.team and l.season = ac.season

    -- Returning production (prior season — if game is 2024, returning from 2023)
    left join returning_prod hr on l.home_team = hr.team and l.season = hr.season
    left join returning_prod ar on l.away_team = ar.team and l.season = ar.season

    -- Recruiting
    left join recruiting hrec on l.home_team = hrec.team and l.season = hrec.season
    left join recruiting arec on l.away_team = arec.team and l.season = arec.season

    -- Advanced stats
    left join adv hadv on l.home_team = hadv.team and l.season = hadv.season
    left join adv aadv on l.away_team = aadv.team and l.season = aadv.season

    -- Draft production
    left join draft hd on l.home_team = hd.college_team and l.season = hd.year
    left join draft ad on l.away_team = ad.college_team and l.season = ad.year

    -- Rivalry (check both directions)
    left join rivalries r1 on l.home_team = r1.team1 and l.away_team = r1.team2
    left join rivalries r2 on l.home_team = r2.team2 and l.away_team = r2.team1
)

select
    *,

    -- Derived context flags
    case
        when high_wind and not game_indoors      then 'windy'
        when rain_game                            then 'rain'
        when snow_game                            then 'snow'
        when temp_bucket = 'freezing (<32°F)'    then 'freezing'
        when game_indoors                         then 'dome'
        else 'normal'
    end as weather_impact,

    -- Returning production advantage
    case
        when returning_production_gap > 0.15 then 'home big edge'
        when returning_production_gap > 0.05 then 'home slight edge'
        when returning_production_gap < -0.15 then 'away big edge'
        when returning_production_gap < -0.05 then 'away slight edge'
        else 'even'
    end as returning_edge,

    -- Recruiting gap bucket
    case
        when recruiting_gap > 30  then 'home talent advantage'
        when recruiting_gap > 10  then 'home slight talent edge'
        when recruiting_gap < -30 then 'away talent advantage'
        when recruiting_gap < -10 then 'away slight talent edge'
        else 'even talent'
    end as talent_gap_bucket

from base
