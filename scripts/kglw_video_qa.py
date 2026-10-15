#!/usr/bin/env python3
"""
scripts/kglw_video_qa.py — sanity check for the King Gizzard page.

Prints:
  1. Freshness: newest show date in kglw.shows, newest upload in
     kglw_youtube.videos, count of upcoming shows.
  2. Live uploads ("Live in/at ...") that did NOT land in
     mart_kglw_youtube_matches — each one is either a show kglw.net
     hasn't listed yet, or a title needing a new row in that model's
     festival_aliases CTE.
  3. Uploads that are neither a matched live show nor a music video,
     so you can spot official videos the music-video regex missed.

Read-only. Stop FastAPI first if it holds the DuckDB write lock.

Usage:
  python scripts/kglw_video_qa.py
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse" / "ons.duckdb"


def main() -> int:
    con = duckdb.connect(str(DB), read_only=True)

    print("── Freshness ─────────────────────────────────────────")
    newest_show, upcoming = con.execute(
        "SELECT max(CAST(show_date AS DATE)), "
        "count(*) FILTER (WHERE CAST(show_date AS DATE) >= ?) FROM kglw.shows",
        [date.today()],
    ).fetchone()
    newest_upload = con.execute(
        "SELECT max(CAST(published_at AS TIMESTAMP)) FROM kglw_youtube.videos"
    ).fetchone()[0]
    n_mv = con.execute("SELECT count(*) FROM main_marts.mart_kglw_music_videos").fetchone()[0]
    n_rec = con.execute("SELECT count(*) FROM main_marts.mart_kglw_youtube_matches").fetchone()[0]
    print(f"  newest show in kglw.shows : {newest_show}  ({upcoming} upcoming)")
    print(f"  newest YouTube upload     : {newest_upload}")
    print(f"  matched live recordings   : {n_rec}")
    print(f"  music videos              : {n_mv}")

    print("\n── Live uploads with no matching show ────────────────")
    rows = con.execute("""
        SELECT CAST(v.published_at AS DATE), v.title
        FROM kglw_youtube.videos v
        LEFT JOIN main_marts.mart_kglw_youtube_matches m USING (video_id)
        WHERE m.video_id IS NULL
          AND regexp_matches(v.title, ' - live (in|at) ', 'i')
        ORDER BY 1 DESC
    """).fetchall()
    for d, t in rows:
        print(f"  {d}  {t}")
    if not rows:
        print("  (none)")

    print("\n── Other uploads (not a recording, not a music video) — newest 25 ──")
    rows = con.execute("""
        SELECT CAST(v.published_at AS DATE), v.title
        FROM kglw_youtube.videos v
        LEFT JOIN main_marts.mart_kglw_youtube_matches m USING (video_id)
        LEFT JOIN main_marts.mart_kglw_music_videos mv USING (video_id)
        WHERE m.video_id IS NULL AND mv.video_id IS NULL
          AND NOT regexp_matches(v.title, ' - live (in|at) ', 'i')
        ORDER BY 1 DESC
        LIMIT 25
    """).fetchall()
    for d, t in rows:
        print(f"  {d}  {t}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
