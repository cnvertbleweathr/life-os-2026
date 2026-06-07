-- mart_cfbd_game_signals
--
-- Master signal table: one row per game per week combining:
--   - Line movement (from mart_cfbd_line_movement)
--   - News signals (from cfbd.news_signals)
--   - PPA efficiency edge
--
-- This is the table that answers: "when the line moved, was there news?
-- And if so, what kind — and does it explain or contradict the movement?"
--
-- Signal interpretation:
--   movement_explained   = TRUE if high-strength news (≥5) found and movement ≥0.5
--   sharp_or_news        = TRUE if movement likely sharp (no news found)
--   overreaction_flag    = TRUE if news is minor but line moved significantly
--   confirm_bet          = movement + news + PPA all point same direction

with movement as (
    select * from {{ ref('mart_cfbd_line_movement') }}
),

-- Aggregate news signals per game — highest strength article wins
news_agg as (
    select
        game_id,
        season,
        week,

        -- Best signal found for each team
        max(signal_strength) filter (where team_affected = home_team) as home_max_signal,
        max(signal_strength) filter (where team_affected = away_team) as away_max_signal,

        -- Signal type of the best article
        arg_max(signal_type, signal_strength)
            filter (where team_affected = home_team) as home_signal_type,
        arg_max(signal_type, signal_strength)
            filter (where team_affected = away_team) as away_signal_type,

        -- Count meaningful articles (strength ≥3)
        count(*) filter (where signal_strength >= 3) as meaningful_articles,

        -- Was there a QB injury?
        max(case when signal_type = 'INJURY_QB' then 1 else 0 end) as qb_injury_found,

        -- Was there a suspension?
        max(case when signal_type = 'SUSPENSION' then 1 else 0 end) as suspension_found,

        -- Was there a weather signal?
        max(case when signal_type = 'WEATHER' then 1 else 0 end) as weather_signal,

        -- Headlines for display (top 3 by strength)
        list(title order by signal_strength desc) [1:3] as top_headlines,
        list(signal_type order by signal_strength desc) [1:3] as top_signal_types,
        list(team_affected order by signal_strength desc) [1:3] as top_signal_teams,

        max(snapshot_date) as news_date

    from cfbd.news_signals
    group by game_id, season, week
),

joined as (
    select
        m.*,
        n.home_max_signal,
        n.away_max_signal,
        n.home_signal_type,
        n.away_signal_type,
        n.meaningful_articles,
        n.qb_injury_found,
        n.suspension_found,
        n.weather_signal,
        n.top_headlines,
        n.top_signal_types,
        n.top_signal_teams,
        n.news_date,

        -- Combined signal strength (highest of home/away)
        greatest(
            coalesce(n.home_max_signal, 0),
            coalesce(n.away_max_signal, 0)
        ) as max_signal_strength

    from movement m
    left join news_agg n
        on n.game_id = m.game_id
        and n.season = m.season
        and n.week   = m.week
),

with_interpretation as (
    select
        *,

        -- Did news explain the movement?
        -- High-strength news (≥5) + significant movement
        case
            when max_signal_strength >= 5 and movement_magnitude >= 0.5
            then true
            else false
        end as movement_explained_by_news,

        -- Likely sharp money: movement present but no meaningful news
        case
            when movement_magnitude >= 0.5
                and (meaningful_articles is null or meaningful_articles = 0)
            then true
            else false
        end as likely_sharp_money,

        -- Overreaction flag: minor news but large movement
        -- Market may be overcorrecting — potential fade opportunity
        case
            when max_signal_strength between 1 and 3
                and movement_magnitude >= 1.5
            then true
            else false
        end as possible_overreaction,

        -- QB injury context: if home QB injured and line moved toward away team
        case
            when qb_injury_found = 1
                and home_signal_type = 'INJURY_QB'
                and sharp_signal = 'sharp_away'
            then 'HOME_QB_INJURY_EXPLAINS_MOVE'
            when qb_injury_found = 1
                and away_signal_type = 'INJURY_QB'
                and sharp_signal = 'sharp_home'
            then 'AWAY_QB_INJURY_EXPLAINS_MOVE'
            when qb_injury_found = 1
            then 'QB_INJURY_FOUND_MOVE_DIRECTION_UNCLEAR'
            else null
        end as injury_context,

        -- Master bet signal incorporating news
        -- Upgrades/downgrades composite_signal based on news context
        case
            -- QB injury to the team we want to bet — downgrade
            when composite_signal in ('STRONG_BET', 'BET')
                and qb_injury_found = 1
                and (
                    (ppa_gap > 0 and home_signal_type = 'INJURY_QB') or
                    (ppa_gap < 0 and away_signal_type = 'INJURY_QB')
                )
            then 'DOWNGRADE_QB_INJURY'

            -- Suspension to the team we want to bet — downgrade
            when composite_signal in ('STRONG_BET', 'BET')
                and suspension_found = 1
            then 'DOWNGRADE_SUSPENSION'

            -- Sharp money + model agree + no bad news — highest confidence
            when composite_signal = 'STRONG_BET'
                and likely_sharp_money = true
                and qb_injury_found = 0
            then 'PRIME_BET'

            -- Model signal + movement explained by news to opponent
            -- e.g. we like home team, away QB got hurt, line moved our way
            when composite_signal in ('STRONG_BET', 'BET')
                and movement_explained_by_news = true
                and likely_sharp_money = false
            then 'NEWS_CONFIRMS_BET'

            -- Possible overreaction — consider fading the news move
            when possible_overreaction = true
            then 'OVERREACTION_WATCH'

            else composite_signal
        end as master_signal

    from joined
)

select * from with_interpretation
order by season desc, week desc,
         case master_signal
             when 'PRIME_BET'           then 1
             when 'STRONG_BET'          then 2
             when 'NEWS_CONFIRMS_BET'   then 3
             when 'BET'                 then 4
             when 'OVERREACTION_WATCH'  then 5
             when 'FADE_SIGNAL'         then 6
             when 'DOWNGRADE_QB_INJURY' then 7
             when 'DOWNGRADE_SUSPENSION' then 8
             else 9
         end,
         movement_magnitude desc nulls last
