#!/usr/bin/env python3
"""
pipelines/letterboxd_pipeline.py — Letterboxd film diary via RSS.

Ingests watched films, ratings, and reviews from Letterboxd's public RSS feed.
No authentication required — Letterboxd exposes public RSS for all accounts.

Feed URL: https://letterboxd.com/{username}/rss/

Usage:
  python pipelines/letterboxd_pipeline.py
  python pipelines/letterboxd_pipeline.py --username yourname
  python pipelines/letterboxd_pipeline.py --dry-run

Tables created in DuckDB:
  letterboxd.diary_entries     — watched films with dates, ratings, reviews
  letterboxd.films_summary     — YTD counts, avg rating, top genres

Config:
  Set LETTERBOXD_USERNAME in .env or pass via --username
"""
from __future__ import annotations

import argparse
import os
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

import dlt
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

RSS_BASE = "https://letterboxd.com/{username}/rss/"

# Letterboxd RSS uses a custom namespace for film metadata
LB_NS  = "https://letterboxd.com"
TMDB_NS = "https://themoviedb.org"


def _parse_rating(text: str | None) -> float | None:
    """Convert Letterboxd star rating text to numeric. '★★★½' → 3.5"""
    if not text:
        return None
    stars = text.strip()
    full  = stars.count("★")
    half  = "½" in stars
    if full == 0 and not half:
        return None
    return float(full) + (0.5 if half else 0.0)


def _parse_watched_date(item: ET.Element) -> str | None:
    """Extract watched date from Letterboxd RSS item."""
    # Try letterboxd:watchedDate first
    wd = item.find(f"{{{LB_NS}}}watchedDate")
    if wd is not None and wd.text:
        return wd.text.strip()

    # Fall back to pubDate
    pd = item.find("pubDate")
    if pd is not None and pd.text:
        try:
            dt = datetime.strptime(pd.text.strip(), "%a, %d %b %Y %H:%M:%S %z")
            return dt.date().isoformat()
        except ValueError:
            pass

    return None


def _parse_year(item: ET.Element) -> int | None:
    """Extract film release year from Letterboxd RSS item."""
    yr = item.find(f"{{{LB_NS}}}filmYear")
    if yr is not None and yr.text:
        try:
            return int(yr.text.strip())
        except ValueError:
            pass
    return None


def _extract_review(description: str | None) -> str | None:
    """Strip HTML tags from Letterboxd review description."""
    if not description:
        return None
    clean = re.sub(r"<[^>]+>", "", description).strip()
    # Remove "Watched on..." suffix that Letterboxd adds
    clean = re.sub(r"\s*Watched on .+$", "", clean, flags=re.IGNORECASE).strip()
    return clean or None


@dlt.resource(
    name="diary_entries",
    write_disposition="merge",
    primary_key="entry_id",
)
def letterboxd_diary(username: str) -> Iterator[dict]:
    """Fetch Letterboxd diary entries from RSS feed."""
    url = RSS_BASE.format(username=username)

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "ons-2026/1.0 (personal use)"},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        if resp.status_code == 404:
            raise SystemExit(
                f"Letterboxd user '{username}' not found or feed is private.\n"
                f"Check LETTERBOXD_USERNAME in .env"
            )
        raise

    root = ET.fromstring(resp.text)
    channel = root.find("channel")
    if channel is None:
        return

    items = channel.findall("item")
    print(f"  Found {len(items)} diary entries for @{username}")

    for item in items:
        title_el = item.find("title")
        link_el  = item.find("link")
        desc_el  = item.find("description")
        guid_el  = item.find("guid")

        title_raw = (title_el.text or "") if title_el is not None else ""
        link      = (link_el.text or "") if link_el is not None else ""
        guid      = (guid_el.text or link) if guid_el is not None else link

        # Parse film title and year from title like "The Godfather, 1972 - ★★★★★"
        film_title = title_raw
        rating_str = None
        if " - " in title_raw:
            parts      = title_raw.rsplit(" - ", 1)
            film_title = parts[0].strip()
            rating_str = parts[1].strip() if len(parts) > 1 else None

        # Remove year from title if present: "The Godfather, 1972" → "The Godfather"
        film_year_inline = None
        year_match = re.search(r",\s*(\d{4})$", film_title)
        if year_match:
            film_year_inline = int(year_match.group(1))
            film_title = film_title[:year_match.start()].strip()

        watched_date = _parse_watched_date(item)
        film_year    = _parse_year(item) or film_year_inline
        rating       = _parse_rating(rating_str)
        review       = _extract_review(
            (desc_el.text or "") if desc_el is not None else None
        )

        # Rewatch detection
        rewatch_el = item.find(f"{{{LB_NS}}}rewatch")
        is_rewatch = (rewatch_el is not None and
                      rewatch_el.text and
                      rewatch_el.text.strip().lower() == "yes")

        # Unique entry ID: guid or constructed from title + date
        entry_id = guid or f"{film_title}_{watched_date}"

        yield {
            "entry_id":     entry_id,
            "film_title":   film_title,
            "film_year":    film_year,
            "watched_date": watched_date,
            "rating":       rating,
            "review":       review,
            "is_rewatch":   is_rewatch,
            "film_url":     link,
            "letterboxd_user": username,
            "ingested_at":  datetime.utcnow().isoformat(),
        }


def build_summary(username: str) -> list[dict]:
    """
    Build a YTD summary from diary entries already loaded into DuckDB.
    Called after the DLT pipeline completes.
    """
    import duckdb
    db_path = ROOT / "data" / "warehouse" / "ons.duckdb"
    if not db_path.exists():
        return []

    try:
        con = duckdb.connect(str(db_path), read_only=True)
        year = date.today().year
        rows = con.execute(f"""
            SELECT
                count(*)                                    AS films_watched,
                round(avg(rating) FILTER (WHERE rating IS NOT NULL), 2) AS avg_rating,
                sum(CASE WHEN is_rewatch THEN 1 ELSE 0 END) AS rewatches,
                count(*) FILTER (WHERE rating = 5.0)        AS perfect_scores,
                min(watched_date)                           AS first_watch,
                max(watched_date)                           AS last_watch
            FROM letterboxd.diary_entries
            WHERE year(watched_date::date) = {year}
              AND letterboxd_user = '{username}'
        """).df()
        con.close()
        return rows.to_dict(orient="records")
    except Exception:
        return []


def main() -> int:
    p = argparse.ArgumentParser(description="Ingest Letterboxd diary via RSS.")
    p.add_argument("--username", default=os.getenv("LETTERBOXD_USERNAME", ""))
    p.add_argument("--dry-run",  action="store_true")
    args = p.parse_args()

    if not args.username:
        print("❌ No Letterboxd username. Set LETTERBOXD_USERNAME in .env or pass --username")
        return 1

    print(f"Letterboxd pipeline — @{args.username}")

    if args.dry_run:
        print("[dry-run] Would fetch:", RSS_BASE.format(username=args.username))
        print("[dry-run] Would load into: letterboxd.diary_entries")
        return 0

    pipeline = dlt.pipeline(
        pipeline_name="letterboxd",
        destination=dlt.destinations.duckdb(
            str(ROOT / "data" / "warehouse" / "ons.duckdb")
        ),
        dataset_name="letterboxd",
    )

    load_info = pipeline.run(letterboxd_diary(args.username))
    print(f"✅ Loaded: {load_info}")

    summary = build_summary(args.username)
    if summary and summary[0]:
        s = summary[0]
        print()
        print(f"  Films watched (YTD): {s.get('films_watched', 0)}")
        print(f"  Avg rating:          {s.get('avg_rating') or '—'}")
        print(f"  Rewatches:           {s.get('rewatches', 0)}")
        print(f"  Perfect scores:      {s.get('perfect_scores', 0)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
