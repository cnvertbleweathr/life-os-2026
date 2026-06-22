# DRAFT -- NOT TESTED against your live FastAPI app, since I can't run it
# from this sandbox. Logically straightforward (a single SELECT against
# a table that already exists and is confirmed populated via your dbt
# run), but you should still verify it returns what's expected before
# trusting it in production.
#
# Replaces the earlier DRAFT_kglw_links_endpoint.py approach entirely --
# that one depended on kglw.net's broken links/show/{id} endpoint via
# kglw.show_links, which is confirmed dead (server-side PHP exception on
# every call, not a transient issue). This endpoint instead reads
# main_marts.mart_kglw_youtube_matches, which has no dependency on
# kglw.net's links API at all -- it matches the official YouTube channel
# directly against kglw.shows.
#
# Add this to api/routers/kglw.py. Route placement: anywhere in the file
# is safe -- "/youtube-matches" doesn't share a path prefix with any
# existing route (no /shows/{show_id} collision risk).

@router.get("/youtube-matches")
async def kglw_youtube_matches(
    request: Request,
    show_ids: str = Query(..., description="Comma-separated show_id list"),
):
    """
    YouTube video matches for one or more shows, sourced from
    main_marts.mart_kglw_youtube_matches (built by matching the official
    KGLW YouTube channel against kglw.shows directly -- see that model's
    header comment for the full matching logic and confirmed gotchas).

    Returns [] for show_ids with no match -- this is a normal, expected
    case (not every show has a corresponding YouTube upload), not an
    error condition.
    """
    db = get_db(request)
    try:
        ids = [int(x) for x in show_ids.split(",") if x.strip().isdigit()]
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        rows = query(db, f"""
            SELECT video_id, title, published_at, show_id, show_date,
                   venue_name, city, country, tour_year, night_number,
                   match_confidence
            FROM main_marts.mart_kglw_youtube_matches
            WHERE show_id IN ({placeholders})
            ORDER BY show_id
        """, ids)
        return rows
    except Exception:
        # Table may not exist yet if dbt hasn't been run since this mart
        # was added. Return [] rather than a 500 -- same pattern used
        # throughout this router (e.g. /reading/in-progress).
        return []
