"""
/api/reading — books in progress, books read in 2026, YTD summary.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Request

from api.deps import get_db, query, query_one

router = APIRouter()


@router.get("/summary")
async def reading_summary(request: Request):
    """YTD reading stats."""
    db   = get_db(request)
    year = date.today().year
    return query_one(db, """
        SELECT total_read AS books_read, fiction_read AS fiction_books,
               nonfiction_read AS nonfiction_books
        FROM hardcover.reading_summary
        WHERE year = ?
        LIMIT 1
    """, [year]) or {}


@router.get("/in-progress")
async def books_in_progress(request: Request):
    """
    Books currently being read.

    NOTE: hardcover.books_read has no status/started_at columns — it only
    tracks finished books (every row has marked_read_at + year). There's
    currently no data source for "in progress" until the Hardcover pipeline
    is extended to capture that status. Returns [] until then rather than
    erroring on columns that don't exist.
    """
    return []


@router.get("/read")
async def books_read(request: Request, year: int | None = None, limit: int = 50):
    """Books finished — defaults to current year."""
    db   = get_db(request)
    yr   = year or date.today().year
    return query(db, """
        SELECT title, authors, classification,
               marked_read_at::date AS finished_date,
               cached_tags
        FROM hardcover.books_read
        WHERE year = ?
        ORDER BY marked_read_at DESC
        LIMIT ?
    """, [yr, limit])


@router.get("/by-classification")
async def books_by_classification(request: Request, year: int | None = None):
    """Fiction vs nonfiction breakdown."""
    db = get_db(request)
    yr = year or date.today().year
    return query(db, """
        SELECT classification, count(*) AS books
        FROM hardcover.books_read
        WHERE year = ?
        GROUP BY classification
        ORDER BY books DESC
    """, [yr])
