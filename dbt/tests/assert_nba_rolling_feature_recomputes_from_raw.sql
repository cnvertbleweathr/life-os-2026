-- Recompute one rolling feature for 20 random NBA games straight from the raw
-- nba.team_game_logs table and compare with the mart: the home team's offensive
-- rating over its previous 10 games of the season (home_ortg_l10).
--
-- The recomputation uses no window function: it takes the raw rows of the same
-- nba_api team_id and season with a game date strictly before the game, keeps the
-- 10 most recent, and computes 100 * points / possessions. A lookahead (the game
-- itself, or a later game, inside the window) would show up as a mismatch.
-- Returns the games that disagree.

with sample as (
    select *
    from (
        select m.game_key, m.season, m.game_date, s.home_nba_team_id, m.home_ortg_l10
        from {{ ref('mart_nba_game_features') }} m
        join {{ ref('int_nba__game_spine') }} s using (game_key)
        where s.home_nba_team_id is not null
    )
    using sample reservoir (20 rows) repeatable (20261109)
),

raw as (
    select
        t.team_id,
        t.season,
        cast(t.game_date as date)                                    as game_date,
        t.pts,
        0.5 * ((t.fga - t.oreb + t.tov + 0.44 * t.fta)
             + (o.fga - o.oreb + o.tov + 0.44 * o.fta))              as poss
    from {{ source('nba', 'team_game_logs') }} t
    join {{ source('nba', 'team_game_logs') }} o
      on o.game_id = t.game_id and o.team_id <> t.team_id
),

previous as (
    select
        s.game_key,
        r.pts,
        r.poss,
        row_number() over (partition by s.game_key order by r.game_date desc) as recency
    from sample s
    join raw r
      on r.team_id = s.home_nba_team_id
     and r.season = s.season
     and r.game_date < s.game_date
),

recomputed as (
    select
        s.game_key,
        s.home_ortg_l10                                              as mart_value,
        100 * sum(p.pts) / nullif(sum(p.poss), 0)                    as raw_value
    from sample s
    left join previous p
      on p.game_key = s.game_key and p.recency <= 10
    group by s.game_key, s.home_ortg_l10
)

select *
from recomputed
where (mart_value is null) <> (raw_value is null)
   or abs(mart_value - raw_value) > 1e-6
