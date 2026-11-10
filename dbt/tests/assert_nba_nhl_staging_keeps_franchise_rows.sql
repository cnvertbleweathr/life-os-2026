-- The crosswalk joins in staging are inner joins. This catches a key that is
-- missing from a seed (a new season, a renamed team): every stats row must
-- survive staging, and no ESPN game may have exactly one side mapped (games with
-- neither side mapped are exhibitions and are dropped on purpose).
-- Fix a failure by rerunning scripts/nba_nhl_build_crosswalks.py.

select * from (
select 'nba.team_game_logs' as source_table,
       (select count(*) from {{ source('nba', 'team_game_logs') }}) as raw_rows,
       (select count(*) from {{ ref('stg_nba__team_game_logs') }}) as staged_rows
union all
select 'nba.historical_lines',
       (select count(*) from {{ source('nba', 'historical_lines') }}),
       (select count(*) from {{ ref('stg_nba__historical_lines') }})
union all
select 'nhl.moneypuck_team_games',
       (select count(*) from {{ source('nhl', 'moneypuck_team_games') }}),
       (select count(*) from {{ ref('stg_nhl__moneypuck_team_games') }})
union all
select 'nhl.goalie_games',
       (select count(*) from {{ source('nhl', 'goalie_games') }}),
       (select count(*) from {{ ref('stg_nhl__goalie_games') }})
union all
select 'nba.games half-mapped',
       (select count(*) from {{ source('nba', 'games') }} g
        where (select count(*) from {{ ref('nba_team_crosswalk') }} x
               where {{ team_xwalk_join('x', 'espn_id', 'g.home_id', 'g.season') }})
            + (select count(*) from {{ ref('nba_team_crosswalk') }} x
               where {{ team_xwalk_join('x', 'espn_id', 'g.away_id', 'g.season') }}) = 1),
       0
union all
select 'nhl.games half-mapped',
       (select count(*) from {{ source('nhl', 'games') }} g
        where (select count(*) from {{ ref('nhl_team_crosswalk') }} x
               where {{ team_xwalk_join('x', 'espn_id', 'g.home_id', 'g.season') }})
            + (select count(*) from {{ ref('nhl_team_crosswalk') }} x
               where {{ team_xwalk_join('x', 'espn_id', 'g.away_id', 'g.season') }}) = 1),
       0
)
where raw_rows <> staged_rows
