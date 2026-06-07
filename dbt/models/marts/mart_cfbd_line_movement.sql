-- mart_cfbd_line_movement
--
-- One row per game per week showing the full line movement story:
--   open → current → close
--
-- Key computed fields:
--   spread_movement     — total movement from open to latest snapshot
--   sharp_signal        — direction of movement (negative = moved toward home)
--   sharp_agrees_model  — does movement direction match PPA efficiency edge?
--   movement_magnitude  — how much the line moved (abs value)
--   line_freeze         — TRUE if line barely moved (market confident)

with history as (
    select
        game_id,
        season,
        week,
        home_team,
        away_team,
        home_conference,
        provider,

        -- Opening line (first snapshot of the week)
        min(spread)          filter (where line_type = 'open') as spread_open,
        min(over_under)      filter (where line_type = 'open') as ou_open,

        -- Latest current line
        max(spread)          filter (where line_type = 'current') as spread_current,
        max(over_under)      filter (where line_type = 'current') as ou_current,

        -- Closing line (Saturday)
        min(spread)          filter (where line_type = 'close') as spread_close,
        min(over_under)      filter (where line_type = 'close') as ou_close,

        -- Latest snapshot regardless of type
        last(spread       order by snapshot_date) as spread_latest,
        last(over_under   order by snapshot_date) as ou_latest,
        last(snapshot_date order by snapshot_date) as last_updated,

        -- Number of daily snapshots taken
        count(distinct snapshot_date) as snapshots_taken,

        -- Movement per day (array for sparkline)
        list(spread order by snapshot_date) as spread_history,
        list(snapshot_date order by snapshot_date) as snapshot_dates

    from cfbd.line_history
    group by game_id, season, week, home_team, away_team, home_conference, provider
),

with_movement as (
    select
        *,

        -- Total movement: latest vs open
        case
            when spread_open is not null and spread_latest is not null
            then round(spread_latest - spread_open, 1)
        end as spread_movement,

        case
            when ou_open is not null and ou_latest is not null
            then round(ou_latest - ou_open, 1)
        end as ou_movement,

        -- Magnitude
        case
            when spread_open is not null and spread_latest is not null
            then abs(round(spread_latest - spread_open, 1))
        end as movement_magnitude

    from history
),

with_signals as (
    select
        *,

        -- Sharp signal direction:
        -- Negative movement = line moved toward home team (home team getting more expensive)
        -- Positive movement = line moved toward away team
        case
            when spread_movement < -0.5 then 'sharp_home'
            when spread_movement >  0.5 then 'sharp_away'
            else 'no_movement'
        end as sharp_signal,

        -- Line freeze: market very confident, barely moved
        movement_magnitude <= 0.5 as line_freeze,

        -- Significant move: half point or more
        movement_magnitude >= 0.5 as significant_move,

        -- Big move: full point or more
        movement_magnitude >= 1.0 as big_move,

        -- O/U movement signal
        case
            when ou_movement > 0.5  then 'sharp_over'
            when ou_movement < -0.5 then 'sharp_under'
            else 'no_movement'
        end as ou_sharp_signal

    from with_movement
),

-- Join PPA data to check if movement agrees with model
with_ppa as (
    select
        m.*,
        h_adv.off_ppa  as home_off_ppa,
        a_adv.off_ppa  as away_off_ppa,
        case
            when h_adv.off_ppa is not null and a_adv.off_ppa is not null
            then round(h_adv.off_ppa - a_adv.off_ppa, 4)
        end as ppa_gap,

        -- Does sharp money agree with model's PPA signal?
        case
            when h_adv.off_ppa is null or a_adv.off_ppa is null then null
            when h_adv.off_ppa > a_adv.off_ppa and sharp_signal = 'sharp_home' then true
            when h_adv.off_ppa < a_adv.off_ppa and sharp_signal = 'sharp_away' then true
            when sharp_signal = 'no_movement' then null
            else false
        end as sharp_agrees_model

    from with_signals m
    left join cfbd.advanced_stats h_adv
        on h_adv.team   = m.home_team
        and h_adv.season = m.season - 1  -- prior season efficiency
    left join cfbd.advanced_stats a_adv
        on a_adv.team   = m.away_team
        and a_adv.season = m.season - 1
)

select
    game_id,
    season,
    week,
    home_team,
    away_team,
    home_conference,
    provider,
    spread_open,
    spread_latest,
    spread_close,
    spread_movement,
    movement_magnitude,
    ou_open,
    ou_latest,
    ou_movement,
    sharp_signal,
    ou_sharp_signal,
    line_freeze,
    significant_move,
    big_move,
    sharp_agrees_model,
    ppa_gap,
    home_off_ppa,
    away_off_ppa,
    snapshots_taken,
    spread_history,
    snapshot_dates,
    last_updated,

    -- Composite bet signal:
    -- BET when PPA edge >0.15 AND sharp agrees AND spread in range
    case
        when abs(ppa_gap) > 0.15
            and sharp_agrees_model = true
            and spread_latest is not null
            and abs(spread_latest) between 3 and 17
        then 'STRONG_BET'
        when abs(ppa_gap) > 0.15
            and (sharp_agrees_model = true or sharp_signal = 'no_movement')
            and spread_latest is not null
            and abs(spread_latest) between 3 and 17
        then 'BET'
        when abs(ppa_gap) > 0.15
            and sharp_agrees_model = false
        then 'FADE_SIGNAL'  -- model says one thing, sharp money says opposite
        else 'PASS'
    end as composite_signal

from with_ppa
order by season desc, week desc, movement_magnitude desc nulls last
