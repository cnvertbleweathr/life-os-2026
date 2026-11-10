{{ config(severity='warn') }}
-- Every ESPN odds provider seen in the raw tables has a row in
-- seeds/nba_nhl_odds_providers.csv. A new provider (a new book, a new live feed)
-- is never chosen until it is added with is_book and a priority. Warns only.

select 'nba' as league, provider_id, any_value(provider_name) as provider_name, count(distinct game_id) as games
from {{ source('nba', 'odds') }}
where provider_id not in (select provider_id from {{ ref('nba_nhl_odds_providers') }} where league = 'nba')
group by 1, 2

union all

select 'nhl', provider_id, any_value(provider_name), count(distinct game_id)
from {{ source('nhl', 'odds') }}
where provider_id not in (select provider_id from {{ ref('nba_nhl_odds_providers') }} where league = 'nhl')
group by 1, 2
