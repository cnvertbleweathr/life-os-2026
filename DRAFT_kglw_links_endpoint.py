# DRAFT — NOT VERIFIED AGAINST LIVE DATA
#
# This endpoint is missing from the current api/routers/kglw.py despite
# kglw_pipeline.py's kglw_links() resource already populating kglw.show_links
# (confirmed present in the pipeline code, NOT confirmed present in the
# router). Add this block to api/routers/kglw.py and test against your
# live DuckDB — I can't run this from the sandbox, so treat every field
# name and table reference below as "should be right based on the pipeline
# code" rather than "confirmed against real data."
#
# Known caveat from the pipeline: kglw_links() only ingests links for the
# most recent 100 shows (kglw_pipeline.py's _get_recent_show_ids(limit=100)
# call in main()), and ONLY when the pipeline is run WITHOUT --shows-only.
# If your last pipeline run used --shows-only, kglw.show_links may not
# exist at all or may be empty — check before assuming this endpoint will
# return real data.

@router.get("/shows/{show_id}/links")
async def kglw_show_links(show_id: int, request: Request):
    """
    YouTube/audio recording links for a single show.

    Returns [] if kglw.show_links doesn't exist yet (pipeline run with
    --shows-only) or if this show wasn't in the most recent 100 shows
    at ingestion time — both are real "no data" cases, not bugs, given
    the pipeline's current scope.
    """
    db = get_db(request)
    try:
        rows = query(db, """
            SELECT show_id, url, link_type, is_youtube, is_audio,
                   label, source, youtube_id
            FROM kglw.show_links
            WHERE show_id = ?
            ORDER BY is_youtube DESC
        """, [show_id])
        return rows
    except Exception:
        # Table may not exist if the pipeline has only ever run with
        # --shows-only. Return [] rather than a 500 — same pattern as
        # /reading/in-progress when its source data doesn't exist.
        return []


# Optional companion: bulk-fetch links for many shows at once, so the
# frontend's show list can show a "▶" play icon without N+1 requests.
# Only useful if you want the list view itself to indicate watchability
# without the user clicking each show first.
@router.get("/links")
async def kglw_links_bulk(
    request: Request,
    show_ids: str = Query(..., description="Comma-separated show_id list"),
):
    """Bulk lookup — youtube_id per show_id, for list-view play icons."""
    db = get_db(request)
    try:
        ids = [int(x) for x in show_ids.split(",") if x.strip().isdigit()]
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        rows = query(db, f"""
            SELECT show_id, youtube_id
            FROM kglw.show_links
            WHERE show_id IN ({placeholders}) AND is_youtube = true
            ORDER BY show_id
        """, ids)
        return rows
    except Exception:
        return []
