"""
Which news stories the brief has already run, so tomorrow's brief can prefer
fresh ones (news_for_brief.already_featured / featured_on).

brief.featured_news has one row per (article, day it ran). Stories are keyed
by the same hash of the canonical URL that news.articles uses, so a link with
tracking params still matches. A link that isn't in news.articles is recorded
anyway (article_id from its URL), so nothing the brief linked is lost.

This writes to the warehouse: call it only when nothing else holds the DuckDB
write lock (in daily_sync, after the dbt step, while the API is stopped).

  uv run python -m agents.morning_brief.featured --list          # last 14 days
  uv run python -m agents.morning_brief.featured --init          # create the table
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

import duckdb

from agents.morning_brief.tools import DB_PATH
from pipelines.news_pipeline import article_id, canonical_url

# Keep in step with the on-run-start hook in dbt/dbt_project.yml, which
# creates the same table so news_for_brief builds on a fresh warehouse.
DDL = [
    "CREATE SCHEMA IF NOT EXISTS brief",
    """CREATE TABLE IF NOT EXISTS brief.featured_news (
        article_id  VARCHAR NOT NULL,
        url         VARCHAR NOT NULL,
        featured_on DATE    NOT NULL,
        section     VARCHAR,
        recorded_at TIMESTAMP DEFAULT current_timestamp,
        PRIMARY KEY (article_id, featured_on)
    )""",
]


def db_path() -> str:
    return str(DB_PATH)   # ONS_DB_PATH, same as the rest of the agent


def ensure_table(con: duckdb.DuckDBPyConnection) -> None:
    for stmt in DDL:
        con.execute(stmt)


def record_featured(links: list[str] | list[tuple[str, str | None]], featured_on: date,
                    *, path: str | None = None) -> int:
    """Record the news links a brief ran on `featured_on`. Returns rows added.

    `links` is a list of URLs, or of (url, section) pairs. Re-recording the
    same story on the same day is a no-op, so a re-run brief is safe.
    """
    pairs = [(l, None) if isinstance(l, str) else (l[0], l[1]) for l in links]
    pairs = [(u, s) for u, s in pairs if u and u.strip()]
    if not pairs:
        return 0
    con = duckdb.connect(path or db_path())
    try:
        ensure_table(con)
        before = con.execute("SELECT count(*) FROM brief.featured_news").fetchone()[0]
        con.executemany(
            "INSERT OR IGNORE INTO brief.featured_news (article_id, url, featured_on, section) "
            "VALUES (?, ?, ?, ?)",
            [(article_id(u), canonical_url(u), featured_on, s) for u, s in pairs],
        )
        after = con.execute("SELECT count(*) FROM brief.featured_news").fetchone()[0]
    finally:
        con.close()
    return after - before


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--init", action="store_true", help="create brief.featured_news")
    p.add_argument("--list", action="store_true", help="show the last 14 days")
    args = p.parse_args()

    if args.init:
        con = duckdb.connect(db_path())
        ensure_table(con)
        con.close()
        print("brief.featured_news ready")
    if args.list:
        con = duckdb.connect(db_path(), read_only=True)
        rows = con.execute(
            "SELECT featured_on, section, url FROM brief.featured_news "
            "WHERE featured_on >= ? ORDER BY featured_on DESC, section",
            [date.today() - timedelta(days=14)],
        ).fetchall()
        con.close()
        for r in rows:
            print(*r, sep="  ")
        print(f"{len(rows)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
