{#
  espn_odds(league)

  One chosen line per game for stg_nba__odds / stg_nhl__odds. The rule:

  1. Books only. Projection sites, consensus, the "Opening" feed and the live
     in-game feeds are is_book = false in the nba_nhl_odds_providers seed and are
     never chosen. Providers are keyed on (league, provider_id): ESPN reuses ids
     across leagues for different providers.

  2. Snapshot: the close snapshot when the book has one for that market
     (2023-24 on), else the item-level number, which before 2023-24 is the final
     pregame line (= current). Prices always come from the same snapshot as
     their line.

  3. Spread (the bet; line_source describes it). Among the game's book rows with
     a spread, in order:
       a. spread agrees with the book's own moneyline favourite (about 2% of NHL
          rows put -1.5 on the ML underdog);
       b. spread within tolerance of the median spread of all books on the game
          (NBA 3 points, NHL 1 goal; only checked when >= 3 books quote it), which
          drops one-book errors and placeholders such as 0 / -110 / -110;
       c. NHL only: the standard +-1.5 puck line before alternates (ESPN BET is
          the only 2024-25 book and sometimes posts -2.5);
       d. lowest seed priority: DraftKings, ESPN BET, MGM, Caesars NJ ... and,
          for 2013-14 to 2016-17, 5Dimes, Pinnacle, BetOnline, Bovada ...
          The books that disagree with the market most often (Caesars Sportsbook
          id 31, Unibet, SugarHouse: ~4% of NBA games off by > 3 points) sit last.

  4. Moneyline: from the spread's book when it quotes a valid 2-way pair, else the
     highest-priority book that does. ml_book records it. A pair is valid when its
     implied probabilities sum to 1.00-1.12: most NHL books before 2024-25 carry
     3-way regulation prices in the moneyline field (both legs often plus money),
     which are dropped.

  5. Total: the highest-priority book whose total is within tolerance of the
     median total (NBA 6 points, NHL 1 goal), preferring the spread's book.
     Picked separately because some books, DraftKings NHL in particular (71%),
     often quote no total. total_book records it.

  line_source = 'espn:<book>:<close|final>' for the spread.
  open_* come from the spread's book (initialSpread fills the open for 2013-14 to
  ~2017-18; real open snapshots from 2023-24).
#}
{% macro espn_odds(league) %}
{%- set spread_tol = 3.0 if league == 'nba' else 1.0 -%}
{%- set total_tol = 6.0 if league == 'nba' else 1.0 -%}
with books as (
    select
        o.game_id,
        cast(o.season as integer)                             as season,
        o.provider_id,
        p.provider_name                                       as book,
        p.priority,
        o.close_home_spread is not null                       as spread_is_close,
        coalesce(o.close_home_spread, o.home_spread)          as home_spread,
        case when o.close_home_spread is not null then o.close_home_spread_price else o.home_spread_price end as home_spread_price,
        case when o.close_home_spread is not null then o.close_away_spread_price else o.away_spread_price end as away_spread_price,
        o.close_home_ml is not null                           as ml_is_close,
        case when o.close_home_ml is not null then o.close_home_ml else o.home_ml end as home_ml,
        case when o.close_home_ml is not null then o.close_away_ml else o.away_ml end as away_ml,
        o.close_total is not null                             as total_is_close,
        coalesce(o.close_total, o.total)                      as total,
        case when o.close_total is not null then o.close_over_price  else o.over_price  end as over_price,
        case when o.close_total is not null then o.close_under_price else o.under_price end as under_price,
        o.open_home_spread,
        o.open_home_spread_price,
        o.open_away_spread_price,
        o.open_home_ml,
        o.open_away_ml,
        o.open_total
    from {{ source(league, 'odds') }} o
    join {{ ref('nba_nhl_odds_providers') }} p
      on p.league = '{{ league }}' and p.provider_id = o.provider_id and p.is_book
),

-- A moneyline is kept only when its two sides form a 2-way market: implied
-- probabilities summing to 1.00-1.12. Most NHL books before 2024-25 put the 3-way
-- (regulation-time) price in ESPN's moneyLine field, home and away legs without the
-- draw (MIN +120 / away +175), which sums to ~0.85 and would settle wrongly as a
-- 2-way bet. Same check for the opening pair.
priced as (
    select
        * replace (
            case when {{ implied_prob('home_ml') }} + {{ implied_prob('away_ml') }} between 1.0 and 1.12
                 then home_ml end                             as home_ml,
            case when {{ implied_prob('home_ml') }} + {{ implied_prob('away_ml') }} between 1.0 and 1.12
                 then away_ml end                             as away_ml,
            case when {{ implied_prob('open_home_ml') }} + {{ implied_prob('open_away_ml') }} between 1.0 and 1.12
                 then open_home_ml end                        as open_home_ml,
            case when {{ implied_prob('open_home_ml') }} + {{ implied_prob('open_away_ml') }} between 1.0 and 1.12
                 then open_away_ml end                        as open_away_ml
        )
    from books
),

market as (
    select
        *,
        count(home_spread) over (partition by game_id)        as n_books,
        median(home_spread) over (partition by game_id)       as median_spread,
        count(total) over (partition by game_id)              as n_totals,
        median(total) over (partition by game_id)             as median_total
    from priced
),

flagged as (
    select
        *,
        -- spread sign agrees with this book's moneyline favourite (unknown counts as agreeing)
        coalesce(home_spread = 0 or home_ml = away_ml
                 or (home_spread < 0) = (home_ml < away_ml), true)        as line_consistent,
        n_books < 3 or abs(home_spread - median_spread) <= {{ spread_tol }} as spread_agrees,
        n_totals < 3 or abs(total - median_total) <= {{ total_tol }}       as total_agrees
    from market
),

spread_pick as (
    select *
    from flagged
    where home_spread is not null
    qualify row_number() over (
        partition by game_id
        order by line_consistent desc,
                 spread_agrees desc,
                 {% if league == 'nhl' %}abs(home_spread) = 1.5 desc,{% endif %}
                 priority, provider_id
    ) = 1
),

ml_pick as (
    select f.game_id, f.book as ml_book, f.ml_is_close, f.home_ml, f.away_ml
    from flagged f
    join spread_pick s using (game_id)
    where f.home_ml is not null and f.away_ml is not null
    qualify row_number() over (
        partition by f.game_id
        order by f.provider_id = s.provider_id desc, f.priority, f.provider_id
    ) = 1
),

total_pick as (
    select f.game_id, f.book as total_book, f.total_is_close, f.total, f.over_price, f.under_price
    from flagged f
    join spread_pick s using (game_id)
    where f.total is not null
    qualify row_number() over (
        partition by f.game_id
        order by f.total_agrees desc, f.provider_id = s.provider_id desc, f.priority, f.provider_id
    ) = 1
)

select
    s.game_id,
    s.season,
    s.provider_id,
    s.book,
    case when s.spread_is_close then 'close' else 'final' end   as line_snapshot,
    'espn:' || s.book || ':' || case when s.spread_is_close then 'close' else 'final' end as line_source,
    s.home_spread,
    s.home_spread_price,
    s.away_spread_price,
    m.ml_book,
    m.home_ml,
    m.away_ml,
    t.total_book,
    t.total,
    t.over_price,
    t.under_price,
    s.open_home_spread,
    s.open_home_spread_price,
    s.open_away_spread_price,
    s.open_home_ml,
    s.open_away_ml,
    s.open_total,
    s.line_consistent,
    s.spread_agrees                                           as spread_agrees_with_market,
    s.median_spread                                           as market_median_spread,
    s.n_books
from spread_pick s
left join ml_pick m using (game_id)
left join total_pick t using (game_id)
{% endmacro %}
