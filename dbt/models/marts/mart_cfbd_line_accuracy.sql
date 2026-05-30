-- mart_cfbd_line_accuracy.sql
--
-- One row per game per provider with:
--   - Actual result vs spread/O/U
--   - SP+ differential (pregame true strength gap)
--   - Home/away, conference, neutral site flags
--   - Cover/miss/push classification
--
-- This is the core table powering all CFB betting analysis.

with lines as (
    select * from cfbd.lines
    where spread is not null
      and home_score is not null
      and away_score is not null
),

games as (
    select * from cfbd.games
),

sp as (
    select * from cfbd.sp_ratings
),

joined as (
    select
        l.game_id,
        l.season,
        l.week,
        l.season_type,
        l.provider,

        -- Teams
        l.home_team,
        l.away_team,
        g.home_conference,
        g.away_conference,
        g.neutral_site,
        g.conference_game,

        -- Scores
        l.home_score,
        l.away_score,
        l.total_points,
        l.actual_margin,
        l.home_win,

        -- Lines
        l.spread,
        l.spread_open,
        l.over_under,
        l.over_under_open,
        l.home_moneyline,
        l.away_moneyline,

        -- Derived line fields
        cast(l.spread as double) as spread_num,
        cast(l.over_under as double) as over_under_num,

        -- Favorite identification
        case
            when cast(l.spread as double) < 0 then l.home_team
            when cast(l.spread as double) > 0 then l.away_team
            else 'pick'
        end as favorite,

        abs(cast(l.spread as double)) as spread_abs,

        -- Spread result
        l.spread_covered,
        l.spread_push,

        -- O/U result
        l.ou_result,
        l.ou_push,

        -- Margin vs spread (how far off was the line)
        l.actual_margin - (-cast(l.spread as double)) as margin_vs_spread,
        l.total_points - cast(l.over_under as double) as total_vs_ou,

        -- SP+ differential (home_sp - away_sp)
        home_sp.rating  as home_sp_rating,
        away_sp.rating  as away_sp_rating,
        home_sp.rating - away_sp.rating as sp_differential,

        -- Home field: does SP+ agree with the line direction?
        case
            when home_sp.rating > away_sp.rating and cast(l.spread as double) < 0 then true
            when home_sp.rating < away_sp.rating and cast(l.spread as double) > 0 then true
            else false
        end as sp_agrees_with_line,

        -- Line movement (open vs close)
        cast(l.spread as double) - cast(l.spread_open as double) as spread_movement,
        cast(l.over_under as double) - cast(l.over_under_open as double) as ou_movement,

    from lines l
    left join games g
        on l.game_id = g.game_id
    left join sp home_sp
        on l.home_team = home_sp.team and l.season = home_sp.season
    left join sp away_sp
        on l.away_team = away_sp.team and l.season = away_sp.season
)

select
    *,

    -- Spread cover bucket
    case
        when spread_push then 'push'
        when spread_covered then 'covered'
        when spread_covered = false then 'missed'
        else 'unknown'
    end as spread_result,

    -- O/U bucket
    case
        when ou_push then 'push'
        when ou_result = 'over' then 'over'
        when ou_result = 'under' then 'under'
        else 'unknown'
    end as ou_bucket,

    -- Underdog flag (home team getting points)
    spread_num > 0 as home_is_underdog,

    -- Big spread flag (double digit)
    spread_abs >= 10 as is_big_spread,
    spread_abs >= 17 as is_massive_spread,

    -- SP+ upset potential (SP disagrees with line direction significantly)
    abs(sp_differential) > 10 and not sp_agrees_with_line as sp_upset_alert

from joined
