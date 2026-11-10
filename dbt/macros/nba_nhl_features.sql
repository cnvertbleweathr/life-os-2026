{#
  Helpers for the NBA / NHL pregame feature models.

  Every rolling feature is a ratio of SUMS over a window, not an average of
  per-game ratios, and every window ends at 1 PRECEDING: the game's own row is
  never inside its own features. Pass `over` as 'over w10' (a named window in the
  calling model) or '' for a plain aggregate (the prior-season rows).
#}

{% macro haversine_miles(lat1, lng1, lat2, lng2) -%}
    (3958.8 * 2 * asin(sqrt(
        power(sin(radians(({{ lat2 }}) - ({{ lat1 }})) / 2), 2)
        + cos(radians({{ lat1 }})) * cos(radians({{ lat2 }}))
          * power(sin(radians(({{ lng2 }}) - ({{ lng1 }})) / 2), 2))))
{%- endmacro %}


{# NBA box-score metric names, in output order (suffixed _l5 / _l10 / _std / _prior) #}
{% macro nba_box_metric_names() -%}
    {{ return(['games', 'ortg', 'drtg', 'net', 'pace',
               'efg', 'tov_pct', 'orb_pct', 'ft_rate',
               'opp_efg', 'opp_tov_pct', 'opp_orb_pct', 'opp_ft_rate']) }}
{%- endmacro %}

{#
  NBA box-score metrics from team-game sums (int_nba__team_box_features).
  poss = 0.5 * ((FGA - ORB + TOV + 0.44 FTA) + same for the opponent).
  Ratings per 100 possessions; pace per 48 minutes (240 team minutes).
  Four factors: eFG% = (FGM + 0.5 3PM) / FGA; TOV% = TOV / (FGA + 0.44 FTA + TOV);
  ORB% = ORB / (ORB + opp DRB); FT rate = FTM / FGA. opp_* are the same for the
  opponent (what the team allows).
#}
{% macro nba_box_metrics(over, sfx) -%}
    count(poss) {{ over }}                                                             as games_{{ sfx }},
    100 * sum(pts) {{ over }} / nullif(sum(poss) {{ over }}, 0)                        as ortg_{{ sfx }},
    100 * sum(opp_pts) {{ over }} / nullif(sum(poss) {{ over }}, 0)                    as drtg_{{ sfx }},
    100 * (sum(pts) {{ over }} - sum(opp_pts) {{ over }}) / nullif(sum(poss) {{ over }}, 0) as net_{{ sfx }},
    240 * sum(poss) {{ over }} / nullif(sum(team_minutes) {{ over }}, 0)               as pace_{{ sfx }},
    (sum(fgm) {{ over }} + 0.5 * sum(fg3m) {{ over }}) / nullif(sum(fga) {{ over }}, 0) as efg_{{ sfx }},
    sum(tov) {{ over }} / nullif(sum(fga) {{ over }} + 0.44 * sum(fta) {{ over }} + sum(tov) {{ over }}, 0) as tov_pct_{{ sfx }},
    sum(oreb) {{ over }} / nullif(sum(oreb) {{ over }} + sum(opp_dreb) {{ over }}, 0)   as orb_pct_{{ sfx }},
    sum(ftm) {{ over }} / nullif(sum(fga) {{ over }}, 0)                               as ft_rate_{{ sfx }},
    (sum(opp_fgm) {{ over }} + 0.5 * sum(opp_fg3m) {{ over }}) / nullif(sum(opp_fga) {{ over }}, 0) as opp_efg_{{ sfx }},
    sum(opp_tov) {{ over }} / nullif(sum(opp_fga) {{ over }} + 0.44 * sum(opp_fta) {{ over }} + sum(opp_tov) {{ over }}, 0) as opp_tov_pct_{{ sfx }},
    sum(opp_oreb) {{ over }} / nullif(sum(opp_oreb) {{ over }} + sum(dreb) {{ over }}, 0) as opp_orb_pct_{{ sfx }},
    sum(opp_ftm) {{ over }} / nullif(sum(opp_fga) {{ over }}, 0)                       as opp_ft_rate_{{ sfx }}
{%- endmacro %}


{# NHL team xG metric names (suffixed _l10 / _std / _prior) #}
{% macro nhl_xg_metric_names() -%}
    {{ return(['games', 'xgf_pct_5v5', 'corsi_pct_5v5', 'hd_share_5v5',
               'pp_xgf60', 'pk_xga60', 'finishing_per_game', 'xgf_pct_all']) }}
{%- endmacro %}

{#
  NHL team metrics from MoneyPuck team-game sums (int_nhl__team_xg_features).
  5v5: xGF% = xGF / (xGF + xGA); Corsi% = shot attempts for / (for + against);
  high-danger share = HD shots for / (for + against).
  PP xGF/60 from the 5on4 situation, PK xGA/60 from 4on5 (ice time in seconds).
  finishing_per_game = (goals - xG) per game, all situations (MoneyPuck goals
  exclude the shootout goal). xgf_pct_all = all-situations xGF%.
#}
{% macro nhl_xg_metrics(over, sfx) -%}
    count(xgf_all) {{ over }}                                                           as games_{{ sfx }},
    sum(xgf_5v5) {{ over }} / nullif(sum(xgf_5v5) {{ over }} + sum(xga_5v5) {{ over }}, 0) as xgf_pct_5v5_{{ sfx }},
    sum(cf_5v5) {{ over }} / nullif(sum(cf_5v5) {{ over }} + sum(ca_5v5) {{ over }}, 0)    as corsi_pct_5v5_{{ sfx }},
    sum(hdf_5v5) {{ over }} / nullif(sum(hdf_5v5) {{ over }} + sum(hda_5v5) {{ over }}, 0) as hd_share_5v5_{{ sfx }},
    3600 * sum(xgf_pp) {{ over }} / nullif(sum(toi_pp) {{ over }}, 0)                   as pp_xgf60_{{ sfx }},
    3600 * sum(xga_pk) {{ over }} / nullif(sum(toi_pk) {{ over }}, 0)                   as pk_xga60_{{ sfx }},
    (sum(gf_all) {{ over }} - sum(xgf_all) {{ over }}) / nullif(count(xgf_all) {{ over }}, 0) as finishing_per_game_{{ sfx }},
    sum(xgf_all) {{ over }} / nullif(sum(xgf_all) {{ over }} + sum(xga_all) {{ over }}, 0) as xgf_pct_all_{{ sfx }}
{%- endmacro %}


{#
  Blend a season-to-date value with the prior-season value, weighting the prior
  season as k games: (std * gp + prior * k) / (gp + k). Falls back to whichever
  side exists; null when neither does.
#}
{% macro blend_with_prior(std, games, prior, k=10) -%}
    case
        when {{ std }} is null and {{ prior }} is null then null
        when {{ prior }} is null then {{ std }}
        when {{ std }} is null then {{ prior }}
        else ({{ std }} * {{ games }} + {{ prior }} * {{ k }}) / ({{ games }} + {{ k }})
    end
{%- endmacro %}


{# American odds -> implied probability (with vig) #}
{% macro implied_prob(ml) -%}
    case when {{ ml }} < 0 then -({{ ml }}) / (-({{ ml }}) + 100.0)
         when {{ ml }} > 0 then 100.0 / ({{ ml }} + 100.0) end
{%- endmacro %}


{#
  team_schedule(league): one row per (game, team) from the game spine with the
  schedule features that need no box score: days rest, back-to-back, 3-in-4,
  games in the previous 7 days, road-trip game number, travel miles from the
  previous game's site, and ATS form over the last 10 games of the season.

  Site: the ESPN venue (nba_nhl_venues seed), which also covers neutral sites,
  the 2020 bubbles and outdoor games; else the home team's city
  (nba_nhl_team_cities seed), for pre-ESPN seasons and the 3 NHL games ESPN has
  no venue for. Rest and travel are null for a team's first game of a season.
  A neutral-site game is a road game for both teams.
#}
{% macro team_schedule(league) %}
with spine as (
    select s.*, g.venue
    from {{ ref('int_' ~ league ~ '__game_spine') }} s
    left join {{ ref('stg_' ~ league ~ '__games') }} g on g.game_id = s.espn_game_id
),

sited as (
    select
        s.*,
        coalesce(v.lat, c.lat)                                as site_lat,
        coalesce(v.lng, c.lng)                                as site_lng
    from spine s
    left join {{ ref('nba_nhl_venues') }} v on v.venue = s.venue
    left join {{ ref('nba_nhl_team_cities') }} c
      on c.league = '{{ league }}' and c.team_code = s.home_team
     and s.season between coalesce(c.valid_from_season, 0) and coalesce(c.valid_to_season, 9999)
),

team_games as (
    select game_key, season, season_type, game_date, site_lat, site_lng,
           home_team as team_code, away_team as opp_code, true as is_home,
           not coalesce(neutral_site, false) as at_home,
           home_spread as team_spread, home_ats_margin as ats_margin
    from sited
    union all
    select game_key, season, season_type, game_date, site_lat, site_lng,
           away_team, home_team, false,
           false,
           -home_spread, -home_ats_margin
    from sited
),

seq as (
    select
        *,
        lag(game_date) over w_team                            as prev_date,
        lag(season)    over w_team                            as prev_season,
        lag(site_lat)  over w_team                            as prev_lat,
        lag(site_lng)  over w_team                            as prev_lng,
        count(*) over (partition by team_code order by game_date
                       range between interval 7 days preceding and interval 1 day preceding) as games_last7,
        count(*) over (partition by team_code order by game_date
                       range between interval 3 days preceding and interval 1 day preceding) as games_prev3d,
        -- road trips: a new "island" starts at every home game
        sum(at_home::int) over (partition by team_code, season order by game_date, game_key
                                rows between unbounded preceding and current row) as home_island
    from team_games
    window w_team as (partition by team_code order by game_date, game_key)
)

select
    game_key,
    team_code,
    opp_code,
    season,
    is_home,
    at_home,
    case when prev_season = season then date_diff('day', prev_date, game_date) - 1 end as days_rest,
    coalesce(prev_season = season and date_diff('day', prev_date, game_date) = 1, false)  as is_b2b,
    games_prev3d >= 2                                         as is_3in4,
    games_last7,
    case when at_home then 0
         else count(*) filter (where not at_home) over (
                  partition by team_code, season, home_island order by game_date, game_key
                  rows between unbounded preceding and current row) end as road_trip_game,
    case when prev_season = season
         then {{ haversine_miles('prev_lat', 'prev_lng', 'site_lat', 'site_lng') }} end as travel_miles,
    count(ats_margin)                         over w10        as ats_games_l10,
    count(*) filter (where ats_margin > 0)    over w10        as ats_covers_l10,
    count(*) filter (where ats_margin < 0)    over w10        as ats_losses_l10,
    count(*) filter (where ats_margin = 0)    over w10        as ats_pushes_l10,
    avg(ats_margin)                           over w10        as ats_margin_avg_l10
from seq
window w10 as (partition by team_code, season order by game_date, game_key
               rows between 10 preceding and 1 preceding)
{% endmacro %}
