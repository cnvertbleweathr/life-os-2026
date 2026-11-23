#!/usr/bin/env python3
"""
news_pipeline.py — Good News and Science headlines for the morning brief.

Sources (chosen Nov 2026):
  good_news  Good News Network and Reasons to be Cheerful, via RSS
  science    NewsAPI top-headlines, category=science (needs NEWS_API_KEY),
             plus the ScienceDaily top-science RSS feed

Writes news.articles (merge on article_id, a hash of the canonical URL), so a
story seen on several days is stored once and keeps its first_seen_at.
Only a short teaser is kept (summary, max 400 chars): the brief summarizes and
links to the source, it never reprints an article.

One failing source is reported and skipped; the run fails only if every
source fails.

Usage:
  python pipelines/news_pipeline.py            # fetch and load
  python pipelines/news_pipeline.py --dry-run  # fetch and print, no writes
"""

from __future__ import annotations

import argparse
import hashlib
import html
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import dlt
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

UA = {"User-Agent": "ons-2026/1.0 (personal use)"}
SUMMARY_MAX = 400

RSS_FEEDS = [
    # (source name, category, url)
    ("Good News Network", "good_news", "https://www.goodnewsnetwork.org/feed/"),
    ("Reasons to be Cheerful", "good_news", "https://reasonstobecheerful.world/feed/"),
    ("ScienceDaily", "science", "https://www.sciencedaily.com/rss/top/science.xml"),
]
NEWSAPI_URL = "https://newsapi.org/v2/top-headlines"


def db_path() -> str:
    return os.getenv("ONS_DUCKDB_PATH", str(ROOT / "data" / "warehouse" / "ons.duckdb"))


# ── normalising ──────────────────────────────────────────────────────────────

def canonical_url(url: str) -> str:
    """Drop tracking params and fragments so the same story hashes the same."""
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith(("utm_", "fbclid", "gclid"))]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def article_id(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode()).hexdigest()[:16]


def clean_text(raw: str | None, limit: int = SUMMARY_MAX) -> str | None:
    """Strip tags and entities, collapse whitespace, cut at a word boundary."""
    if not raw:
        return None
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    # WordPress feeds end teasers with "The post X appeared first on Y."
    text = re.sub(r"\s*The post .* appeared first on .*$", "", text)
    if not text:
        return None
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return text


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _row(*, url: str, title: str, summary: str | None, source: str, category: str,
         published: datetime | None, fetched_at: str) -> dict:
    return {
        "article_id": article_id(url),
        "url": url.strip(),
        "title": clean_text(title, limit=300),
        "summary": clean_text(summary),
        "source": source,
        "category": category,
        "published_at": _iso(published),
        "first_seen_at": fetched_at,
    }


# ── sources ──────────────────────────────────────────────────────────────────

def parse_rss(xml_text: str, source: str, category: str, fetched_at: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    rows = []
    for item in root.iter("item"):
        link = (item.findtext("link") or "").strip()
        title = (item.findtext("title") or "").strip()
        if not link or not title:
            continue
        published = None
        if item.findtext("pubDate"):
            try:
                published = parsedate_to_datetime(item.findtext("pubDate"))
            except (TypeError, ValueError):
                pass
        rows.append(_row(url=link, title=title, summary=item.findtext("description"),
                         source=source, category=category, published=published,
                         fetched_at=fetched_at))
    return rows


def parse_newsapi(payload: dict, category: str, fetched_at: str) -> list[dict]:
    if payload.get("status") != "ok":
        raise RuntimeError(f"NewsAPI: {payload.get('code')}: {payload.get('message')}")
    rows = []
    for a in payload.get("articles", []):
        url, title = a.get("url"), a.get("title")
        if not url or not title or title == "[Removed]":
            continue
        # NewsAPI appends " - Source" to titles; the source is stored separately.
        source = (a.get("source") or {}).get("name") or "NewsAPI"
        title = re.sub(rf"\s+[-–|]\s+{re.escape(source)}.*$", "", title)
        published = None
        if a.get("publishedAt"):
            try:
                published = datetime.fromisoformat(a["publishedAt"].replace("Z", "+00:00"))
            except ValueError:
                pass
        rows.append(_row(url=url, title=title, summary=a.get("description"), source=source,
                         category=category, published=published, fetched_at=fetched_at))
    return rows


def fetch_all() -> tuple[list[dict], list[str]]:
    """Return (rows, errors). Duplicate URLs across sources keep the first."""
    fetched_at = datetime.now(timezone.utc).isoformat()
    rows: list[dict] = []
    errors: list[str] = []

    for source, category, url in RSS_FEEDS:
        try:
            resp = requests.get(url, headers=UA, timeout=20)
            resp.raise_for_status()
            got = parse_rss(resp.text, source, category, fetched_at)
            print(f"  {source:<24} {category:<9} {len(got):>3} items")
            rows += got
        except Exception as e:  # one bad feed must not sink the rest
            errors.append(f"{source}: {e}")

    key = os.getenv("NEWS_API_KEY")
    if key:
        try:
            resp = requests.get(NEWSAPI_URL, headers={**UA, "X-Api-Key": key}, timeout=20,
                                params={"country": "us", "category": "science", "pageSize": 30})
            got = parse_newsapi(resp.json(), "science", fetched_at)
            print(f"  {'NewsAPI':<24} {'science':<9} {len(got):>3} items")
            rows += got
        except Exception as e:
            errors.append(f"NewsAPI: {e}")
    else:
        errors.append("NewsAPI: NEWS_API_KEY not set; skipped")

    seen: set[str] = set()
    unique = []
    for r in rows:
        if r["article_id"] not in seen:
            seen.add(r["article_id"])
            unique.append(r)
    return unique, errors


# ── load ─────────────────────────────────────────────────────────────────────

@dlt.resource(
    name="articles",
    write_disposition="merge",
    primary_key="article_id",
    columns={
        "summary":       {"data_type": "text"},
        "published_at":  {"data_type": "timestamp"},
        # keep_first_seen() carries the stored value over, since merge overwrites
        "first_seen_at": {"data_type": "timestamp"},
    },
)
def articles(rows: list[dict]) -> Iterator[dict]:
    yield from rows


def keep_first_seen(rows: list[dict]) -> list[dict]:
    """A merge overwrites every column, so carry first_seen_at over for known stories."""
    import duckdb
    path = Path(db_path())
    if not path.exists() or not rows:
        return rows
    try:
        con = duckdb.connect(str(path), read_only=True)
        known = dict(con.execute(
            "SELECT article_id, first_seen_at FROM news.articles WHERE article_id IN (SELECT unnest(?))",
            [[r["article_id"] for r in rows]],
        ).fetchall())
        con.close()
    except Exception:
        return rows   # first run: no table yet
    for r in rows:
        if r["article_id"] in known and known[r["article_id"]] is not None:
            r["first_seen_at"] = _iso(known[r["article_id"]])
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description="Ingest Good News and Science headlines.")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    print("News pipeline")
    rows, errors = fetch_all()
    for e in errors:
        print(f"  ⚠ {e}")
    if not rows:
        print("❌ No articles from any source")
        return 1

    if args.dry_run:
        print(f"[dry-run] {len(rows)} unique articles; would merge into news.articles")
        for r in rows[:6]:
            print(f"  {r['category']:<9} {r['source'][:18]:<18} {r['title'][:70]}")
        return 0

    rows = keep_first_seen(rows)
    pipeline = dlt.pipeline(
        pipeline_name="news",
        destination=dlt.destinations.duckdb(db_path()),
        dataset_name="news",
    )
    load_info = pipeline.run(articles(rows))
    print(f"✅ Loaded {len(rows)} articles: {load_info}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
