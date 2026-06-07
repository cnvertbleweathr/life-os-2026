-- mart_cfbd_coach_matchups
--
-- All-time head-to-head records between any pair of coaches.
-- Uses mart_cfbd_game_context which already has home_coach + away_coach.
--
-- One row per coach pair (alphabetically ordered to avoid duplicates),
-- plus a separate lookup view for quick directional queries.
--
-- Key fields:
--   coach1_wins       — wins for alphabetically-first coach
--   coach2_wins       — wins for alphabetically-second coach
--   last_3_winner     — who won the last 3 matchups
--   home_advantage    — does home field matter in this matchup?
--   recent_trend      — who's been dominant in the last 3 years?

with games as (
    select
        game_id,
        season,
        week,
        home_team,
        away_team,
        home_coach,
        away_coach,
        -- did home team cover the spread?
        spread_covered,
        -- actual result
        home_score,
        away_score,
        case
            when home_score > away_score then home_coach
            when away_score > home_score then away_coach
            else null
        end as winning_coach,
        case
            when home_score > away_score then away_coach
            when away_score > home_score then home_coach
            else null
        end as losing_coach
    from main_marts.mart_cfbd_game_context
    where home_coach is not null
      and away_coach is not null
      and home_score is not null
),

-- Normalize coach pairs alphabetically so A vs B and B vs A are the same row
normalized as (
    select
        *,
        case when home_coach < away_coach then home_coach else away_coach end as coach_a,
        case when home_coach < away_coach then away_coach else home_coach end as coach_b,
        case when home_coach < away_coach then home_coach else away_coach end = winning_coach
            as coach_a_won
    from games
    where home_coach != away_coach
),

-- Aggregate H2H record
h2h as (
    select
        coach_a,
        coach_b,
        count(*)                                                         as total_games,
        sum(case when coach_a_won = true  then 1 else 0 end)            as coach_a_wins,
        sum(case when coach_a_won = false and winning_coach is not null
                 then 1 else 0 end)                                      as coach_b_wins,
        sum(case when winning_coach is null then 1 else 0 end)           as ties,
        min(season)                                                       as first_matchup,
        max(season)                                                       as last_matchup,

        -- Last 3 games list
        list(winning_coach order by season desc, week desc) [1:3]        as last_3_winners,
        list(season        order by season desc, week desc) [1:3]        as last_3_seasons,

        -- Home win rate: how often does the home coach win?
        round(
            avg(case when winning_coach = home_coach then 1.0 else 0.0 end) * 100,
            1
        )                                                                 as home_win_pct,

        -- ATS performance when these coaches meet
        round(
            avg(case when spread_covered = true then 1.0 else 0.0 end) * 100,
            1
        )                                                                 as home_ats_pct

    from normalized
    group by coach_a, coach_b
    having count(*) >= 1
),

-- Compute recent wins separately (last 3 seasons per pair)
-- Can't use window functions inside aggregates in DuckDB
recent_cutoff as (
    select max(season) - 2 as cutoff_season
    from normalized
),

recent_wins as (
    select
        n.coach_a,
        n.coach_b,
        sum(case when n.coach_a_won = true  then 1 else 0 end) as coach_a_recent_wins,
        sum(case when n.coach_a_won = false
                  and n.winning_coach is not null then 1 else 0 end) as coach_b_recent_wins
    from normalized n
    cross join recent_cutoff rc
    where n.season >= rc.cutoff_season
    group by n.coach_a, n.coach_b
),

with_joined as (
    select
        h.*,
        coalesce(r.coach_a_recent_wins, 0) as coach_a_recent_wins,
        coalesce(r.coach_b_recent_wins, 0) as coach_b_recent_wins
    from h2h h
    left join recent_wins r
        on r.coach_a = h.coach_a
        and r.coach_b = h.coach_b
),

with_derived as (
    select
        *,
        -- Who has the all-time edge?
        case
            when coach_a_wins > coach_b_wins then coach_a
            when coach_b_wins > coach_a_wins then coach_b
            else 'even'
        end as all_time_leader,

        -- Is home field significant in this matchup?
        home_win_pct >= 65 or home_win_pct <= 35 as home_matters,

        -- Recent trend leader (last 3 years)
        case
            when coach_a_recent_wins > coach_b_recent_wins then coach_a
            when coach_b_recent_wins > coach_a_recent_wins then coach_b
            else 'even'
        end as recent_trend_leader

    from with_joined
)

select * from with_derived
order by total_games desc, last_matchup desc
