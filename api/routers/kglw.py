"""
/api/kglw — King Gizzard & The Lizard Wizard show catalog.

Backs the KGLW Globe page: Show mode (browse by venue/location) and
Song mode (browse by song, see everywhere it's been played).

Data confirmed against live kglw.net API responses (2026-06-20):
  - kglw.shows:    1104 rows, no working pagination upstream — full
                   dataset fetched in one call by the ingestion pipeline
  - kglw.songs:    1001 rows, no times_played/gap fields available
                   (KGLW's API doesn't expose frequency data on this
                   endpoint — would need deriving from setlists if needed)
  - kglw.venues:   671 rows, no lat/lng available anywhere in the API —
                   globe placement needs separate geocoding, not present yet
  - kglw.jamchart: 247 rows, primary key is uniqueid (string)

show_tags is stored as a JSON-encoded string column — parsed before
returning to the client so the frontend gets a real array, not a string.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from fastapi import APIRouter, Query, Request

from api.deps import get_db, query, query_one

router = APIRouter()


def _parse_show_tags(row: dict[str, Any]) -> dict[str, Any]:
    """show_tags is stored as a JSON string column — parse to a real list."""
    raw = row.get("show_tags")
    if isinstance(raw, str):
        try:
            row["show_tags"] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            row["show_tags"] = []
    elif raw is None:
        row["show_tags"] = []
    return row


# ── Summary ──────────────────────────────────────────────────────────────────

@router.get("/summary")
async def kglw_summary(request: Request):
    """Top-level counts for the Globe page header."""
    db = get_db(request)

    counts = query_one(db, """
        SELECT
            (SELECT count(*) FROM kglw.shows)    AS total_shows,
            (SELECT count(*) FROM kglw.songs)    AS total_songs,
            (SELECT count(*) FROM kglw.venues)   AS total_venues,
            (SELECT count(*) FROM kglw.jamchart) AS total_jamchart_entries
    """) or {}

    next_show = query_one(db, """
        SELECT show_date, venue_name, city, country, show_title
        FROM kglw.shows
        WHERE show_date >= ?
        ORDER BY show_date ASC
        LIMIT 1
    """, [date.today().isoformat()])

    return {
        **counts,
        "next_show": next_show,
    }


# ── Shows ────────────────────────────────────────────────────────────────────

@router.get("/shows")
async def kglw_shows(
    request:  Request,
    upcoming: bool = Query(False, description="Only shows on or after today"),
    venue_id: int | None = Query(None),
    limit:    int = Query(100),
):
    """
    List shows, most recent first.

    Filterable by venue_id (for Show mode — clicking a globe location)
    or upcoming=true (for tour/calendar context).
    """
    db = get_db(request)

    where  = []
    params: list[Any] = []

    if upcoming:
        where.append("show_date >= ?")
        params.append(date.today().isoformat())

    if venue_id is not None:
        where.append("venue_id = ?")
        params.append(venue_id)

    where_clause = f"WHERE {' AND '.join(where)}" if where else ""
    params.append(limit)

    rows = query(db, f"""
        SELECT show_id, show_date, show_time, artist, show_title,
               venue_id, venue_name, location, city, state, country,
               tour_name, show_year, show_month, show_day, show_dayname,
               show_tags, permalink
        FROM kglw.shows
        {where_clause}
        ORDER BY show_date DESC
        LIMIT ?
    """, params)

    return [_parse_show_tags(r) for r in rows]


@router.get("/shows/{show_id}")
async def kglw_show_detail(show_id: int, request: Request):
    """Single show with full detail."""
    db = get_db(request)

    show = query_one(db, """
        SELECT * FROM kglw.shows WHERE show_id = ?
    """, [show_id])

    if not show:
        return None

    return _parse_show_tags(show)


@router.get("/shows/on-this-day")
async def kglw_on_this_day(request: Request, month: int | None = None, day: int | None = None):
    """
    Shows played on this calendar date in any year — for the
    "On This Day" card on the Globe page. Defaults to today.
    """
    db = get_db(request)
    today = date.today()
    m = month or today.month
    d = day or today.day

    rows = query(db, """
        SELECT show_id, show_date, show_year, artist, show_title,
               venue_id, venue_name, city, state, country, permalink
        FROM kglw.shows
        WHERE show_month = ? AND show_day = ?
        ORDER BY show_year DESC
    """, [m, d])

    return rows


# ── Songs ────────────────────────────────────────────────────────────────────

@router.get("/songs")
async def kglw_songs(
    request: Request,
    search:  str | None = Query(None, description="Filter by name substring"),
    limit:   int = Query(200),
):
    """
    Song catalog.

    No times_played/gap/last_played_date available from KGLW's API —
    do not expect those fields. Frontend should treat their absence as
    expected, not as missing data.
    """
    db = get_db(request)

    if search:
        rows = query(db, """
            SELECT song_id, name, slug, is_original, original_artist
            FROM kglw.songs
            WHERE name ILIKE ?
            ORDER BY name
            LIMIT ?
        """, [f"%{search}%", limit])
    else:
        rows = query(db, """
            SELECT song_id, name, slug, is_original, original_artist
            FROM kglw.songs
            ORDER BY name
            LIMIT ?
        """, [limit])

    return rows


@router.get("/songs/{song_id}/shows")
async def kglw_song_shows(song_id: int, request: Request):
    """
    Every show where this song appears in the jam chart.

    NOTE: jamchart only contains 247 NOTABLE versions, not every time
    a song was ever played. This is not the song's full performance
    history — it's the subset flagged as jam-chart-worthy. A complete
    "everywhere this song has been played" feature would need full
    setlist data ingested for all 1104 shows, which the pipeline does
    not currently do (setlists are only fetched for the most recent 50).
    """
    db = get_db(request)

    rows = query(db, """
        SELECT j.show_id, j.show_date, j.venue_name, j.city, j.state,
               j.country, j.footnote, j.jamchart_note, j.is_recommended,
               s.venue_id
        FROM kglw.jamchart j
        LEFT JOIN kglw.shows s ON s.show_id = j.show_id
        WHERE j.song_id = ?
        ORDER BY j.show_date DESC
    """, [song_id])

    return rows


# ── Venues ───────────────────────────────────────────────────────────────────

@router.get("/venues")
async def kglw_venues(
    request: Request,
    search:  str | None = Query(None),
    limit:   int = Query(700),
):
    """
    Venue catalog.

    NOTE: no latitude/longitude available from KGLW's API at all —
    the Globe page cannot place real map pins from this data alone.
    Would need a separate geocoding pass (city/state/country -> lat/lng)
    before the globe visualization can plot venues spatially. Until
    then, the frontend should use a list/picker UI rather than assuming
    coordinates exist.
    """
    db = get_db(request)

    if search:
        rows = query(db, """
            SELECT venue_id, name, city, state, country, capacity, slug
            FROM kglw.venues
            WHERE name ILIKE ? OR city ILIKE ?
            ORDER BY name
            LIMIT ?
        """, [f"%{search}%", f"%{search}%", limit])
    else:
        rows = query(db, """
            SELECT venue_id, name, city, state, country, capacity, slug
            FROM kglw.venues
            ORDER BY name
            LIMIT ?
        """, [limit])

    return rows


# ── Jam chart ────────────────────────────────────────────────────────────────

@router.get("/jamchart")
async def kglw_jamchart(
    request:      Request,
    recommended:  bool | None = Query(None, description="Filter to is_recommended only"),
    limit:        int = Query(247),
):
    """Notable/legendary live versions."""
    db = get_db(request)

    if recommended is True:
        rows = query(db, """
            SELECT uniqueid, show_id, song_id, song_name, show_date,
                   venue_name, city, state, country, footnote,
                   jamchart_note, is_recommended, permalink
            FROM kglw.jamchart
            WHERE is_recommended = true
            ORDER BY show_date DESC
            LIMIT ?
        """, [limit])
    else:
        rows = query(db, """
            SELECT uniqueid, show_id, song_id, song_name, show_date,
                   venue_name, city, state, country, footnote,
                   jamchart_note, is_recommended, permalink
            FROM kglw.jamchart
            ORDER BY show_date DESC
            LIMIT ?
        """, [limit])

    return rows
# YouTube matches
@router.get("/youtube-matches")
async def kglw_youtube_matches(request: Request, show_ids: str = Query(...)):
    db = get_db(request)
    ids = [int(x) for x in show_ids.split(",") if x.strip().isdigit()]
    if not ids:
        return []
    ph = ",".join("?" * len(ids))
    cols = "video_id, title, published_at, show_id, "
    cols += "show_date, venue_name, city, country, "
    cols += "tour_year, night_number, match_confidence"
    sql = "SELECT " + cols + " "
    sql += "FROM main_marts.mart_kglw_youtube_matches "
    sql += "WHERE show_id IN (" + ph + ") "
    sql += "ORDER BY show_id"
    return query(db, sql, ids)

