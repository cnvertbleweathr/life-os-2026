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
  letterboxd.diary_entries     — watched films with dates, ratings, reviews and
                                 the TMDB movie id (the join key for mart_film_watches)

The feed only holds the latest ~50 entries; merging on entry_id keeps the
older ones, so history builds up as the daily sync runs.

Config:
  Set LETTERBOXD_USERNAME in .env or pass via --username
"""
from __future__ import annotations

import argparse
import os
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator

import dlt
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

RSS_BASE = "https://letterboxd.com/{username}/rss/"


def db_path() -> str:
    return os.getenv("ONS_DUCKDB_PATH", str(ROOT / "data" / "warehouse" / "ons.duckdb"))

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


def _text(item: ET.Element, tag: str) -> str | None:
    el = item.find(tag)
    if el is None or el.text is None:
        return None
    return el.text.strip() or None


def _int_or_none(text: str | None) -> int | None:
    try:
        return int(text) if text else None
    except ValueError:
        return None


def parse_feed(xml_text: str, username: str) -> list[dict]:
    """Turn the RSS document into diary rows. Pure, so it can be tested offline.

    Keeps watches and reviews (guid `letterboxd-watch-…` / `letterboxd-review-…`);
    skips lists and anything else the feed carries."""
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        return []

    ingested_at = datetime.now(timezone.utc).isoformat()
    rows: list[dict] = []
    for item in channel.findall("item"):
        title_raw = _text(item, "title") or ""
        link      = _text(item, "link") or ""
        guid      = _text(item, "guid") or link

        entry_type = None
        if guid.startswith("letterboxd-watch-"):
            entry_type = "watch"
        elif guid.startswith("letterboxd-review-"):
            entry_type = "review"
        else:
            continue  # lists, stories

        # Fall back to parsing "The Godfather, 1972 - ★★★★★" when the namespaced tags are absent.
        film_title = title_raw
        rating_str = None
        if " - " in title_raw:
            film_title, rating_str = (part.strip() for part in title_raw.rsplit(" - ", 1))
        film_year_inline = None
        year_match = re.search(r",\s*(\d{4})$", film_title)
        if year_match:
            film_year_inline = int(year_match.group(1))
            film_title = film_title[:year_match.start()].strip()

        film_title = _text(item, f"{{{LB_NS}}}filmTitle") or film_title
        film_year  = _parse_year(item) or film_year_inline

        member_rating = _text(item, f"{{{LB_NS}}}memberRating")
        try:
            rating = float(member_rating) if member_rating else _parse_rating(rating_str)
        except ValueError:
            rating = _parse_rating(rating_str)

        watched_date = _parse_watched_date(item)
        rewatch = (_text(item, f"{{{LB_NS}}}rewatch") or "").lower() == "yes"
        liked   = (_text(item, f"{{{LB_NS}}}memberLike") or "").lower() == "yes"

        rows.append({
            "entry_id":        guid or f"{film_title}_{watched_date}",
            "entry_type":      entry_type,
            "film_title":      film_title,
            "film_year":       film_year,
            "tmdb_id":         _int_or_none(_text(item, f"{{{TMDB_NS}}}movieId")),
            "watched_date":    watched_date,
            "rating":          rating,
            "liked":           liked,
            "review":          _extract_review(_text(item, "description")),
            "is_rewatch":      rewatch,
            "film_url":        link,
            "letterboxd_user": username,
            "ingested_at":     ingested_at,
        })
    return rows


def fetch_feed(username: str) -> str:
    url = RSS_BASE.format(username=username)
    resp = requests.get(
        url,
        headers={"User-Agent": "ons-2026/1.0 (personal use)"},
        timeout=15,
    )
    if resp.status_code == 404:
        raise SystemExit(
            f"Letterboxd user '{username}' not found or feed is private.\n"
            f"Check LETTERBOXD_USERNAME in .env"
        )
    resp.raise_for_status()
    return resp.text


@dlt.resource(
    name="diary_entries",
    write_disposition="merge",
    primary_key="entry_id",
    # Nullable columns are declared: dlt drops a column that is null in every row of a
    # load, and stg_letterboxd__diary selects them by name.
    columns={
        "tmdb_id":      {"data_type": "bigint"},
        "film_year":    {"data_type": "bigint"},
        "rating":       {"data_type": "double"},
        "review":       {"data_type": "text"},
        "watched_date": {"data_type": "text"},
        "liked":        {"data_type": "bool"},
        "is_rewatch":   {"data_type": "bool"},
        "entry_type":   {"data_type": "text"},
    },
)
def letterboxd_diary(username: str) -> Iterator[dict]:
    """Fetch Letterboxd diary entries from RSS feed."""
    rows = parse_feed(fetch_feed(username), username)
    print(f"  Found {len(rows)} diary entries for @{username}")
    yield from rows


def build_summary(username: str) -> list[dict]:
    """
    Build a YTD summary from diary entries already loaded into DuckDB.
    Called after the DLT pipeline completes.
    """
    import duckdb
    path = Path(db_path())
    if not path.exists():
        return []

    try:
        con = duckdb.connect(str(path), read_only=True)
        year = date.today().year
        rows = con.execute("""
            SELECT
                count(*)                                    AS films_watched,
                round(avg(rating) FILTER (WHERE rating IS NOT NULL), 2) AS avg_rating,
                sum(CASE WHEN is_rewatch THEN 1 ELSE 0 END) AS rewatches,
                count(*) FILTER (WHERE rating = 5.0)        AS perfect_scores,
                min(watched_date)                           AS first_watch,
                max(watched_date)                           AS last_watch
            FROM letterboxd.diary_entries
            WHERE year(watched_date::date) = ?
              AND letterboxd_user = ?
        """, [year, username]).df()
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
        rows = parse_feed(fetch_feed(args.username), args.username)
        print(f"[dry-run] Parsed {len(rows)} entries; would merge into letterboxd.diary_entries")
        for r in rows[:5]:
            print(f"  {r['watched_date']}  tmdb={r['tmdb_id']}  {r['rating']}  {r['film_title']} ({r['film_year']})")
        return 0

    pipeline = dlt.pipeline(
        pipeline_name="letterboxd",
        destination=dlt.destinations.duckdb(db_path()),
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
