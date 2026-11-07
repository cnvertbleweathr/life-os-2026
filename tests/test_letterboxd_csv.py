"""
Tests for scripts/import_letterboxd_csv.py and the RSS/CSV dedupe in
stg_letterboxd__diary. Everything writes to tmp_path; no network.

  uv run --with pytest pytest tests/test_letterboxd_csv.py -q
"""

from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
DBT = Path(sys.executable).parent / "dbt"

spec = importlib.util.spec_from_file_location("import_letterboxd_csv", ROOT / "scripts/import_letterboxd_csv.py")
imp = importlib.util.module_from_spec(spec)
sys.modules["import_letterboxd_csv"] = imp   # dlt resolves the resource's module by name
spec.loader.exec_module(imp)

CSV = """Date,Name,Year,Letterboxd URI,Rating,Rewatch,Tags,Watched Date
2024-12-26,Moana 2,2024,https://boxd.it/a1,2,,,2024-12-25
2025-01-08,Heat,1995,https://boxd.it/a2,3.5,,crime,2025-01-07
2025-02-01,Heat,1995,https://boxd.it/a3,4,Yes,,2025-02-01
2026-10-31,The Texas Chain Saw Massacre,1974,https://boxd.it/a4,5,,,2026-10-30
2026-11-02,Carnival of Souls,1962,https://boxd.it/a5,,,,
,No Date Film,2000,https://boxd.it/a6,3,,,
2026-11-03,Carnival of Souls,1962,https://boxd.it/a7,4.5,,,2026-11-01
"""


# ── parsing ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    ("4.5", 4.5), ("5", 5.0), ("0.5", 0.5), ("", None), (None, None),
    ("  3 ", 3.0), ("abc", None), ("0", None), ("7", None),
])
def test_parse_rating(text, expected):
    assert imp.parse_rating(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("Yes", True), ("yes", True), (" Yes ", True), ("", False), (None, False), ("No", False),
])
def test_parse_rewatch(text, expected):
    assert imp.parse_rewatch(text) is expected


def test_parse_csv_dates_and_fields():
    rows = {r["entry_id"]: r for r in imp.parse_csv(io.StringIO(CSV))}
    assert "https://boxd.it/a6" not in rows                         # no watched or logged date: dropped
    assert rows["https://boxd.it/a1"]["watched_date"] == "2024-12-25"   # Watched Date, not logged Date
    assert rows["https://boxd.it/a5"]["watched_date"] == "2026-11-02"   # falls back to the logged Date
    heat = rows["https://boxd.it/a3"]
    assert heat["rating"] == 4.0 and heat["is_rewatch"] is True and heat["film_year"] == 1995
    assert rows["https://boxd.it/a2"]["tags"] == "crime"
    assert rows["https://boxd.it/a5"]["rating"] is None


def test_dedupe_by_entry_id_keeps_the_last_line():
    rows = [{"entry_id": "x", "rating": 3.0}, {"entry_id": "y"}, {"entry_id": "x", "rating": 4.0}]
    out = imp.dedupe(rows)
    assert len(out) == 2 and {r["entry_id"]: r for r in out}["x"]["rating"] == 4.0


# ── TMDB resolution ──────────────────────────────────────────────────────────

def test_resolve_prefers_rss_then_cache_then_search_and_caches_misses(tmp_path):
    rows = imp.parse_csv(io.StringIO(CSV))
    cache = imp.TmdbCache(tmp_path / "cache.json")
    cache.set(imp.film_key("Moana 2", 2024), 1241982)
    calls = []

    def search(title, year):
        calls.append((title, year))
        return {"Heat": 949}.get(title)

    known = {imp.film_key("The Texas Chain Saw Massacre", 1974): 30497}
    counts = imp.resolve_tmdb_ids(rows, known, cache, search)
    cache.save()

    by_title = {r["film_title"]: r["tmdb_id"] for r in rows}
    assert by_title == {"Moana 2": 1241982, "Heat": 949, "The Texas Chain Saw Massacre": 30497,
                        "Carnival of Souls": None}
    assert sorted(calls) == [("Carnival of Souls", 1962), ("Heat", 1995)]   # once per film
    assert counts == {"rss": 1, "cache": 1, "search": 1, "unresolved": 1}

    # Re-run from the saved cache: no searches, the miss is remembered too.
    calls.clear()
    imp.resolve_tmdb_ids(imp.parse_csv(io.StringIO(CSV)), known, imp.TmdbCache(tmp_path / "cache.json"), search)
    assert calls == []


def test_resolve_without_api_key_leaves_null():
    rows = imp.parse_csv(io.StringIO(CSV))
    counts = imp.resolve_tmdb_ids(rows, {}, imp.TmdbCache(Path("/nonexistent/cache.json")), None)
    assert all(r["tmdb_id"] is None for r in rows)
    assert counts["unresolved"] == 4 and counts["search"] == 0


# ── RSS/CSV dedupe through dbt ───────────────────────────────────────────────

@pytest.mark.skipif(not DBT.exists(), reason="dbt not installed in this environment")
def test_reimport_and_rss_overlap_make_no_duplicate_watches(tmp_path):
    db = tmp_path / "ons.duckdb"

    # The RSS table as letterboxd_pipeline loads it: TCSM on 2026-10-30, with TMDB id and liked.
    with duckdb.connect(str(db)) as con:
        con.execute("create schema letterboxd")
        con.execute("""
            create table letterboxd.diary_entries as select * from (values
              ('letterboxd-watch-1', 'watch', 'The Texas Chain Saw Massacre', 1974, 30497,
               '2026-10-30', 5.0, true, false, null, 'https://letterboxd.com/u/film/tcsm/', 'u', 'x'),
              ('letterboxd-watch-2', 'watch', 'Heat', 1995, 949,
               '2025-03-01', 4.0, false, true, null, 'https://letterboxd.com/u/film/heat/', 'u', 'x')
            ) t(entry_id, entry_type, film_title, film_year, tmdb_id, watched_date, rating, liked,
                is_rewatch, review, film_url, letterboxd_user, ingested_at)
        """)

    rows = imp.parse_csv(io.StringIO(CSV))
    imp.load(rows, destination_path=str(db), pipelines_dir=str(tmp_path / "dlt"))
    imp.load(imp.parse_csv(io.StringIO(CSV)), destination_path=str(db), pipelines_dir=str(tmp_path / "dlt"))

    (tmp_path / "profiles.yml").write_text(
        f"ons:\n  target: dev\n  outputs:\n    dev:\n      type: duckdb\n      path: {db}\n"
        f"      schema: main\n      threads: 1\n"
    )
    proc = subprocess.run(
        [str(DBT), "run", "--profiles-dir", str(tmp_path), "--project-dir", str(ROOT / "dbt"),
         "--target-path", str(tmp_path / "target"), "--log-path", str(tmp_path / "logs"),
         "--select", "stg_letterboxd__diary", "stg_plex__history", "mart_film_watches"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout[-2000:]

    with duckdb.connect(str(db), read_only=True) as con:
        assert con.sql("select count(*) from letterboxd.csv_diary").fetchone()[0] == 6   # re-import merged

        stg = con.sql("""select title, watched_date::varchar, source, tmdb_id, liked
                         from main_staging.stg_letterboxd__diary order by 2, 1""").fetchall()
        assert stg == [
            ("Moana 2",                      "2024-12-25", "csv", None,  False),
            ("Heat",                         "2025-01-07", "csv", 949,   False),  # borrowed from the RSS row
            ("Heat",                         "2025-02-01", "csv", 949,   False),
            ("Heat",                         "2025-03-01", "rss", 949,   False),
            ("The Texas Chain Saw Massacre", "2026-10-30", "rss", 30497, True),   # RSS wins over the CSV row
            ("Carnival of Souls",            "2026-11-01", "csv", None,  False),
            ("Carnival of Souls",            "2026-11-02", "csv", None,  False),
        ]

        mart = con.sql("""select title, watch_date::varchar, film_key, watch_number, is_rewatch
                          from main_marts.mart_film_watches order by 2, 1""").fetchall()
        assert len(mart) == 7
        assert con.sql("select count(*) = count(distinct watch_id) from main_marts.mart_film_watches").fetchone()[0]
        heat = [m for m in mart if m[0] == "Heat"]
        assert {m[2] for m in heat} == {"tmdb:949"} and [m[3] for m in heat] == [1, 2, 3]
        assert [m[2] for m in mart if m[0] == "Moana 2"] == ["title:moana 2:2024"]


class FakeSession:
    def __init__(self, results):
        self.results, self.calls = results, []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((params, headers))
        results = self.results

        class R:
            def raise_for_status(self): pass
            def json(self): return {"results": results}
        return R()


def test_tmdb_search_prefers_exact_year_and_handles_both_key_kinds():
    results = [{"id": 1, "release_date": "2018-10-19"}, {"id": 948, "release_date": "1978-10-25"}]

    v3 = FakeSession(results)
    assert imp.tmdb_search("abc123", v3)("Halloween", 1978) == 948
    params, headers = v3.calls[0]
    assert params["api_key"] == "abc123" and params["year"] == 1978 and "Authorization" not in headers

    v4 = FakeSession(results)
    assert imp.tmdb_search("eyJhbGciOi.token", v4)("Halloween", None) == 1   # no year: first result
    params, headers = v4.calls[0]
    assert headers["Authorization"] == "Bearer eyJhbGciOi.token" and "api_key" not in params

    assert imp.tmdb_search("k", FakeSession([]))("Nothing", 2000) is None
