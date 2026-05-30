-- mart_cfbd_edge_factors.sql
--
-- Aggregated cover rates by situational factor.
-- This is where actionable betting edges surface:
--   "Home underdogs of 7-13.5 cover 58% of the time in SEC"
--   "Games with SP+ disagreement hit the over 54% of the time"
--
-- Excludes pushes from ATS% calculations (standard convention).

with base as (
    select *
    from {{ ref('mart_cfbd_line_accuracy') }}
    where spread_result in ('covered', 'missed')  -- exclude pushes
      and ou_bucket in ('over', 'under')           -- exclude O/U pushes
),

-- Overall accuracy
overall as (
    select
        'overall' as factor_type,
        'all games' as factor_value,
        count(*) as games,
        sum(case when spread_covered then 1 else 0 end) as covers,
        round(avg(case when spread_covered then 1.0 else 0.0 end) * 100, 1) as ats_pct,
        sum(case when ou_result = 'over' then 1 else 0 end) as overs,
        round(avg(case when ou_result = 'over' then 1.0 else 0.0 end) * 100, 1) as over_pct,
        round(avg(abs(margin_vs_spread)), 1) as avg_margin_vs_spread,
    from base
),

-- By home/away underdog status
by_dog_status as (
    select
        'dog_status' as factor_type,
        case
            when home_is_underdog then 'home underdog'
            else 'home favorite'
        end as factor_value,
        count(*) as games,
        sum(case when spread_covered then 1 else 0 end) as covers,
        round(avg(case when spread_covered then 1.0 else 0.0 end) * 100, 1) as ats_pct,
        sum(case when ou_result = 'over' then 1 else 0 end) as overs,
        round(avg(case when ou_result = 'over' then 1.0 else 0.0 end) * 100, 1) as over_pct,
        round(avg(abs(margin_vs_spread)), 1) as avg_margin_vs_spread,
    from base
    group by 2
),

-- By spread bucket
by_spread_size as (
    select
        'spread_size' as factor_type,
        case
            when spread_abs < 3  then '0-2.5 (pick em)'
            when spread_abs < 7  then '3-6.5 (field goal)'
            when spread_abs < 10 then '7-9.5 (TD range)'
            when spread_abs < 14 then '10-13.5 (10+ pts)'
            when spread_abs < 21 then '14-20.5 (2+ TDs)'
            else '21+ (blowout)'
        end as factor_value,
        count(*) as games,
        sum(case when spread_covered then 1 else 0 end) as covers,
        round(avg(case when spread_covered then 1.0 else 0.0 end) * 100, 1) as ats_pct,
        sum(case when ou_result = 'over' then 1 else 0 end) as overs,
        round(avg(case when ou_result = 'over' then 1.0 else 0.0 end) * 100, 1) as over_pct,
        round(avg(abs(margin_vs_spread)), 1) as avg_margin_vs_spread,
    from base
    group by 2
),

-- By home conference
by_home_conference as (
    select
        'home_conference' as factor_type,
        coalesce(home_conference, 'Independent') as factor_value,
        count(*) as games,
        sum(case when spread_covered then 1 else 0 end) as covers,
        round(avg(case when spread_covered then 1.0 else 0.0 end) * 100, 1) as ats_pct,
        sum(case when ou_result = 'over' then 1 else 0 end) as overs,
        round(avg(case when ou_result = 'over' then 1.0 else 0.0 end) * 100, 1) as over_pct,
        round(avg(abs(margin_vs_spread)), 1) as avg_margin_vs_spread,
    from base
    group by 2
    having count(*) >= 50
),

-- By SP+ agreement
by_sp_agreement as (
    select
        'sp_agreement' as factor_type,
        case
            when sp_agrees_with_line then 'SP+ agrees with line'
            when sp_upset_alert then 'SP+ upset alert'
            else 'SP+ mild disagreement'
        end as factor_value,
        count(*) as games,
        sum(case when spread_covered then 1 else 0 end) as covers,
        round(avg(case when spread_covered then 1.0 else 0.0 end) * 100, 1) as ats_pct,
        sum(case when ou_result = 'over' then 1 else 0 end) as overs,
        round(avg(case when ou_result = 'over' then 1.0 else 0.0 end) * 100, 1) as over_pct,
        round(avg(abs(margin_vs_spread)), 1) as avg_margin_vs_spread,
    from base
    where sp_agrees_with_line is not null
    group by 2
),

-- By neutral site
by_neutral as (
    select
        'neutral_site' as factor_type,
        case when neutral_site then 'neutral site' else 'home/away' end as factor_value,
        count(*) as games,
        sum(case when spread_covered then 1 else 0 end) as covers,
        round(avg(case when spread_covered then 1.0 else 0.0 end) * 100, 1) as ats_pct,
        sum(case when ou_result = 'over' then 1 else 0 end) as overs,
        round(avg(case when ou_result = 'over' then 1.0 else 0.0 end) * 100, 1) as over_pct,
        round(avg(abs(margin_vs_spread)), 1) as avg_margin_vs_spread,
    from base
    group by 2
),

-- By week (early season vs late season)
by_week as (
    select
        'week' as factor_type,
        case
            when week <= 3  then 'early season (wk 1-3)'
            when week <= 8  then 'mid season (wk 4-8)'
            when week <= 13 then 'late season (wk 9-13)'
            else 'bowl/playoff'
        end as factor_value,
        count(*) as games,
        sum(case when spread_covered then 1 else 0 end) as covers,
        round(avg(case when spread_covered then 1.0 else 0.0 end) * 100, 1) as ats_pct,
        sum(case when ou_result = 'over' then 1 else 0 end) as overs,
        round(avg(case when ou_result = 'over' then 1.0 else 0.0 end) * 100, 1) as over_pct,
        round(avg(abs(margin_vs_spread)), 1) as avg_margin_vs_spread,
    from base
    group by 2
),

-- By line movement direction
by_line_movement as (
    select
        'line_movement' as factor_type,
        case
            when spread_movement is null or spread_movement = 0 then 'no movement'
            when spread_movement < 0 then 'line moved toward home'
            else 'line moved toward away'
        end as factor_value,
        count(*) as games,
        sum(case when spread_covered then 1 else 0 end) as covers,
        round(avg(case when spread_covered then 1.0 else 0.0 end) * 100, 1) as ats_pct,
        sum(case when ou_result = 'over' then 1 else 0 end) as overs,
        round(avg(case when ou_result = 'over' then 1.0 else 0.0 end) * 100, 1) as over_pct,
        round(avg(abs(margin_vs_spread)), 1) as avg_margin_vs_spread,
    from base
    group by 2
)

select * from overall
union all select * from by_dog_status
union all select * from by_spread_size
union all select * from by_home_conference
union all select * from by_sp_agreement
union all select * from by_neutral
union all select * from by_week
union all select * from by_line_movement
order by factor_type, ats_pct desc
