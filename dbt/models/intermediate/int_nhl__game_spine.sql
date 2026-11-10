-- Intermediate: NHL game spine. One row per completed regular-season or playoff
-- game between two franchises, 2008-09 on.
--
-- Games: ESPN (stg_nhl__games) for every season ESPN is loaded (2019-20 on),
-- MoneyPuck (stg_nhl__moneypuck_team_games, situation 'all') before that.
-- game_source says which. ESPN's score counts a shootout win as one goal;
-- MoneyPuck leaves the shootout goal out, so a pre-ESPN shootout game shows a
-- tie with shootout = true and no winner.
--
-- Stats key: nhl_game_id (the NHL game id) into stg_nhl__moneypuck_team_games and
-- stg_nhl__goalie_games. An ESPN game matches the MoneyPuck game with the same two
-- teams on the same Eastern date, else within one day; ESPN's home side is kept.
--
-- Line: the chosen ESPN line (stg_nhl__odds, rule documented in macros/espn_odds.sql);
-- NHL has no lines before 2019-20. home_spread is the puck line, < 0 when home is
-- favoured; 18 ESPN BET-only games in 2024-25 carry only a +-2.5 alternate
-- (is_standard_puck_line = false; filter them in backtests). line_source = 'espn:<book>:<close|final>'.
-- home_ats_margin = home_margin + home_spread: > 0 home covered.
-- A game won in OT or a shootout is a one-goal game: the -1.5 side always loses it.

with espn_games as (
    select * from {{ ref('stg_nhl__games') }}
    where completed and season_type in (2, 3)
),

espn_start as (
    select min(season) as season from {{ ref('stg_nhl__games') }}
),

mp as (
    select
        nhl_game_id,
        any_value(season)                                     as season,
        any_value(season_type)                                as season_type,
        any_value(game_date)                                  as game_date,
        min(team_code)                                        as team_a,
        max(team_code)                                        as team_b,
        max(team_code) filter (where is_home)                 as home_team,
        max(team_code) filter (where not is_home)             as away_team,
        cast(max(goalsfor) filter (where is_home) as integer)     as home_goals,
        cast(max(goalsfor) filter (where not is_home) as integer) as away_goals,
        max(icetime)                                          as icetime
    from {{ ref('stg_nhl__moneypuck_team_games') }}
    where situation = 'all'
    group by 1
),

espn_match as (
    select
        e.game_id,
        m.nhl_game_id,
        date_diff('day', e.game_date, m.game_date)            as stats_date_offset
    from espn_games e
    join mp m
      on m.team_a = least(e.home_team, e.away_team)
     and m.team_b = greatest(e.home_team, e.away_team)
     and m.game_date between e.game_date - 1 and e.game_date + 1
    qualify row_number() over (
        partition by e.game_id
        order by abs(date_diff('day', e.game_date, m.game_date)),
                 m.home_team is not distinct from e.home_team desc
    ) = 1
),

games as (
    select
        'espn:' || e.game_id                                  as game_key,
        'espn'                                                as game_source,
        e.game_id                                             as espn_game_id,
        m.nhl_game_id,
        m.stats_date_offset,
        e.season,
        e.season_type,
        e.game_date,
        e.home_team,
        e.away_team,
        e.home_score,
        e.away_score,
        e.went_ot,
        e.shootout,
        -- neutral when ESPN says so, when the game is in the 2020 restart bubbles
        -- (every game from July 2020: Orlando, Edmonton, Toronto, no crowds, including
        -- the Magic's and Oilers' own "home" games), or when the venue is > 50 miles
        -- from the home team's city (relocated games); ESPN flags none of these
        coalesce(e.neutral_site, false)
          or (e.season = 2020 and e.game_date >= date '2020-07-01')
          or coalesce({{ haversine_miles('v.lat', 'v.lng', 'c.lat', 'c.lng') }} > 50, false) as neutral_site,
        coalesce(e.neutral_site, false)                       as espn_neutral_site
    from espn_games e
    left join espn_match m using (game_id)
    left join {{ ref('nba_nhl_venues') }} v on v.venue = e.venue
    left join {{ ref('nba_nhl_team_cities') }} c
      on c.league = 'nhl' and c.team_code = e.home_team
     and e.season between coalesce(c.valid_from_season, 0) and coalesce(c.valid_to_season, 9999)

    union all

    select
        'nhl:' || m.nhl_game_id,
        'moneypuck',
        null,
        m.nhl_game_id,
        0,
        m.season,
        m.season_type,
        m.game_date,
        m.home_team,
        m.away_team,
        m.home_goals,
        m.away_goals,
        m.icetime > 3600,
        m.season_type = 2 and m.home_goals = m.away_goals,
        null,
        null
    from mp m
    where m.season < (select season from espn_start)
)

select
    g.*,
    g.home_score - g.away_score                               as home_margin,
    g.home_score + g.away_score                               as total_goals,

    o.line_source,
    o.line_snapshot,
    o.book                                                    as line_book,
    o.home_spread,
    o.home_spread_price,
    o.away_spread_price,
    abs(o.home_spread) = 1.5                                  as is_standard_puck_line,
    o.ml_book,
    o.home_ml,
    o.away_ml,
    o.total_book,
    o.total,
    o.over_price,
    o.under_price,
    o.open_home_spread,
    o.open_home_spread_price,
    o.open_away_spread_price,
    o.open_total,
    o.open_over_price,
    o.open_under_price,
    o.open_home_ml,
    o.open_away_ml,
    o.line_consistent,
    o.spread_agrees_with_market,
    o.n_books,

    g.home_score - g.away_score + o.home_spread               as home_ats_margin,
    g.home_score + g.away_score - o.total                     as total_margin
from games g
left join {{ ref('stg_nhl__odds') }} o
  on o.game_id = g.espn_game_id
