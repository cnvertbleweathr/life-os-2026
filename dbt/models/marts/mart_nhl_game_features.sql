-- mart_nhl_game_features
--
-- One row per NHL game in int_nhl__game_spine (2008-09 on) with pregame features
-- for both teams, computed only from games strictly before this one:
--   home_* / away_*  5v5 xGF%, Corsi%, high-danger share, PP xGF/60, PK xGA/60,
--                    finishing (goals - xG per game) and all-situations xGF% over the
--                    previous 10 games, season to date and the prior season
--                    (int_nhl__team_xg_features); rest, travel and puck-line form
--                    (int_nhl__team_schedule); the starting goalie's GSAx and save%
--                    over his previous 10 starts and this season (int_nhl__goalie_form,
--                    2019-20 on; the starter is the actual one, see that model);
--   gap_*            home minus away for every numeric feature;
--   xG model         all-situations xGF% blended with the prior season (prior
--                    weighted as 10 games), combined with log5, plus home ice as a
--                    log-odds constant fitted ONLY on earlier seasons
--                    (logit of the pooled home win rate, non-neutral, decided games).
--                    model_home_win_prob vs market_home_win_prob (the moneyline with
--                    the vig removed): home_prob_edge = model - market.
-- The market line and the results are carried for backtests; results are labels.

{%- set xg_feats = [] -%}
{%- for w in ['l10', 'std', 'prior'] -%}{%- for m in nhl_xg_metric_names() -%}
    {%- do xg_feats.append(m ~ '_' ~ w) -%}
{%- endfor -%}{%- endfor -%}
{%- set goalie_feats = ['starter_starts_l10', 'starter_gsax_l10', 'starter_sv_pct_l10',
                        'starter_starts_std', 'starter_gsax_std', 'starter_sv_pct_std'] -%}
{%- set sched_feats = ['days_rest', 'is_b2b', 'is_3in4', 'games_last7', 'road_trip_game',
                       'travel_miles', 'ats_games_l10', 'ats_covers_l10', 'ats_losses_l10',
                       'ats_pushes_l10', 'ats_margin_avg_l10'] %}
{%- set bool_feats = ['is_b2b', 'is_3in4'] %}

with spine as (
    select * from {{ ref('int_nhl__game_spine') }}
),

joined as (
    select
        s.game_key,
        s.espn_game_id,
        s.nhl_game_id,
        s.season,
        s.season_type,
        s.game_date,
        s.home_team,
        s.away_team,
        coalesce(s.neutral_site, false)                          as neutral_site,

        -- market (chosen closing line; see int_nhl__game_spine)
        s.line_source,
        s.home_spread,
        s.home_spread_price,
        s.away_spread_price,
        s.is_standard_puck_line,
        s.line_consistent,
        s.home_ml,
        s.away_ml,
        s.total,
        s.over_price,
        s.under_price,
        s.open_home_spread,
        s.open_home_ml,
        s.open_away_ml,

        -- results (labels only)
        s.home_score,
        s.away_score,
        s.home_margin,
        s.total_goals,
        s.home_ats_margin,
        s.total_margin,
        s.went_ot,
        s.shootout,

        gh.starter_id   as home_starter_id,
        gh.starter_name as home_starter_name,
        ga.starter_id   as away_starter_id,
        ga.starter_name as away_starter_name,

        {% for f in xg_feats -%}
        xh.{{ f }} as home_{{ f }},
        xa.{{ f }} as away_{{ f }},
        xh.{{ f }} - xa.{{ f }} as gap_{{ f }},
        {% endfor -%}
        {% for f in goalie_feats -%}
        gh.{{ f }} as home_{{ f }},
        ga.{{ f }} as away_{{ f }},
        gh.{{ f }} - ga.{{ f }} as gap_{{ f }},
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
    left join {{ ref('int_nhl__team_schedule') }} sh
      on sh.game_key = s.game_key and sh.team_code = s.home_team
    left join {{ ref('int_nhl__team_schedule') }} sa
      on sa.game_key = s.game_key and sa.team_code = s.away_team
    left join {{ ref('int_nhl__team_xg_features') }} xh
      on xh.nhl_game_id = s.nhl_game_id and xh.team_code = s.home_team
    left join {{ ref('int_nhl__team_xg_features') }} xa
      on xa.nhl_game_id = s.nhl_game_id and xa.team_code = s.away_team
    left join {{ ref('int_nhl__goalie_form') }} gh
      on gh.nhl_game_id = s.nhl_game_id and gh.team_code = s.home_team
    left join {{ ref('int_nhl__goalie_form') }} ga
      on ga.nhl_game_id = s.nhl_game_id and ga.team_code = s.away_team
),

rated as (
    select
        *,
        {{ blend_with_prior('home_xgf_pct_all_std', 'home_games_std', 'home_xgf_pct_all_prior') }} as home_xgf_pct_blend,
        {{ blend_with_prior('away_xgf_pct_all_std', 'away_games_std', 'away_xgf_pct_all_prior') }} as away_xgf_pct_blend
    from joined
),

log5 as (
    select
        *,
        home_xgf_pct_blend * (1 - away_xgf_pct_blend)
          / nullif(home_xgf_pct_blend * (1 - away_xgf_pct_blend)
                   + away_xgf_pct_blend * (1 - home_xgf_pct_blend), 0) as log5_home_prob
    from rated
),

-- home ice: pooled home win rate over earlier seasons only, as log-odds
hia_season as (
    select season,
           count(*) filter (where home_score > away_score)        as home_wins,
           count(*)                                               as n
    from joined
    where not neutral_site and home_score <> away_score
    group by season
),

hia as (
    select season,
           ln((sum(home_wins) over w) / (sum(n) over w - sum(home_wins) over w)) as home_ice_logit
    from hia_season
    window w as (order by season rows between unbounded preceding and 1 preceding)
),

model as (
    select
        l.*,
        h.home_ice_logit,
        1 / (1 + exp(-(ln(l.log5_home_prob / (1 - l.log5_home_prob))
                       + case when l.neutral_site then 0 else h.home_ice_logit end))) as model_home_win_prob,
        {{ implied_prob('l.home_ml') }}
          / nullif({{ implied_prob('l.home_ml') }} + {{ implied_prob('l.away_ml') }}, 0)   as market_home_win_prob
    from log5 l
    left join hia h using (season)
)

select
    *,
    model_home_win_prob - market_home_win_prob                   as home_prob_edge
from model
