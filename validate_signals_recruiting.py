import duckdb
con = duckdb.connect('data/warehouse/ons.duckdb', read_only=True)

print('=== 4-YEAR WEIGHTED RECRUITING TALENT GAP vs ATS ===')
print(con.execute("""
    WITH talent_games AS (
        SELECT
            l.game_id, l.season, l.spread_covered,
            home_t.weighted_talent - away_t.weighted_talent AS talent_gap
        FROM main_marts.mart_cfbd_line_accuracy l
        JOIN main_marts.mart_cfbd_game_context gc ON gc.game_id = l.game_id
        LEFT JOIN main_marts.mart_cfbd_recruiting_talent home_t
            ON home_t.team = l.home_team AND home_t.season = l.season - 1
        LEFT JOIN main_marts.mart_cfbd_recruiting_talent away_t
            ON away_t.team = l.away_team AND away_t.season = l.season - 1
        WHERE l.spread_covered IS NOT NULL
          AND home_t.weighted_talent IS NOT NULL
          AND away_t.weighted_talent IS NOT NULL
    )
    SELECT
        CASE
            WHEN talent_gap > 50  THEN 'home dominant (>50)'
            WHEN talent_gap > 30  THEN 'home big edge (30-50)'
            WHEN talent_gap > 10  THEN 'home slight edge (10-30)'
            WHEN talent_gap BETWEEN -10 AND 10 THEN 'even'
            WHEN talent_gap < -30 THEN 'away big edge (<-30)'
            WHEN talent_gap < -10 THEN 'away slight edge (-30 to -10)'
            ELSE 'other'
        END AS bucket,
        count(*) AS games,
        round(avg(CASE WHEN spread_covered THEN 1.0 ELSE 0.0 END)*100,1) AS home_cover,
        round(avg(CASE WHEN spread_covered THEN 0.909 ELSE -1.0 END)*100,1) AS home_roi
    FROM talent_games
    GROUP BY 1 ORDER BY min(talent_gap) DESC
""").df().to_string())

print()
print('=== RECRUITING + PPA COMBO ===')
print(con.execute("""
    WITH talent_games AS (
        SELECT
            l.spread_covered,
            gc.off_ppa_gap,
            home_t.weighted_talent - away_t.weighted_talent AS talent_gap
        FROM main_marts.mart_cfbd_line_accuracy l
        JOIN main_marts.mart_cfbd_game_context gc ON gc.game_id = l.game_id
        LEFT JOIN main_marts.mart_cfbd_recruiting_talent home_t
            ON home_t.team = l.home_team AND home_t.season = l.season - 1
        LEFT JOIN main_marts.mart_cfbd_recruiting_talent away_t
            ON away_t.team = l.away_team AND away_t.season = l.season - 1
        WHERE l.spread_covered IS NOT NULL
          AND gc.off_ppa_gap IS NOT NULL
          AND home_t.weighted_talent IS NOT NULL
          AND away_t.weighted_talent IS NOT NULL
    )
    SELECT
        CASE
            WHEN off_ppa_gap > 0.15 AND talent_gap > 10  THEN 'PPA + home talent'
            WHEN off_ppa_gap > 0.15 AND talent_gap BETWEEN -10 AND 10 THEN 'PPA + even talent'
            WHEN off_ppa_gap > 0.15 AND talent_gap < -10 THEN 'PPA + away talent'
            ELSE 'no PPA edge'
        END AS scenario,
        count(*) AS games,
        round(avg(CASE WHEN spread_covered THEN 1.0 ELSE 0.0 END)*100,1) AS home_cover,
        round(avg(CASE WHEN spread_covered THEN 0.909 ELSE -1.0 END)*100,1) AS home_roi
    FROM talent_games
    GROUP BY 1 ORDER BY home_cover DESC
""").df().to_string())

con.close()
