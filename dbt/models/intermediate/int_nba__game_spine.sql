-- Intermediate: NBA game spine. One row per completed regular-season or playoff
-- game between two franchises, 2007-08 on.
--
-- Games: ESPN (stg_nba__games) for every season ESPN is loaded (2013-14 on),
-- nba_api box scores (stg_nba__team_game_logs) before that. game_source says which.
--
-- Stats key: nba_game_id (+ home / away nba_team_id) into stg_nba__team_game_logs.
-- An ESPN game matches the nba_api game with the same two teams on the same
-- Eastern date, else within one day (a late West-coast tip is past midnight
-- Eastern, while stats.nba.com keeps the local date). The pair is unordered:
-- nba_api lists both teams as away at neutral sites (NBA Cup knockouts, Paris,
-- Mexico City), so ESPN's home designation is kept. The NBA Cup final isn't in
-- LeagueGameLog's regular season, so it has no nba_game_id.
--
-- Line: the chosen ESPN line (stg_nba__odds, rule documented in macros/espn_odds.sql)
-- when the game has one, else the SBR closing line from stg_nba__historical_lines.
-- All line fields come from one source; line_source names it
-- ('espn:<book>:<close|final>' or 'historical_lines'). historical_lines has no
-- prices: price those at -110.
--
-- home_spread < 0 when home is favoured. home_ats_margin = home_margin + home_spread:
-- > 0 home covered, 0 push. total_margin = total_points - total: > 0 over.

with espn_games as (
    select * from {{ ref('stg_nba__games') }}
    where completed and season_type in (2, 3)
),

espn_start as (
    select min(season) as season from {{ ref('stg_nba__games') }}
),

logs as (
    select
        nba_game_id,
        any_value(season)                                     as season,
        any_value(season_type)                                as season_type,
        any_value(game_date)                                  as game_date,
        min(team_code)                                        as team_a,
        max(team_code)                                        as team_b,
        max(team_code)   filter (where is_home)               as home_team,
        max(team_code)   filter (where not is_home)           as away_team,
        max(nba_team_id) filter (where is_home)               as home_nba_team_id,
        max(nba_team_id) filter (where not is_home)           as away_nba_team_id,
        max(pts)         filter (where is_home)               as home_pts,
        max(pts)         filter (where not is_home)           as away_pts,
        max(minutes)                                          as team_minutes
    from {{ ref('stg_nba__team_game_logs') }}
    group by 1
),

team_ids as (
    select distinct nba_game_id, team_code, nba_team_id
    from {{ ref('stg_nba__team_game_logs') }}
),

espn_match as (
    select
        e.game_id,
        l.nba_game_id,
        date_diff('day', e.game_date, l.game_date)            as stats_date_offset
    from espn_games e
    join logs l
      on l.team_a = least(e.home_team, e.away_team)
     and l.team_b = greatest(e.home_team, e.away_team)
     and l.game_date between e.game_date - 1 and e.game_date + 1
    qualify row_number() over (
        partition by e.game_id
        order by abs(date_diff('day', e.game_date, l.game_date)),
                 l.home_team is not distinct from e.home_team desc
    ) = 1
),

games as (
    select
        'espn:' || e.game_id                                  as game_key,
        'espn'                                                as game_source,
        e.game_id                                             as espn_game_id,
        m.nba_game_id,
        th.nba_team_id                                        as home_nba_team_id,
        ta.nba_team_id                                        as away_nba_team_id,
        m.stats_date_offset,
        e.season,
        e.season_type,
        e.game_date,
        e.home_team,
        e.away_team,
        e.home_score,
        e.away_score,
        e.went_ot,
        -- neutral when ESPN says so, or when the venue is > 50 miles from the home
        -- team's city (the 2020 bubbles, relocated games); ESPN flags neither
        coalesce(e.neutral_site, false)
          or coalesce({{ haversine_miles('v.lat', 'v.lng', 'c.lat', 'c.lng') }} > 50, false) as neutral_site,
        coalesce(e.neutral_site, false)                       as espn_neutral_site
    from espn_games e
    left join espn_match m using (game_id)
    left join {{ ref('nba_nhl_venues') }} v on v.venue = e.venue
    left join {{ ref('nba_nhl_team_cities') }} c
      on c.league = 'nba' and c.team_code = e.home_team
     and e.season between coalesce(c.valid_from_season, 0) and coalesce(c.valid_to_season, 9999)
    left join team_ids th on th.nba_game_id = m.nba_game_id and th.team_code = e.home_team
    left join team_ids ta on ta.nba_game_id = m.nba_game_id and ta.team_code = e.away_team

    union all

    select
        'nba:' || l.nba_game_id,
        'nba_api',
        null,
        l.nba_game_id,
        l.home_nba_team_id,
        l.away_nba_team_id,
        0,
        l.season,
        l.season_type,
        l.game_date,
        l.home_team,
        l.away_team,
        l.home_pts,
        l.away_pts,
        l.team_minutes > 240,
        null,
        null
    from logs l
    where l.season < (select season from espn_start)
),

lines as (
    select
        g.game_key,
        o.game_id is not null                                 as has_espn_line,
        o.*,
        h.home_spread                                         as hl_home_spread,
        h.home_ml                                             as hl_home_ml,
        h.away_ml                                             as hl_away_ml,
        h.total                                               as hl_total
    from games g
    left join {{ ref('stg_nba__odds') }} o
      on o.game_id = g.espn_game_id
    left join {{ ref('stg_nba__historical_lines') }} h
      on h.game_date = g.game_date
     and h.home_team = g.home_team
     and h.away_team = g.away_team
)

select
    g.*,
    g.home_score - g.away_score                               as home_margin,
    g.home_score + g.away_score                               as total_points,

    case when l.has_espn_line then l.line_source
         when l.hl_home_spread is not null then 'historical_lines' end   as line_source,
    case when l.has_espn_line then l.line_snapshot
         when l.hl_home_spread is not null then 'final' end              as line_snapshot,
    case when l.has_espn_line then l.book end                            as line_book,
    case when l.has_espn_line then l.home_spread else l.hl_home_spread end as home_spread,
    case when l.has_espn_line then l.home_spread_price end               as home_spread_price,
    case when l.has_espn_line then l.away_spread_price end               as away_spread_price,
    case when l.has_espn_line then l.ml_book end                         as ml_book,
    case when l.has_espn_line then l.home_ml else l.hl_home_ml end       as home_ml,
    case when l.has_espn_line then l.away_ml else l.hl_away_ml end       as away_ml,
    case when l.has_espn_line then l.total_book end                      as total_book,
    case when l.has_espn_line then l.total else l.hl_total end           as total,
    case when l.has_espn_line then l.over_price end                      as over_price,
    case when l.has_espn_line then l.under_price end                     as under_price,
    l.open_home_spread,
    l.open_home_spread_price,
    l.open_away_spread_price,
    l.open_total,
    l.open_over_price,
    l.open_under_price,
    l.open_home_ml,
    l.open_away_ml,
    l.spread_agrees_with_market,
    l.n_books,

    g.home_score - g.away_score
      + case when l.has_espn_line then l.home_spread else l.hl_home_spread end as home_ats_margin,
    g.home_score + g.away_score
      - case when l.has_espn_line then l.total else l.hl_total end             as total_margin
from games g
join lines l using (game_key)
