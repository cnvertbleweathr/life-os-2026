import duckdb
con = duckdb.connect('data/warehouse/ons.duckdb', read_only=True)

print('=== SUCCESS RATE DIFFERENTIAL vs ATS ===')
print(con.execute("""
    SELECT
        CASE
            WHEN home_off_success_rate - away_def_success_rate > 0.10 THEN 'home dominant'
            WHEN home_off_success_rate - away_def_success_rate > 0.05 THEN 'home edge'
            WHEN home_off_success_rate - away_def_success_rate BETWEEN -0.05 AND 0.05 THEN 'even'
            WHEN home_off_success_rate - away_def_success_rate < -0.05 THEN 'away edge'
            ELSE 'other'
        END AS bucket,
        count(*) AS games,
        round(avg(CASE WHEN spread_covered THEN 1.0 ELSE 0.0 END)*100,1) AS home_cover,
        round(avg(CASE WHEN spread_covered THEN 0.909 ELSE -1.0 END)*100,1) AS home_roi
    FROM main_marts.mart_cfbd_game_context
    WHERE spread_covered IS NOT NULL
      AND home_off_success_rate IS NOT NULL
      AND away_def_success_rate IS NOT NULL
    GROUP BY 1
    ORDER BY min(home_off_success_rate - away_def_success_rate) DESC
""").df().to_string())

print()
print('=== SUCCESS RATE + PPA COMBO ===')
print(con.execute("""
    SELECT
        CASE
            WHEN off_ppa_gap > 0.15 AND home_off_success_rate - away_def_success_rate > 0.05 THEN 'PPA + home success'
            WHEN off_ppa_gap > 0.15 AND home_off_success_rate - away_def_success_rate BETWEEN -0.05 AND 0.05 THEN 'PPA + even success'
            WHEN off_ppa_gap > 0.15 AND home_off_success_rate - away_def_success_rate < -0.05 THEN 'PPA + away success'
            ELSE 'no PPA edge'
        END AS scenario,
        count(*) AS games,
        round(avg(CASE WHEN spread_covered THEN 1.0 ELSE 0.0 END)*100,1) AS home_cover,
        round(avg(CASE WHEN spread_covered THEN 0.909 ELSE -1.0 END)*100,1) AS home_roi
    FROM main_marts.mart_cfbd_game_context
    WHERE spread_covered IS NOT NULL
      AND off_ppa_gap IS NOT NULL
      AND home_off_success_rate IS NOT NULL
      AND away_def_success_rate IS NOT NULL
    GROUP BY 1
    ORDER BY home_cover DESC
""").df().to_string())

print()
print('=== DEF HAVOC vs ATS ===')
print(con.execute("""
    SELECT
        CASE
            WHEN home_def_havoc - away_def_havoc > 0.02 THEN 'home havoc edge'
            WHEN home_def_havoc - away_def_havoc BETWEEN -0.02 AND 0.02 THEN 'even'
            WHEN home_def_havoc - away_def_havoc < -0.02 THEN 'away havoc edge'
            ELSE 'other'
        END AS bucket,
        count(*) AS games,
        round(avg(CASE WHEN spread_covered THEN 1.0 ELSE 0.0 END)*100,1) AS home_cover,
        round(avg(CASE WHEN spread_covered THEN 0.909 ELSE -1.0 END)*100,1) AS home_roi
    FROM main_marts.mart_cfbd_game_context
    WHERE spread_covered IS NOT NULL
      AND home_def_havoc IS NOT NULL
      AND away_def_havoc IS NOT NULL
    GROUP BY 1
    ORDER BY min(home_def_havoc - away_def_havoc) DESC
""").df().to_string())

con.close()