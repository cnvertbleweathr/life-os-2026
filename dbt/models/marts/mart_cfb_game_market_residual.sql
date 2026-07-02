-- mart_cfb_game_market_residual.sql
--
-- Phase B of the Quality-of-Win/SOS system (design v5).
-- One row per (completed game, team). Computes the spread residual
-- (actual margin vs market expected margin) and transforms it into
-- a bounded 0-10 result score via tanh.
--
-- IMPORTANT: is_verified_close = false for all historical rows.
-- CFBD's /lines endpoint has no timestamp field (confirmed Phase 0.1).
-- The 'spread' field here is CFBD's best available historical reference
-- line, NOT a verified closing line. Named accordingly.
--
-- scale parameter: empirically estimated from dev seasons (2021-2023)
-- spread-error dispersion. Computed in scripts/estimate_scale.py,
-- locked here as a constant. Must not be re-estimated from param-
-- selection or holdout seasons.
-- Dev-season robust scale estimate: 10.5 (median absolute deviation
-- of actual_margin - expected_margin across 2,685 deduplicated 2021-2023
-- FBS games). Estimated by scripts/estimate_scale.py, confirmed against
-- real warehouse 2026-06-30. This is locked. Do not change without
-- re-running estimate_scale.py on dev seasons only.

with games as (
    select
        l.game_id,
        l.season,
        l.week,
        l.home_team,
        l.away_team,
        l.home_conference,
        l.home_score,
        l.away_score,
        l.spread,
        l.over_under,
        l.provider,
        -- Honest naming: not verified as closing line
        cast(l.spread as double)    as historical_reference_line,
        cast(l.over_under as double) as historical_reference_total,
        false                        as is_verified_close,
        l.neutral_site
    from main_marts.mart_cfbd_line_accuracy l
    where l.home_score is not null
      and l.away_score is not null
      and l.spread is not null
      and l.home_conference in (
          'SEC', 'Big Ten', 'Big 12', 'ACC', 'Pac-12',
          'American Athletic', 'Mountain West', 'Conference USA',
          'Mid-American', 'Sun Belt', 'FBS Independents'
      )
),

residuals as (
    select
        game_id, season, week,
        home_team, away_team, home_conference,
        home_score, away_score,
        historical_reference_line,
        historical_reference_total,
        is_verified_close,
        neutral_site,
        provider,

        -- Market expectation (home perspective):
        -- spread is stored as home_spread (negative = home favored)
        -historical_reference_line as expected_home_margin,

        -- Actual margin
        (home_score - away_score)  as actual_home_margin,

        -- Spread residual: positive = home outperformed market expectation
        (home_score - away_score) - (-historical_reference_line) as home_spread_residual,
        (away_score - home_score) - historical_reference_line    as away_spread_residual,

        -- Market-implied team points (requires total to be available)
        -- Algebra: home_pts = (total - spread) / 2, away_pts = (total + spread) / 2
        -- Verified algebraically: solving home - away = -spread AND home + away = total
        case when historical_reference_total is not null then
            (historical_reference_total - historical_reference_line) / 2.0
        end as implied_home_points,
        case when historical_reference_total is not null then
            (historical_reference_total + historical_reference_line) / 2.0
        end as implied_away_points,

        -- Scoring residuals (points_for vs market-implied)
        -- NOTE: named as 'scoring' not 'offensive/defensive' --
        -- actual points scored includes defensive TDs, ST scores, etc.
        -- Not pure offensive/defensive performance. See design v5.
        case when historical_reference_total is not null then
            home_score - (historical_reference_total - historical_reference_line) / 2.0
        end as home_points_for_residual,
        case when historical_reference_total is not null then
            (historical_reference_total - historical_reference_line) / 2.0 - away_score
        end as home_points_against_residual,
        case when historical_reference_total is not null then
            away_score - (historical_reference_total + historical_reference_line) / 2.0
        end as away_points_for_residual,
        case when historical_reference_total is not null then
            (historical_reference_total + historical_reference_line) / 2.0 - home_score
        end as away_points_against_residual,

        -- 0-10 result score via tanh with locked scale=10.5
        -- scale estimated from dev seasons (2021-2023) MAD of spread residuals
        -- across 2,685 deduplicated FBS games. Higher = outperformed market.
        5.0 + 5.0 * tanh(
            (home_score - away_score - (-historical_reference_line)) / 10.5
        ) as home_result_score,
        5.0 + 5.0 * tanh(
            (away_score - home_score - historical_reference_line) / 10.5
        ) as away_result_score

    from games
)

-- Output: two rows per game (one per team perspective)
select
    game_id, season, week, neutral_site,
    is_verified_close, provider,
    home_team as team,
    away_team as opponent,
    'home' as home_away,
    actual_home_margin as actual_margin,
    expected_home_margin as expected_margin,
    home_spread_residual as spread_residual,
    home_points_for_residual as points_for_residual,
    home_points_against_residual as points_against_residual,
    round(home_result_score, 4) as result_score,
    historical_reference_line,
    historical_reference_total,
    implied_home_points as implied_points_for,
    implied_away_points as implied_points_against

from residuals

union all

select
    game_id, season, week, neutral_site,
    is_verified_close, provider,
    away_team as team,
    home_team as opponent,
    'away' as home_away,
    (away_score - home_score) as actual_margin,
    -expected_home_margin as expected_margin,
    away_spread_residual as spread_residual,
    away_points_for_residual as points_for_residual,
    away_points_against_residual as points_against_residual,
    round(away_result_score, 4) as result_score,
    historical_reference_line,
    historical_reference_total,
    implied_away_points as implied_points_for,
    implied_home_points as implied_points_against

from residuals

order by season, week, game_id, home_away
