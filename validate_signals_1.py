import duckdb
con = duckdb.connect('data/warehouse/ons.duckdb', read_only=True)
 
print('=== PPA THRESHOLDS ===')
print(con.execute("""
SELECT
    CASE
        WHEN off_ppa_gap > 0.30 THEN 'PPA >0.30'
        WHEN off_ppa_gap > 0.15 THEN 'PPA >0.15'
        WHEN off_ppa_gap > 0.05 THEN 'PPA >0.05'
        ELSE 'no edge'
    END AS ppa_bucket,
    count(*) AS games,
    round(avg(CASE WHEN spread_covered THEN 1.0 ELSE 0.0 END)*100,1) AS home_cover,
    round(avg(CASE WHEN spread_covered THEN 0.909 ELSE -1.0 END)*100,1) AS home_roi
FROM main_marts.mart_cfbd_game_context
WHERE spread_covered IS NOT NULL AND off_ppa_gap IS NOT NULL
GROUP BY 1 ORDER BY min(off_ppa_gap) DESC
""").df().to_string())
 
con.close()
 