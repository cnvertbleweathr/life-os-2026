#!/usr/bin/env python3
import sys, hashlib, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import duckdb
from generate_picks import cfbd_get
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")
con = duckdb.connect(DB_PATH)
con.execute("""
    CREATE TABLE IF NOT EXISTS cfbd.coaches (
        first_name VARCHAR NOT NULL, last_name VARCHAR NOT NULL,
        full_name VARCHAR, school VARCHAR NOT NULL, year BIGINT NOT NULL,
        games BIGINT, wins BIGINT, losses BIGINT, ties BIGINT,
        srs DOUBLE, sp_overall DOUBLE, sp_offense DOUBLE, sp_defense DOUBLE,
        preseason_rank BIGINT, postseason_rank BIGINT,
        _dlt_load_id VARCHAR NOT NULL, _dlt_id VARCHAR NOT NULL
    )
""")
load_id = str(time.time())
rows = 0
for year in [2021, 2022, 2023, 2024, 2025]:
    data = cfbd_get("/coaches", {"year": year})
    for coach in data:
        first = coach.get("firstName", "")
        last = coach.get("lastName", "")
        for season in (coach.get("seasons") or []):
            if season.get("year") != year:
                continue
            dlt_id = hashlib.md5(f"{first}|{last}|{season.get('school')}|{year}".encode()).hexdigest()
            con.execute(
                "INSERT INTO cfbd.coaches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [first, last, f"{first} {last}",
                 season.get("school"), season.get("year"),
                 season.get("games"), season.get("wins"),
                 season.get("losses"), season.get("ties"),
                 season.get("srs"), season.get("spOverall"),
                 season.get("spOffense"), season.get("spDefense"),
                 season.get("preSeasonRank"), season.get("postSeasonRank"),
                 load_id, dlt_id]
            )
            rows += 1
    print(f"{year}: loaded")
con.close()
print(f"Total rows: {rows}")
