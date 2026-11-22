"""
record_featured() against a throwaway DuckDB file (never the warehouse).

  uv run --with pytest pytest tests/test_morning_brief_featured.py -q
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.morning_brief.featured import record_featured  # noqa: E402
from pipelines.news_pipeline import article_id  # noqa: E402

DAY = date(2026, 11, 21)


def test_records_links_and_is_idempotent(tmp_path):
    db = str(tmp_path / "t.duckdb")
    links = ["https://example.com/a?utm_source=rss", ("https://example.com/b/", "Science")]
    assert record_featured(links, DAY, path=db) == 2
    # same day again: nothing new; tracking params and trailing slash don't create dupes
    assert record_featured(["https://example.com/a", "https://example.com/b"], DAY, path=db) == 0
    # a later day is a new row (a follow-up)
    assert record_featured(["https://example.com/a"], date(2026, 11, 22), path=db) == 1

    con = duckdb.connect(db, read_only=True)
    rows = con.execute(
        "SELECT article_id, url, featured_on, section FROM brief.featured_news ORDER BY featured_on, url"
    ).fetchall()
    con.close()
    assert rows[0] == (article_id("https://example.com/a"), "https://example.com/a", DAY, None)
    assert rows[1][3] == "Science"
    assert len(rows) == 3


def test_empty_links_do_not_touch_the_db(tmp_path):
    db = tmp_path / "t.duckdb"
    assert record_featured(["", "  "], DAY, path=str(db)) == 0
    assert not db.exists()
