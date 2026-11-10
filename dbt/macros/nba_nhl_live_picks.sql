{#
  nba_nhl_live_picks(league): season summary of {league}.live_picks (loaded by
  pipelines/nba_nhl_live_picks_pipeline.py from data/bets/{league}/history/*.json).

  One row per season: games logged, games graded, bets and their record / ROI
  (none until a rule is validated), and the NBA paper forward test's entries,
  record, ROI at the captured price, and CLV (points toward the bet; beat-close %).
  Pushes count as entries but not in win% or ROI, as in mart_live_picks (CFB).
  Falls back to an empty, typed result until the first load creates the table.
#}
{% macro nba_nhl_live_picks(league) %}
{% set src = relation_if_exists(league, 'live_picks') %}
{% if src is not none %}
with picks as (
    select * from {{ src }}
)

select
    season,
    count(*)                                                        as games_logged,
    count(graded_at)                                                as games_graded,
    count(*) filter (where captured_after_start)                    as captured_after_start,
    count(*) filter (where verdict <> 'NO_BET')                     as bets,
    count(*) filter (where coalesce(paper_fires, false))            as paper_entries,
    count(paper_outcome)                                            as paper_graded,
    count(*) filter (where paper_outcome = 'win')                   as paper_wins,
    count(*) filter (where paper_outcome = 'loss')                  as paper_losses,
    count(*) filter (where paper_outcome = 'push')                  as paper_pushes,
    100.0 * count(*) filter (where paper_outcome = 'win')
      / nullif(count(*) filter (where paper_outcome in ('win', 'loss')), 0) as paper_win_pct,
    100.0 * sum(paper_pnl) filter (where paper_outcome in ('win', 'loss'))
      / nullif(count(*) filter (where paper_outcome in ('win', 'loss')), 0) as paper_roi,
    avg(paper_clv)                                                  as paper_clv_avg,
    100.0 * count(*) filter (where paper_clv > 0) / nullif(count(paper_clv), 0) as paper_beat_close_pct,
    min(game_date)                                                  as first_game_date,
    max(game_date)                                                  as last_game_date
from picks
group by season
{% else %}
select
    cast(null as bigint) as season, cast(null as bigint) as games_logged, cast(null as bigint) as games_graded,
    cast(null as bigint) as captured_after_start, cast(null as bigint) as bets,
    cast(null as bigint) as paper_entries, cast(null as bigint) as paper_graded,
    cast(null as bigint) as paper_wins, cast(null as bigint) as paper_losses, cast(null as bigint) as paper_pushes,
    cast(null as double) as paper_win_pct, cast(null as double) as paper_roi,
    cast(null as double) as paper_clv_avg, cast(null as double) as paper_beat_close_pct,
    cast(null as varchar) as first_game_date, cast(null as varchar) as last_game_date
where false
{% endif %}
{% endmacro %}
