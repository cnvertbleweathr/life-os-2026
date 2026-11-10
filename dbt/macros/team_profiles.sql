{#
  team_profiles(league): walk-forward ATS profiles, one row per (team, season the
  profile applies to), built ONLY from that team's games in the four seasons before
  it (CFB's walk-forward v3, scripts/backtest_walk_forward.py -> build_tiers).

  ATS is the spread for the NBA and the puck line for the NHL (standard +-1.5 lines
  consistent with the moneyline only), settled at the actual price; nba
  historical_lines rows have no price and settle at -110. Pushes are counted, not
  in cover% or ROI. Splits: home / away x favourite / underdog (pick'em lines are
  in the overall numbers only). O/U lean: over% over the window (>= 55% OVER,
  <= 45% UNDER). NHL adds moneyline win% and ROI.

  Tier (CFB rules; n_prior = seasons with lines in the window):
    fewer than 10 decided games          -> NEUTRAL
    team seen in < 2 window seasons      -> FADE if ROI <= -15, else NEUTRAL
    ELITE        ROI >= 20 and seasons positive >= max(2, floor(0.8 n_prior))
    STRONG       ROI >= 10 and seasons positive >= max(2, floor(0.6 n_prior))
    STRONG_FADE  ROI <= -20 and seasons positive <= floor(0.2 n_prior)
    FADE         ROI <= -10
    NEUTRAL      otherwise
  Descriptive only: Phase 4 validated no rule, and tiers are not a betting signal
  unless a walk-forward test says otherwise.
#}

{% macro american_payout(p) -%}
    case when {{ p }} < 0 then 100.0 / -({{ p }}) else ({{ p }}) / 100.0 end
{%- endmacro %}

{% macro team_profiles(league) %}
with spine as (
    select * from {{ ref('int_' ~ league ~ '__game_spine') }}
    where home_spread is not null
    {% if league == 'nhl' %}
      and is_standard_puck_line and coalesce(line_consistent, true)
    {% endif %}
),

sides as (
    select
        season, home_team as team_code, true as is_home,
        home_spread < 0 as is_fav, home_spread > 0 as is_dog,
        home_ats_margin as ats_margin,
        case when line_source = 'historical_lines' then coalesce(home_spread_price, -110)
             else home_spread_price end                       as spread_price,
        total_margin,
        case when line_source = 'historical_lines' then coalesce(over_price, -110) else over_price end   as over_price,
        case when line_source = 'historical_lines' then coalesce(under_price, -110) else under_price end as under_price,
        home_margin                                           as team_margin,
        home_ml                                               as ml
    from spine
    union all
    select
        season, away_team, false,
        home_spread > 0, home_spread < 0,
        -home_ats_margin,
        case when line_source = 'historical_lines' then coalesce(away_spread_price, -110)
             else away_spread_price end,
        total_margin,
        case when line_source = 'historical_lines' then coalesce(over_price, -110) else over_price end,
        case when line_source = 'historical_lines' then coalesce(under_price, -110) else under_price end,
        -home_margin,
        away_ml
    from spine
),

settled as (
    select
        *,
        case when spread_price is null or ats_margin is null then null
             when ats_margin > 0 then {{ american_payout('spread_price') }}
             when ats_margin < 0 then -1.0 else 0.0 end        as ats_profit,
        case when over_price is null or total_margin is null then null
             when total_margin > 0 then {{ american_payout('over_price') }}
             when total_margin < 0 then -1.0 else 0.0 end      as over_profit,
        case when under_price is null or total_margin is null then null
             when total_margin < 0 then {{ american_payout('under_price') }}
             when total_margin > 0 then -1.0 else 0.0 end      as under_profit,
        case when ml is null or team_margin is null or team_margin = 0 then null
             when team_margin > 0 then {{ american_payout('ml') }} else -1.0 end as ml_profit
    from sides
),

targets as (
    select distinct season + 1 as profile_season from spine
),

windowed as (
    select t.profile_season, s.*
    from targets t
    join settled s
      on s.season between t.profile_season - 4 and t.profile_season - 1
),

n_prior as (
    select profile_season, count(distinct season) as n_prior
    from windowed
    group by 1
),

team_season as (
    select profile_season, team_code, season,
           sum(ats_profit) filter (where ats_margin <> 0)     as season_profit
    from windowed
    group by all
),

season_counts as (
    select profile_season, team_code,
           count(*)                                          as seasons_in_window,
           count(*) filter (where season_profit > 0)         as seasons_positive
    from team_season
    group by all
),

agg as (
    select
        profile_season,
        team_code,
        count(ats_profit) filter (where ats_margin <> 0)     as ats_games,
        count(*) filter (where ats_profit > 0)               as ats_wins,
        count(*) filter (where ats_profit = -1)              as ats_losses,
        count(*) filter (where ats_margin = 0 and ats_profit is not null) as ats_pushes,
        100.0 * count(*) filter (where ats_profit > 0)
          / nullif(count(ats_profit) filter (where ats_margin <> 0), 0)    as cover_pct,
        100.0 * sum(ats_profit) filter (where ats_margin <> 0)
          / nullif(count(ats_profit) filter (where ats_margin <> 0), 0)    as ats_roi,
        {% for name, cond in [('home', 'is_home'), ('away', 'not is_home'),
                              ('home_fav', 'is_home and is_fav'), ('home_dog', 'is_home and is_dog'),
                              ('away_fav', 'not is_home and is_fav'), ('away_dog', 'not is_home and is_dog')] -%}
        count(ats_profit) filter (where {{ cond }} and ats_margin <> 0)   as {{ name }}_games,
        100.0 * count(*) filter (where {{ cond }} and ats_profit > 0)
          / nullif(count(ats_profit) filter (where {{ cond }} and ats_margin <> 0), 0) as {{ name }}_cover_pct,
        100.0 * sum(ats_profit) filter (where {{ cond }} and ats_margin <> 0)
          / nullif(count(ats_profit) filter (where {{ cond }} and ats_margin <> 0), 0) as {{ name }}_roi,
        {% endfor -%}
        count(over_profit) filter (where total_margin <> 0)  as ou_games,
        100.0 * count(*) filter (where total_margin > 0 and over_profit is not null)
          / nullif(count(over_profit) filter (where total_margin <> 0), 0) as over_pct,
        100.0 * sum(over_profit) filter (where total_margin <> 0)
          / nullif(count(over_profit) filter (where total_margin <> 0), 0)  as over_roi,
        100.0 * sum(under_profit) filter (where total_margin <> 0)
          / nullif(count(under_profit) filter (where total_margin <> 0), 0) as under_roi,
        count(ml_profit)                                     as ml_games,
        100.0 * count(*) filter (where ml_profit > 0) / nullif(count(ml_profit), 0) as ml_win_pct,
        100.0 * avg(ml_profit)                               as ml_roi
    from windowed
    group by all
)

select
    a.profile_season                                         as season,
    a.team_code,
    a.profile_season - 4                                     as window_from_season,
    a.profile_season - 1                                     as window_to_season,
    n.n_prior,
    c.seasons_in_window,
    c.seasons_positive,
    a.* exclude (profile_season, team_code),
    case when a.over_pct >= 55 then 'OVER' when a.over_pct <= 45 then 'UNDER' else 'NONE' end as ou_lean,
    case
        when a.ats_games < 10 then 'NEUTRAL'
        when c.seasons_in_window < 2 then case when a.ats_roi <= -15 then 'FADE' else 'NEUTRAL' end
        when a.ats_roi >= 20 and c.seasons_positive >= greatest(2, floor(0.8 * n.n_prior)) then 'ELITE'
        when a.ats_roi >= 10 and c.seasons_positive >= greatest(2, floor(0.6 * n.n_prior)) then 'STRONG'
        when a.ats_roi <= -20 and c.seasons_positive <= floor(0.2 * n.n_prior) then 'STRONG_FADE'
        when a.ats_roi <= -10 then 'FADE'
        else 'NEUTRAL'
    end                                                      as tier
from agg a
join n_prior n using (profile_season)
join season_counts c using (profile_season, team_code)
{% endmacro %}
