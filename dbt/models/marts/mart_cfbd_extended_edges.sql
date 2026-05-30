-- mart_cfbd_extended_edges.sql
--
-- Cover rates broken down by all extended context factors.
-- The money table for betting research.

with base as (
    select * from {{ ref('mart_cfbd_game_context') }}
    where spread_result in ('covered', 'missed')
      and ou_bucket in ('over', 'under')
),

-- Weather impact
weather_edges as (
    select
        'weather' as factor_type,
        weather_impact as factor_value,
        count(*) as games,
        round(avg(case when spread_covered then 1.0 else 0.0 end) * 100, 1) as ats_pct,
        round(avg(case when ou_result = 'over' then 1.0 else 0.0 end) * 100, 1) as over_pct,
        round(avg(abs(margin_vs_spread)), 1) as avg_margin_error,
        round(avg(abs(total_vs_ou)), 1) as avg_ou_error,
    from base
    where weather_impact is not null
    group by weather_impact
    having count(*) >= 20
),

-- Wind specifically
wind_edges as (
    select
        'high_wind' as factor_type,
        case when high_wind then 'high wind (20+ mph)' else 'normal wind' end as factor_value,
        count(*) as games,
        round(avg(case when spread_covered then 1.0 else 0.0 end) * 100, 1) as ats_pct,
        round(avg(case when ou_result = 'over' then 1.0 else 0.0 end) * 100, 1) as over_pct,
        round(avg(abs(margin_vs_spread)), 1) as avg_margin_error,
        round(avg(abs(total_vs_ou)), 1) as avg_ou_error,
    from base
    where high_wind is not null and not game_indoors
    group by high_wind
    having count(*) >= 20
),

-- Temperature buckets
temp_edges as (
    select
        'temperature' as factor_type,
        temp_bucket as factor_value,
        count(*) as games,
        round(avg(case when spread_covered then 1.0 else 0.0 end) * 100, 1) as ats_pct,
        round(avg(case when ou_result = 'over' then 1.0 else 0.0 end) * 100, 1) as over_pct,
        round(avg(abs(margin_vs_spread)), 1) as avg_margin_error,
        round(avg(abs(total_vs_ou)), 1) as avg_ou_error,
    from base
    where temp_bucket is not null
    group by temp_bucket
    having count(*) >= 20
),

-- Rivalry games
rivalry_edges as (
    select
        'rivalry' as factor_type,
        case when is_rivalry_game then 'rivalry game' else 'non-rivalry' end as factor_value,
        count(*) as games,
        round(avg(case when spread_covered then 1.0 else 0.0 end) * 100, 1) as ats_pct,
        round(avg(case when ou_result = 'over' then 1.0 else 0.0 end) * 100, 1) as over_pct,
        round(avg(abs(margin_vs_spread)), 1) as avg_margin_error,
        round(avg(abs(total_vs_ou)), 1) as avg_ou_error,
    from base
    group by is_rivalry_game
    having count(*) >= 20
),

-- Returning production edge
returning_edges as (
    select
        'returning_production' as factor_type,
        returning_edge as factor_value,
        count(*) as games,
        round(avg(case when spread_covered then 1.0 else 0.0 end) * 100, 1) as ats_pct,
        round(avg(case when ou_result = 'over' then 1.0 else 0.0 end) * 100, 1) as over_pct,
        round(avg(abs(margin_vs_spread)), 1) as avg_margin_error,
        round(avg(abs(total_vs_ou)), 1) as avg_ou_error,
    from base
    where returning_edge is not null
    group by returning_edge
    having count(*) >= 20
),

-- Talent gap (recruiting)
talent_edges as (
    select
        'talent_gap' as factor_type,
        talent_gap_bucket as factor_value,
        count(*) as games,
        round(avg(case when spread_covered then 1.0 else 0.0 end) * 100, 1) as ats_pct,
        round(avg(case when ou_result = 'over' then 1.0 else 0.0 end) * 100, 1) as over_pct,
        round(avg(abs(margin_vs_spread)), 1) as avg_margin_error,
        round(avg(abs(total_vs_ou)), 1) as avg_ou_error,
    from base
    where talent_gap_bucket is not null
    group by talent_gap_bucket
    having count(*) >= 20
),

-- Draft pipeline (home team)
draft_edges as (
    select
        'home_draft_pipeline' as factor_type,
        case
            when home_draft_picks_ytd >= 5 then '5+ picks (elite pipeline)'
            when home_draft_picks_ytd >= 3 then '3-4 picks (strong pipeline)'
            when home_draft_picks_ytd >= 1 then '1-2 picks'
            when home_draft_picks_ytd = 0  then '0 picks'
            else 'unknown'
        end as factor_value,
        count(*) as games,
        round(avg(case when spread_covered then 1.0 else 0.0 end) * 100, 1) as ats_pct,
        round(avg(case when ou_result = 'over' then 1.0 else 0.0 end) * 100, 1) as over_pct,
        round(avg(abs(margin_vs_spread)), 1) as avg_margin_error,
        round(avg(abs(total_vs_ou)), 1) as avg_ou_error,
    from base
    where home_draft_picks_ytd is not null
    group by 2
    having count(*) >= 20
),

-- Dome vs outdoor
dome_edges as (
    select
        'venue_type' as factor_type,
        case when game_indoors then 'dome' else 'outdoor' end as factor_value,
        count(*) as games,
        round(avg(case when spread_covered then 1.0 else 0.0 end) * 100, 1) as ats_pct,
        round(avg(case when ou_result = 'over' then 1.0 else 0.0 end) * 100, 1) as over_pct,
        round(avg(abs(margin_vs_spread)), 1) as avg_margin_error,
        round(avg(abs(total_vs_ou)), 1) as avg_ou_error,
    from base
    where game_indoors is not null
    group by game_indoors
    having count(*) >= 20
),

-- Home defensive strength (havoc rate quartiles)
def_strength_edges as (
    select
        'home_defense_strength' as factor_type,
        case
            when home_def_havoc >= 0.20 then 'elite havoc (20%+)'
            when home_def_havoc >= 0.15 then 'good havoc (15-20%)'
            when home_def_havoc >= 0.10 then 'avg havoc (10-15%)'
            when home_def_havoc < 0.10  then 'low havoc (<10%)'
            else 'unknown'
        end as factor_value,
        count(*) as games,
        round(avg(case when spread_covered then 1.0 else 0.0 end) * 100, 1) as ats_pct,
        round(avg(case when ou_result = 'over' then 1.0 else 0.0 end) * 100, 1) as over_pct,
        round(avg(abs(margin_vs_spread)), 1) as avg_margin_error,
        round(avg(abs(total_vs_ou)), 1) as avg_ou_error,
    from base
    where home_def_havoc is not null
    group by 2
    having count(*) >= 20
),

-- Running game strength
rushing_edges as (
    select
        'home_rushing_strength' as factor_type,
        case
            when home_rush_ppa >= 0.20 then 'elite rushing (0.20+ PPA)'
            when home_rush_ppa >= 0.10 then 'good rushing (0.10-0.20)'
            when home_rush_ppa >= 0.0  then 'avg rushing (0-0.10)'
            when home_rush_ppa < 0.0   then 'poor rushing (<0 PPA)'
            else 'unknown'
        end as factor_value,
        count(*) as games,
        round(avg(case when spread_covered then 1.0 else 0.0 end) * 100, 1) as ats_pct,
        round(avg(case when ou_result = 'over' then 1.0 else 0.0 end) * 100, 1) as over_pct,
        round(avg(abs(margin_vs_spread)), 1) as avg_margin_error,
        round(avg(abs(total_vs_ou)), 1) as avg_ou_error,
    from base
    where home_rush_ppa is not null
    group by 2
    having count(*) >= 20
),

-- Efficiency gap (home off PPA vs away def PPA)
efficiency_mismatch as (
    select
        'efficiency_mismatch' as factor_type,
        case
            when off_ppa_gap > 0.15  then 'home big off advantage'
            when off_ppa_gap > 0.05  then 'home slight off advantage'
            when off_ppa_gap < -0.15 then 'away big off advantage'
            when off_ppa_gap < -0.05 then 'away slight off advantage'
            else 'even'
        end as factor_value,
        count(*) as games,
        round(avg(case when spread_covered then 1.0 else 0.0 end) * 100, 1) as ats_pct,
        round(avg(case when ou_result = 'over' then 1.0 else 0.0 end) * 100, 1) as over_pct,
        round(avg(abs(margin_vs_spread)), 1) as avg_margin_error,
        round(avg(abs(total_vs_ou)), 1) as avg_ou_error,
    from base
    where off_ppa_gap is not null
    group by 2
    having count(*) >= 20
)

select * from weather_edges
union all select * from wind_edges
union all select * from temp_edges
union all select * from rivalry_edges
union all select * from returning_edges
union all select * from talent_edges
union all select * from draft_edges
union all select * from dome_edges
union all select * from def_strength_edges
union all select * from rushing_edges
union all select * from efficiency_mismatch
order by factor_type, ats_pct desc
