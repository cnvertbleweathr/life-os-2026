-- mart_cfb_preseason_quality_v2.sql
--
-- Reweighted variant of mart_cfb_preseason_quality for Phase A Stage 1
-- parameter selection experiment. Efficiency block gets 50% weight instead
-- of equal 1/3, since talent/program and prior_results are more correlated
-- with efficiency and may be diluting the signal rather than adding to it.
-- Run validate_predictor() against both versions to see which produces
-- better Stage 1 results before locking a configuration.
--
-- efficiency 50%, talent_program 25%, prior_results 25%

with seasons as (
    -- Every (team, season) we could compute a preseason score FOR.
    -- season here is the TARGET season; all stats below are pulled from
    -- season - 1.
    select distinct team, season + 1 as season
    from cfbd.advanced_stats
),

efficiency_raw as (
    select
        team,
        season + 1 as season,   -- this row's stats describe the PRIOR season relative to the target
        off_ppa,
        off_success_rate,
        off_explosiveness,
        -def_ppa            as def_ppa_reversed,           -- sign-reversed, confirmed required
        -def_success_rate   as def_success_rate_reversed,  -- sign-reversed, confirmed required
        def_havoc_total                                     -- NOT reversed, higher havoc is better
    from cfbd.advanced_stats
),

talent_raw as (
    select
        r.team,
        r.year + 1 as season,
        r.points as recruiting_points
    from cfbd.recruiting_rankings r
),

draft_raw as (
    -- Aggregated from per-pick rows to team-season, same pattern as
    -- mart_cfbd_game_context.sql's existing draft CTE.
    select
        college_team as team,
        year + 1 as season,
        count(*) as draft_picks,
        sum(case when round = 1 then 1 else 0 end) as first_round_picks
    from cfbd.draft_production
    group by college_team, year
),

prior_results_raw as (
    select
        school as team,
        year + 1 as season,
        max(wins)    as wins,
        max(losses)  as losses,
        max(srs)     as srs
    from cfbd.coaches
    group by school, year
),

-- ── Rank-based percentile, p = (rank - 0.5) / n, per team per season ────

efficiency_ranked as (
    select
        team, season,
        (row_number() over (partition by season order by off_ppa) - 0.5)
            / count(*) over (partition by season) as off_ppa_pctile,
        (row_number() over (partition by season order by off_success_rate) - 0.5)
            / count(*) over (partition by season) as off_sr_pctile,
        (row_number() over (partition by season order by off_explosiveness) - 0.5)
            / count(*) over (partition by season) as off_exp_pctile,
        (row_number() over (partition by season order by def_ppa_reversed) - 0.5)
            / count(*) over (partition by season) as def_ppa_pctile,
        (row_number() over (partition by season order by def_success_rate_reversed) - 0.5)
            / count(*) over (partition by season) as def_sr_pctile,
        (row_number() over (partition by season order by def_havoc_total) - 0.5)
            / count(*) over (partition by season) as def_havoc_pctile,
    from efficiency_raw
),

talent_ranked as (
    select
        team, season,
        (row_number() over (partition by season order by recruiting_points) - 0.5)
            / count(*) over (partition by season) as recruiting_pctile,
    from talent_raw
),

draft_ranked as (
    select
        team, season,
        (row_number() over (partition by season order by draft_picks) - 0.5)
            / count(*) over (partition by season) as draft_picks_pctile,
    from draft_raw
),

prior_results_ranked as (
    select
        team, season,
        (row_number() over (partition by season order by
            cast(wins as double) / nullif(wins + losses, 0)) - 0.5)
            / count(*) over (partition by season) as win_pct_pctile,
        -- srs replaces postseason_rank (2026-06-30): postseason_rank is
        -- null for virtually every team in CFBD's bulk /coaches endpoint
        -- -- confirmed via direct API tracing, the field is simply not
        -- reliably populated at source. SRS (Simple Rating System) is
        -- a better signal anyway: it's continuous, opponent-adjusted, and
        -- directly measures how well the team performed that season,
        -- rather than reflecting AP poll media consensus.
        (row_number() over (partition by season order by srs) - 0.5)
            / count(*) over (partition by season) as srs_pctile,
    from prior_results_raw
),

-- ── Block averages, converted to z-units via the verified macro ────────

efficiency_block as (
    select
        team, season,
        (
            ({{ inv_normal_cdf('off_ppa_pctile') }})
          + ({{ inv_normal_cdf('off_sr_pctile') }})
          + ({{ inv_normal_cdf('off_exp_pctile') }})
        ) / 3.0 as efficiency_off_z,
        (
            ({{ inv_normal_cdf('def_ppa_pctile') }})
          + ({{ inv_normal_cdf('def_sr_pctile') }})
          + ({{ inv_normal_cdf('def_havoc_pctile') }})
        ) / 3.0 as efficiency_def_z,
    from efficiency_ranked
),

talent_program_block as (
    select
        t.team, t.season,
        case when d.draft_picks_pctile is not null then
            (({{ inv_normal_cdf('t.recruiting_pctile') }}) + ({{ inv_normal_cdf('d.draft_picks_pctile') }})) / 2.0
        else
            {{ inv_normal_cdf('t.recruiting_pctile') }}
        end as talent_program_z,
    from talent_ranked t
    left join draft_ranked d using (team, season)
),

prior_results_block as (
    select
        team, season,
        (({{ inv_normal_cdf('win_pct_pctile') }}) + ({{ inv_normal_cdf('srs_pctile') }})) / 2.0
            as prior_results_z,
    from prior_results_ranked
),

-- ── Combine blocks: equal weight, 1/3 each, locked v1 baseline ──────────
-- Talent/program and prior_results are program-level, not
-- offense/defense-specific, so they're shared across both composite
-- scores -- per design v5. Missing blocks are excluded from the average
-- (not treated as zero), with the divisor adjusted accordingly.

combined as (
    select
        s.team,
        s.season,
        eff.efficiency_off_z,
        eff.efficiency_def_z,
        tal.talent_program_z,
        pr.prior_results_z,
        -- Offense: efficiency 50% + talent 25% + prior_results 25%
        (coalesce(eff.efficiency_off_z, 0) * 0.5
       + coalesce(tal.talent_program_z, 0) * 0.25
       + coalesce(pr.prior_results_z, 0) * 0.25)
            / nullif(
                (case when eff.efficiency_off_z is not null then 0.5 else 0 end)
              + (case when tal.talent_program_z is not null then 0.25 else 0 end)
              + (case when pr.prior_results_z   is not null then 0.25 else 0 end), 0
            ) as preseason_off_rating_z,
        (coalesce(eff.efficiency_def_z, 0) * 0.5
       + coalesce(tal.talent_program_z, 0) * 0.25
       + coalesce(pr.prior_results_z, 0) * 0.25)
            / nullif(
                (case when eff.efficiency_def_z is not null then 0.5 else 0 end)
              + (case when tal.talent_program_z is not null then 0.25 else 0 end)
              + (case when pr.prior_results_z   is not null then 0.25 else 0 end), 0
            ) as preseason_def_rating_z,
    from seasons s
    left join efficiency_block      eff using (team, season)
    left join talent_program_block  tal using (team, season)
    left join prior_results_block   pr  using (team, season)
)

select
    team,
    season,
    round(preseason_off_rating_z, 4) as preseason_off_rating_z,
    round(preseason_def_rating_z, 4) as preseason_def_rating_z,
    -- Display-only percentile fields, NEVER fed back into modeling.
    round(percent_rank() over (partition by season order by preseason_off_rating_z) * 100, 1)
        as preseason_off_percentile,
    round(percent_rank() over (partition by season order by preseason_def_rating_z) * 100, 1)
        as preseason_def_percentile,
    -- Uncertainty placeholder: count of missing input blocks. The
    -- continuity block (coach change, returning production) is a
    -- separate, not-yet-built step per design v5 -- this is the
    -- simplest honest signal available until that's wired in.
    (case when efficiency_off_z   is null then 1 else 0 end
   + case when talent_program_z   is null then 1 else 0 end
   + case when prior_results_z    is null then 1 else 0 end) as missing_input_blocks,
from combined
order by season, team
