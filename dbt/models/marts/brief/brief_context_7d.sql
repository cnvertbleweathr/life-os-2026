-- brief_context_7d.sql
--
-- Everything the morning brief may say about the last 7 days (and the coming
-- week's games), as one long table. The brief agent groups it by domain.
--
-- Grain: one row per fact-bearing item. Columns:
--   domain            fitness | music | cfb_picks | cfb_games | team_games | news
--   ref               stable id; the brief's source_refs must use these
--   item_date         the day the item belongs to (null for season-level rows)
--   kind              what sort of row (activity, week_summary, pick, record, game, ...)
--   title             short label
--   url               link to the source, when one exists
--   facts             JSON of the exact numbers the brief may quote
--   already_featured / featured_on   news only; null elsewhere
--
-- Window: item_date in [today - 6, today] for things that happened; games run to
-- today + 7 so the brief can preview the next one. Followed teams (Nov 2026):
-- UCF and Penn State (cfbd.games), and the ESPN MY_TEAMS that the warehouse
-- carries: Magic, Nuggets (NBA), Panthers, Avalanche (NHL). The Bucs, Orlando
-- City, Marlins and Rockies have no warehouse source yet.
--
-- Music comes from the Spotify export files, which can lag weeks behind; the
-- week_summary row carries newest_play_date so the brief can tell.

{% set data_dir = var('data_dir') %}
{% set streams_csv = data_dir ~ '/spotify/processed/streams_clean.csv' %}
{% set daily10_json = data_dir ~ '/spotify/processed/daily10_latest.json' %}
{% set cfb_teams = ['UCF', 'Penn State'] %}

with params as (
    select current_date as today, current_date - 6 as week_start
),

-- ── fitness ─────────────────────────────────────────────────────────────────
activities as (
    select
        strava_id,
        name,
        activity_type,
        is_run,
        cast(start_date as date)                    as activity_date,
        round(distance_miles, 2)                    as distance_miles,
        round(moving_time_s / 60.0)::int            as moving_minutes,
        round(total_elevation_gain_m * 3.28084)::int as elevation_ft,
        round(average_heartrate)::int               as avg_hr
    from strava.activities
),

run_days as (
    select distinct activity_date as d from activities where is_run
),

run_islands as (
    select d, d - (row_number() over (order by d))::int as island from run_days
),

run_streak as (
    -- consecutive run days ending today, or yesterday if today has no run yet
    select count(*) as days
    from run_islands
    where island = (
        select island from run_islands, params
        where d = (select max(d) from run_days, params where d >= today - 1 and d <= today)
    )
),

fitness as (
    select
        'fitness' as domain,
        'strava:' || strava_id as ref,
        activity_date as item_date,
        'activity' as kind,
        name as title,
        'https://www.strava.com/activities/' || strava_id as url,
        json_object(
            'activity_type', activity_type, 'distance_miles', distance_miles,
            'moving_minutes', moving_minutes, 'elevation_ft', elevation_ft, 'avg_hr', avg_hr
        ) as facts
    from activities, params
    where activity_date between week_start and today

    union all

    select
        'fitness', 'fitness:week', (select today from params), 'week_summary',
        'Training week', null,
        json_object(
            'activities',        count(*) filter (where a.activity_date >= p.week_start),
            'runs',              count(*) filter (where a.is_run and a.activity_date >= p.week_start),
            'run_miles',         round(coalesce(sum(a.distance_miles) filter (where a.is_run and a.activity_date >= p.week_start), 0), 1),
            'longest_run_miles', max(a.distance_miles) filter (where a.is_run and a.activity_date >= p.week_start),
            'active_minutes',    coalesce(sum(a.moving_minutes) filter (where a.activity_date >= p.week_start), 0),
            'prev_week_run_miles', round(coalesce(sum(a.distance_miles) filter (where a.is_run and a.activity_date < p.week_start), 0), 1),
            'run_streak_days',   (select days from run_streak),
            'newest_activity_date', max(a.activity_date)
        )
    from activities a, params p
    where a.activity_date between p.week_start - 7 and p.today

    union all

    select
        'fitness', 'fitness:training_load', day, 'training_load', 'Training load', null,
        json_object('ctl', round(ctl, 1), 'atl', round(atl, 1), 'tsb', round(tsb, 1),
                    'readiness_signal', readiness_signal)
    from {{ ref('mart_training_load') }}, params
    where day = (select max(day) from {{ ref('mart_training_load') }} where day <= today)

    union all

    select
        'fitness', 'sugarwod:' || date || ':' || left(md5(title), 8), date, 'crossfit',
        title, null,
        json_object('result', best_result_display, 'score_type', score_type,
                    'rx_or_scaled', rx_or_scaled, 'pr', pr)
    from sugarwod.workouts, params
    where date between week_start and today
),

-- ── music ───────────────────────────────────────────────────────────────────
{% if file_exists(streams_csv) %}
streams as (
    select
        cast(played_at as timestamp)::date as play_date,
        artist_name,
        ms_played
    from read_csv('{{ streams_csv }}', header = true,
                  columns = {'played_at': 'VARCHAR', 'artist_name': 'VARCHAR',
                             'track_name': 'VARCHAR', 'ms_played': 'BIGINT',
                             'source_file': 'VARCHAR'})
),
{% else %}
streams as (
    select null::date as play_date, null::varchar as artist_name, null::bigint as ms_played
    where false
),
{% endif %}

week_streams as (
    select s.* from streams s, params p where s.play_date between p.week_start and p.today
),

top_artists as (
    select
        artist_name,
        count(*)                              as plays,
        round(sum(ms_played) / 60000.0)::int  as minutes,
        row_number() over (order by count(*) desc, artist_name) as rnk
    from week_streams
    group by 1
),

music as (
    select
        'music' as domain, 'music:week' as ref, (select today from params) as item_date,
        'week_summary' as kind, 'Listening week' as title, null as url,
        json_object(
            'plays',            (select count(*) from week_streams),
            'minutes',          (select coalesce(round(sum(ms_played) / 60000.0), 0)::int from week_streams),
            'artists',          (select count(distinct artist_name) from week_streams),
            'newest_play_date', (select max(play_date) from streams)
        ) as facts

    union all

    select
        'music', 'music:artist:' || lower(regexp_replace(artist_name, '[^A-Za-z0-9]+', '-', 'g')),
        (select today from params), 'top_artist', artist_name, null,
        json_object('plays', plays, 'minutes', minutes, 'rank', rnk)
    from top_artists
    where rnk <= 5

{% if file_exists(daily10_json) %}
    union all

    select
        'music', 'music:daily10:' || date, cast(date as date), 'playlist', 'Daily 10 playlist',
        'https://open.spotify.com/playlist/' || playlist_id,
        json_object('discovery_artists', tewnidge_artists)
    from read_json_auto('{{ daily10_json }}'), params
    where cast(date as date) between week_start and today
{% endif %}
),

-- ── CFB picks (published picks only, as on the Live Tracker) ────────────────
picks as (
    select *
    from cfbd.live_picks
    where meets_publish_bar
      and season = (select max(season) from cfbd.live_picks)
),

recent_weeks as (
    select distinct week from picks order by week desc limit 2
),

cfb_picks as (
    select
        'cfb_picks' as domain,
        'pick:' || season || ':' || week || ':' || left(md5(matchup || bet), 8) as ref,
        cast(generated_at as date) as item_date,
        'pick' as kind,
        matchup as title,
        null as url,
        json_object(
            -- bet carries the line from the bettor's side; the raw line column is
            -- home-signed and contradicts it for away bets, so it's left out
            'week', week, 'bet', bet, 'outcome', outcome,
            'units', round(pnl, 2), 'home_score', home_score, 'away_score', away_score
        ) as facts
    from picks
    where week in (select week from recent_weeks)

    union all

    select
        'cfb_picks', 'picks:week:' || season || ':' || week,
        max(cast(generated_at as date)), 'week_record', 'Week ' || week || ' record', null,
        json_object(
            'week', week,
            'wins',    count(*) filter (where outcome = 'win'),
            'losses',  count(*) filter (where outcome = 'loss'),
            'pushes',  count(*) filter (where outcome = 'push'),
            'pending', count(*) filter (where coalesce(outcome, 'pending') = 'pending'),
            'units',   round(coalesce(sum(pnl) filter (where outcome in ('win', 'loss', 'push')), 0), 2)
        )
    from picks
    where week in (select week from recent_weeks)
    group by season, week

    union all

    select
        'cfb_picks', 'picks:season:' || season, null, 'season_record',
        season || ' season record', null,
        json_object(
            'graded_picks', graded_picks, 'wins', wins, 'losses', losses, 'pushes', pushes,
            'win_rate_pct', win_rate_pct, 'units', round(total_pnl, 2),
            'roi_pct', round(roi_pct, 1), 'pending', pending_picks
        )
    from {{ ref('mart_live_picks') }}
    where season = (select max(season) from {{ ref('mart_live_picks') }})
),

-- ── followed CFB teams ──────────────────────────────────────────────────────
cfb_team_games as (
    select
        g.game_id, g.season, g.week, cast(g.start_date as date) as game_date,
        t.team,
        case when g.home_team = t.team then g.away_team else g.home_team end as opponent,
        case when g.neutral_site then 'neutral'
             when g.home_team = t.team then 'home' else 'away' end as venue,
        case when g.home_team = t.team then g.home_points else g.away_points end as team_points,
        case when g.home_team = t.team then g.away_points else g.home_points end as opp_points
    from cfbd.games g
    join (select unnest({{ cfb_teams }}) as team) t
      on t.team in (g.home_team, g.away_team)
    where g.season = (select max(season) from cfbd.games where start_date <= now())
),

cfb_team_games_rec as (
    select
        *,
        case when team_points > opp_points then 'W'
             when team_points < opp_points then 'L' end as result,
        count(*) filter (where team_points > opp_points)
            over (partition by team order by game_date rows unbounded preceding) as wins_to_date,
        count(*) filter (where team_points < opp_points)
            over (partition by team order by game_date rows unbounded preceding) as losses_to_date
    from cfb_team_games
),

draft as (
    select college_team, year, count(*) as players,
           arg_min(name, overall) as top_pick, arg_min(position, overall) as top_pick_position,
           min(overall) as top_pick_overall, arg_min(round, overall) as top_pick_round,
           arg_min(nfl_team, overall) as top_pick_nfl_team
    from cfbd.draft_production
    where college_team in {{ "('" ~ cfb_teams | join("', '") ~ "')" }}
      and year = (select max(year) from cfbd.draft_production)
    group by 1, 2
),

cfb_games as (
    select
        'cfb_games' as domain,
        'cfb_game:' || game_id as ref,
        game_date as item_date,
        case when team_points is null then 'upcoming_game' else 'game' end as kind,
        team || (case venue when 'home' then ' vs ' when 'away' then ' at ' else ' vs ' end) || opponent as title,
        null as url,
        json_object(
            'team', team, 'opponent', opponent, 'venue', venue, 'week', week,
            'team_points', team_points, 'opp_points', opp_points, 'result', result,
            'record_after', case when result is not null then wins_to_date || '-' || losses_to_date end
        ) as facts
    from cfb_team_games_rec, params
    where game_date between week_start and today + 7

    union all

    select
        'cfb_games', 'cfb_record:' || team, null, 'season_record', team || ' season record', null,
        json_object('team', team, 'wins', max(wins_to_date), 'losses', max(losses_to_date))
    from cfb_team_games_rec
    where result is not null
    group by team

    union all

    select
        'cfb_games', 'draft:' || lower(replace(college_team, ' ', '-')) || ':' || year, null,
        'draft_class', college_team || ' in the ' || year || ' NFL Draft', null,
        json_object('school', college_team, 'year', year, 'players_drafted', players,
                    'top_pick', top_pick, 'top_pick_position', top_pick_position,
                    'top_pick_overall', top_pick_overall, 'top_pick_round', top_pick_round,
                    'top_pick_nfl_team', top_pick_nfl_team)
    from draft
),

-- ── followed pro teams (NBA / NHL in the warehouse) ─────────────────────────
pro_games as (
    select 'nba' as league, game_id, season, game_date, home_team, away_team,
           home_score, away_score, completed, false as went_ot_loss_possible, went_ot
    from {{ ref('stg_nba__games') }}
    where 'ORL' in (home_team, away_team) or 'DEN' in (home_team, away_team)
    union all
    select 'nhl', game_id, season, game_date, home_team, away_team,
           home_score, away_score, completed, true, went_ot
    from {{ ref('stg_nhl__games') }}
    where 'FLA' in (home_team, away_team) or 'COL' in (home_team, away_team)
),

pro_team_games as (
    select
        p.league, p.game_id, p.season, p.game_date, t.team,
        case when p.home_team = t.team then p.away_team else p.home_team end as opponent,
        case when p.home_team = t.team then 'home' else 'away' end as venue,
        case when p.completed then case when p.home_team = t.team then p.home_score else p.away_score end end as team_score,
        case when p.completed then case when p.home_team = t.team then p.away_score else p.home_score end end as opp_score,
        t.team_name, p.went_ot, p.went_ot_loss_possible
    from pro_games p
    join (values ('nba', 'ORL', 'Orlando Magic'), ('nba', 'DEN', 'Denver Nuggets'),
                 ('nhl', 'FLA', 'Florida Panthers'), ('nhl', 'COL', 'Colorado Avalanche'))
         as t(league, team, team_name)
      on t.league = p.league and t.team in (p.home_team, p.away_team)
    where p.season = (select max(season) from pro_games where league = p.league)
),

pro_team_games_rec as (
    select
        *,
        case when team_score > opp_score then 'W'
             when team_score < opp_score and went_ot and went_ot_loss_possible then 'OTL'
             when team_score < opp_score then 'L' end as result
    from pro_team_games
),

pro_records as (
    select league, team,
           count(*) filter (where result = 'W')   as wins,
           count(*) filter (where result = 'L')   as losses,
           count(*) filter (where result = 'OTL') as ot_losses
    from pro_team_games_rec
    group by 1, 2
),

team_games as (
    select
        'team_games' as domain,
        g.league || ':' || g.game_id || ':' || g.team as ref,
        g.game_date as item_date,
        case when g.result is null then 'upcoming_game' else 'game' end as kind,
        g.team || (case g.venue when 'home' then ' vs ' else ' at ' end) || g.opponent as title,
        'https://www.espn.com/' || g.league || '/game/_/gameId/' || g.game_id as url,
        json_object(
            'league', g.league, 'team', g.team, 'team_name', g.team_name,
            'opponent', g.opponent, 'venue', g.venue,
            'team_score', g.team_score, 'opp_score', g.opp_score, 'result', g.result,
            'season_record', r.wins || '-' || r.losses
                             || case when g.league = 'nhl' then '-' || r.ot_losses else '' end
        ) as facts
    from pro_team_games_rec g
    join pro_records r using (league, team), params
    -- next 7 days of schedule would swamp the section; keep only the next game per team
    where g.game_date between week_start and today
       or g.game_date = (select min(x.game_date) from pro_team_games x
                         where x.team = g.team and x.game_date > today)
),

-- ── news ────────────────────────────────────────────────────────────────────
news as (
    select
        'news' as domain,
        'news:' || article_id as ref,
        story_date as item_date,
        category as kind,
        title,
        url,
        json_object('source', source, 'summary', summary, 'times_featured', times_featured) as facts,
        already_featured,
        featured_on
    from {{ ref('news_for_brief') }}
),

unioned as (
    select *, null::boolean as already_featured, null::date as featured_on from fitness
    union all select *, null, null from music
    union all select *, null, null from cfb_picks
    union all select *, null, null from cfb_games
    union all select *, null, null from team_games
    union all select * from news
)

select
    domain, ref, cast(item_date as date) as item_date, kind, title, url, facts::json as facts,
    already_featured, featured_on,
    current_date as built_for
from unioned
