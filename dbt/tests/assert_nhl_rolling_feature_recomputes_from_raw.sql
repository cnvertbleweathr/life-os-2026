-- Recompute one rolling feature for 20 random NHL games straight from the raw
-- nhl.moneypuck_team_games table and compare with the mart: the home team's 5v5
-- xGF% over its previous 10 games of the season (home_xgf_pct_5v5_l10).
--
-- No window function: find the home team's raw MoneyPuck code in this game (via the
-- crosswalk seed, since MoneyPuck's own HOME flag is wrong for some Phoenix games),
-- take its 5on5 rows of the same season with an earlier game date, keep the 10 most
-- recent, and compute xGF / (xGF + xGA). Returns the games that disagree.

with sample as (
    select *
    from (
        select m.game_key, m.season, m.game_date, m.home_team, s.nhl_game_id, m.home_xgf_pct_5v5_l10
        from {{ ref('mart_nhl_game_features') }} m
        join {{ ref('int_nhl__game_spine') }} s using (game_key)
        where s.nhl_game_id is not null
    )
    using sample reservoir (20 rows) repeatable (20261109)
),

home_code as (
    select s.game_key, r.playerteam
    from sample s
    join {{ source('nhl', 'moneypuck_team_games') }} r
      on r.gameid = s.nhl_game_id and r.situation = '5on5'
    join {{ ref('nhl_team_crosswalk') }} x
      on {{ team_xwalk_join('x', 'moneypuck', 'r.playerteam', 'r.season_end') }}
    where x.team_code = s.home_team
),

previous as (
    select
        s.game_key,
        r.xgoalsfor,
        r.xgoalsagainst,
        row_number() over (partition by s.game_key order by r.gamedate desc) as recency
    from sample s
    join home_code h using (game_key)
    join {{ source('nhl', 'moneypuck_team_games') }} r
      on r.playerteam = h.playerteam
     and r.season_end = s.season
     and r.situation = '5on5'
     and cast(r.game_date as date) < s.game_date
),

recomputed as (
    select
        s.game_key,
        s.home_xgf_pct_5v5_l10                                       as mart_value,
        sum(p.xgoalsfor) / nullif(sum(p.xgoalsfor) + sum(p.xgoalsagainst), 0) as raw_value
    from sample s
    left join previous p
      on p.game_key = s.game_key and p.recency <= 10
    group by s.game_key, s.home_xgf_pct_5v5_l10
)

select *
from recomputed
where (mart_value is null) <> (raw_value is null)
   or abs(mart_value - raw_value) > 1e-6
