-- mart_nba_game_features
--
-- One row per NBA game in int_nba__game_spine (2007-08 on) with pregame features
-- for both teams, computed only from games strictly before this one:
--   home_* / away_*  box-score ratings, pace and four factors over the previous
--                    5 / 10 games, season to date and the prior season
--                    (int_nba__team_box_features), and schedule / ATS form
--                    (int_nba__team_schedule);
--   gap_*            home minus away for every numeric feature;
--   ratings model    net rating blended with the prior season (prior weighted as
--                    10 games), converted to points at the two teams' blended pace,
--                    plus a home-court constant fitted ONLY on earlier seasons
--                    (mean of home_margin - rating_margin over all prior seasons,
--                    non-neutral games). implied_home_spread uses the market's sign
--                    (< 0 = home favoured); home_spread_edge = home_spread -
--                    implied_home_spread, > 0 means the ratings like home more than
--                    the market does. The first season (2007-08) has no constant.
-- The market line and the results are carried for backtests; results are labels,
-- never features. Games without a box score (the three NBA Cup finals) have null
-- box features but keep schedule features.

{%- set box_windows = ['l5', 'l10', 'std', 'prior'] -%}
{%- set box_feats = [] -%}
{%- for w in box_windows -%}{%- for m in nba_box_metric_names() -%}
    {%- do box_feats.append(m ~ '_' ~ w) -%}
{%- endfor -%}{%- endfor -%}
{%- set sched_feats = ['days_rest', 'is_b2b', 'is_3in4', 'games_last7', 'road_trip_game',
                       'travel_miles', 'ats_games_l10', 'ats_covers_l10', 'ats_losses_l10',
                       'ats_pushes_l10', 'ats_margin_avg_l10'] %}
{%- set bool_feats = ['is_b2b', 'is_3in4'] %}

with spine as (
    select * from {{ ref('int_nba__game_spine') }}
),

joined as (
    select
        s.game_key,
        s.espn_game_id,
        s.nba_game_id,
        s.season,
        s.season_type,
        s.game_date,
        s.home_team,
        s.away_team,
        coalesce(s.neutral_site, false)                          as neutral_site,

        -- market (chosen closing line; see int_nba__game_spine)
        s.line_source,
        s.home_spread,
        s.home_spread_price,
        s.away_spread_price,
        s.home_ml,
        s.away_ml,
        s.total,
        s.over_price,
        s.under_price,
        s.open_home_spread,
        s.open_home_spread_price,
        s.open_away_spread_price,
        s.open_total,
        s.open_over_price,
        s.open_under_price,

        -- results (labels only)
        s.home_score,
        s.away_score,
        s.home_margin,
        s.total_points,
        s.home_ats_margin,
        s.total_margin,
        s.went_ot,

        {% for f in box_feats -%}
        bh.{{ f }} as home_{{ f }},
        ba.{{ f }} as away_{{ f }},
        bh.{{ f }} - ba.{{ f }} as gap_{{ f }},
        {% endfor -%}
        {% for f in sched_feats -%}
        sh.{{ f }} as home_{{ f }},
        sa.{{ f }} as away_{{ f }},
        {% if f in bool_feats -%}
        sh.{{ f }}::int - sa.{{ f }}::int as gap_{{ f }}{{ "," if not loop.last }}
        {% else -%}
        sh.{{ f }} - sa.{{ f }} as gap_{{ f }}{{ "," if not loop.last }}
        {% endif -%}
        {% endfor %}
    from spine s
    left join {{ ref('int_nba__team_schedule') }} sh
      on sh.game_key = s.game_key and sh.team_code = s.home_team
    left join {{ ref('int_nba__team_schedule') }} sa
      on sa.game_key = s.game_key and sa.team_code = s.away_team
    left join {{ ref('int_nba__team_box_features') }} bh
      on bh.nba_game_id = s.nba_game_id and bh.team_code = s.home_team
    left join {{ ref('int_nba__team_box_features') }} ba
      on ba.nba_game_id = s.nba_game_id and ba.team_code = s.away_team
),

rated as (
    select
        *,
        {{ blend_with_prior('home_net_std', 'home_games_std', 'home_net_prior') }}   as home_net_blend,
        {{ blend_with_prior('away_net_std', 'away_games_std', 'away_net_prior') }}   as away_net_blend,
        {{ blend_with_prior('home_pace_std', 'home_games_std', 'home_pace_prior') }} as home_pace_blend,
        {{ blend_with_prior('away_pace_std', 'away_games_std', 'away_pace_prior') }} as away_pace_blend
    from joined
),

margin as (
    select
        *,
        (home_net_blend - away_net_blend)
          * (home_pace_blend + away_pace_blend) / 2 / 100        as rating_margin
    from rated
),

-- home-court constant: residual of the ratings margin, pooled over earlier seasons only
hca_season as (
    select season,
           sum(home_margin - rating_margin)                      as resid_sum,
           count(*)                                              as n
    from margin
    where not neutral_site and rating_margin is not null and home_margin is not null
    group by season
),

hca as (
    select season,
           sum(resid_sum) over w / sum(n) over w                 as home_court_pts
    from hca_season
    window w as (order by season rows between unbounded preceding and 1 preceding)
)

select
    m.*,
    h.home_court_pts,
    m.rating_margin + case when m.neutral_site then 0 else h.home_court_pts end      as implied_home_margin,
    -(m.rating_margin + case when m.neutral_site then 0 else h.home_court_pts end)   as implied_home_spread,
    m.home_spread
      + (m.rating_margin + case when m.neutral_site then 0 else h.home_court_pts end) as home_spread_edge
from margin m
left join hca h using (season)
