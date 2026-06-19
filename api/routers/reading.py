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
        SELECT books_read, fiction_books, nonfiction_books,
               pages_read, avg_days_to_finish
        FROM hardcover.reading_summary
        WHERE year = ?
        LIMIT 1
    """, [year]) or {}


@router.get("/in-progress")
async def books_in_progress(request: Request):
    """Books currently being read."""
    db = get_db(request)
    rows = query(db, """
        SELECT title, authors, classification, cover_url, started_at,
               cached_tags, pages, current_page
        FROM hardcover.books_read
        WHERE status IN ('reading', 'in_progress', 'currently-reading')
        ORDER BY started_at DESC NULLS LAST
        LIMIT 10
    """)
    # Fallback — some schemas use different status values
    if not rows:
        rows = query(db, """
            SELECT title, authors, classification, cover_url, cached_tags
            FROM hardcover.books_read
            WHERE status NOT IN ('read', 'finished', 'completed')
              AND marked_read_at IS NULL
            LIMIT 10
        """)
    return rows


@router.get("/read")
async def books_read(request: Request, year: int | None = None, limit: int = 50):
    """Books finished — defaults to current year."""
    db   = get_db(request)
    yr   = year or date.today().year
    return query(db, """
        SELECT title, authors, classification, cover_url,
               marked_read_at::date AS finished_date,
               cached_tags, pages
        FROM hardcover.books_read
        WHERE year(marked_read_at::date) = ?
          AND status IN ('read', 'finished', 'completed')
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
        WHERE year(marked_read_at::date) = ?
          AND status IN ('read', 'finished', 'completed')
        GROUP BY classification
        ORDER BY books DESC
    """, [yr])
