#!/usr/bin/env python3
"""
scripts/import_letterboxd_csv.py: one-off backfill of the full Letterboxd diary.

The RSS feed (pipelines/letterboxd_pipeline.py) only holds the latest ~50
entries. Letterboxd's data export (Settings → Data → Export) has every diary
entry in diary.csv:

  Date, Name, Year, Letterboxd URI, Rating, Rewatch, Tags, Watched Date

Rows load into letterboxd.csv_diary, a sibling of the RSS table
letterboxd.diary_entries. stg_letterboxd__diary unions the two and keeps one
row per film + watched date, preferring the RSS row (it carries the TMDB id
and the liked flag), so mart_film_watches picks the backfill up as is.

Re-running is safe: rows merge on the entry's Letterboxd URI.

TMDB ids: the CSV has none. For each film the importer tries, in order:
  1. a TMDB id the RSS table already has for the same title + year;
  2. TMDB search by title + year, if TMDB_API_KEY is set in .env (a v3 API key
     or a v4 read access token);
  3. nothing: tmdb_id stays NULL and the mart keys the film on title:year.
Search results, misses included, are cached in data/film/tmdb_search_cache.json
so re-runs don't query again.

Usage:
  python scripts/import_letterboxd_csv.py --file ~/Downloads/letterboxd-export/diary.csv
  python scripts/import_letterboxd_csv.py --file ... --dry-run   # parse and report; no writes, no TMDB calls

Writing to the real warehouse needs the DuckDB lock, which FastAPI holds:
  launchctl bootout gui/$(id -u)/com.ons.fastapi
  python scripts/import_letterboxd_csv.py --file ...
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ons.fastapi.plist
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

import dlt
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

TMDB_SEARCH = "https://api.themoviedb.org/3/search/movie"


def db_path() -> str:
    return os.getenv("ONS_DUCKDB_PATH", str(ROOT / "data" / "warehouse" / "ons.duckdb"))


def data_dir() -> Path:
    return Path(os.getenv("ONS_DATA_DIR", ROOT / "data"))


# ── parsing ──────────────────────────────────────────────────────────────────

def parse_rating(text: str | None) -> float | None:
    """'4.5' → 4.5; '' → None. The export uses 0.5–5 in half steps."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if 0 < value <= 5 else None


def parse_rewatch(text: str | None) -> bool:
    """The export writes 'Yes' for a rewatch and leaves it empty otherwise."""
    return (text or "").strip().lower() in ("yes", "true", "1")


def _year(text: str | None) -> int | None:
    try:
        return int((text or "").strip())
    except ValueError:
        return None


def _date(text: str | None) -> str | None:
    text = (text or "").strip()
    try:
        return datetime.strptime(text, "%Y-%m-%d").date().isoformat() if text else None
    except ValueError:
        return None


def parse_csv(lines: Iterable[str]) -> list[dict]:
    """diary.csv → csv_diary rows (tmdb_id not yet resolved).

    Watched Date is the day watched; Date is the day it was logged and only
    stands in when Watched Date is missing. Rows with neither are dropped."""
    ingested_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for rec in csv.DictReader(lines):
        title = (rec.get("Name") or "").strip()
        watched = _date(rec.get("Watched Date")) or _date(rec.get("Date"))
        if not title or not watched:
            continue
        year = _year(rec.get("Year"))
        uri = (rec.get("Letterboxd URI") or "").strip()
        rows.append({
            "entry_id":     uri or f"{title}|{year}|{watched}",
            "film_title":   title,
            "film_year":    year,
            "tmdb_id":      None,
            "watched_date": watched,
            "logged_date":  _date(rec.get("Date")),
            "rating":       parse_rating(rec.get("Rating")),
            "is_rewatch":   parse_rewatch(rec.get("Rewatch")),
            "tags":         (rec.get("Tags") or "").strip() or None,
            "letterboxd_uri": uri or None,
            "ingested_at":  ingested_at,
        })
    return dedupe(rows)


def dedupe(rows: list[dict]) -> list[dict]:
    """One row per entry_id; a later line wins (the export is oldest first)."""
    return list({r["entry_id"]: r for r in rows}.values())


def film_key(title: str, year: int | None) -> str:
    return f"{title.strip().lower()}|{year if year is not None else ''}"


# ── TMDB resolution ──────────────────────────────────────────────────────────

class TmdbCache:
    """film_key → tmdb_id (or None for a search that found nothing), on disk."""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, int | None] = {}
        if path.exists():
            try:
                self.data = json.loads(path.read_text())
            except json.JSONDecodeError:
                self.data = {}

    def __contains__(self, key: str) -> bool:
        return key in self.data

    def get(self, key: str) -> int | None:
        return self.data.get(key)

    def set(self, key: str, value: int | None) -> None:
        self.data[key] = value

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1, sort_keys=True))
        tmp.replace(self.path)


def tmdb_search(api_key: str, session: requests.Session | None = None) -> Callable[[str, int | None], int | None]:
    """A title + year → TMDB id lookup. Accepts a v3 key or a v4 bearer token."""
    http = session or requests.Session()
    bearer = api_key.startswith("eyJ")   # v4 read access tokens are JWTs

    def search(title: str, year: int | None) -> int | None:
        params = {"query": title, "include_adult": "false"}
        if year:
            params["year"] = year
        headers = {"Accept": "application/json"}
        if bearer:
            headers["Authorization"] = f"Bearer {api_key}"
        else:
            params["api_key"] = api_key
        resp = http.get(TMDB_SEARCH, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        results = resp.json().get("results") or []
        if year:   # prefer an exact release-year match; TMDB's `year` also matches re-releases
            exact = [r for r in results if str(r.get("release_date", ""))[:4] == str(year)]
            results = exact or results
        return int(results[0]["id"]) if results else None

    return search


def known_tmdb_ids(path: str) -> dict[str, int]:
    """film_key → tmdb_id from the RSS table, if the warehouse has it."""
    import duckdb
    if not Path(path).exists():
        return {}
    try:
        with duckdb.connect(path, read_only=True) as con:
            found = con.execute("""
                select film_title, film_year, min(tmdb_id)
                from letterboxd.diary_entries
                where tmdb_id is not null
                group by 1, 2
            """).fetchall()
    except duckdb.Error:
        return {}
    return {film_key(t, y): int(i) for t, y, i in found}


def resolve_tmdb_ids(rows: list[dict], known: dict[str, int], cache: TmdbCache,
                     search: Callable[[str, int | None], int | None] | None) -> dict[str, int]:
    """Fill rows' tmdb_id in place. Returns counts by how each film was resolved."""
    counts = {"rss": 0, "cache": 0, "search": 0, "unresolved": 0}
    seen: dict[str, int | None] = {}
    for row in rows:
        key = film_key(row["film_title"], row["film_year"])
        if key not in seen:
            if key in known:
                seen[key], how = known[key], "rss"
            elif key in cache:
                seen[key], how = cache.get(key), "cache"
            elif search is not None:
                seen[key] = search(row["film_title"], row["film_year"])
                cache.set(key, seen[key])
                how = "search"
            else:
                seen[key], how = None, "unresolved"
            counts["unresolved" if seen[key] is None else how] += 1
        row["tmdb_id"] = seen[key]
    return counts


# ── load ─────────────────────────────────────────────────────────────────────

@dlt.resource(
    name="csv_diary",
    write_disposition="merge",
    primary_key="entry_id",
    columns={
        "entry_id":       {"data_type": "text"},
        "film_title":     {"data_type": "text"},
        "film_year":      {"data_type": "bigint"},
        "tmdb_id":        {"data_type": "bigint"},
        "watched_date":   {"data_type": "text"},
        "logged_date":    {"data_type": "text"},
        "rating":         {"data_type": "double"},
        "is_rewatch":     {"data_type": "bool"},
        "tags":           {"data_type": "text"},
        "letterboxd_uri": {"data_type": "text"},
        "ingested_at":    {"data_type": "text"},
    },
)
def csv_diary(rows: list[dict]):
    yield from rows


def load(rows: list[dict], destination_path: str | None = None, pipelines_dir: str | None = None):
    pipeline = dlt.pipeline(
        pipeline_name="letterboxd_csv",
        destination=dlt.destinations.duckdb(destination_path or db_path()),
        dataset_name="letterboxd",
        pipelines_dir=pipelines_dir,
    )
    return pipeline.run(csv_diary(rows))


def main() -> int:
    p = argparse.ArgumentParser(description="Backfill the Letterboxd diary from the data export's diary.csv.")
    p.add_argument("--file", required=True, type=Path, help="path to diary.csv")
    p.add_argument("--dry-run", action="store_true", help="parse and report; no writes, no TMDB calls")
    args = p.parse_args()

    path = args.file.expanduser()
    if not path.exists():
        print(f"❌ {path} not found")
        return 1
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = parse_csv(f)
    films = {film_key(r["film_title"], r["film_year"]) for r in rows}
    print(f"Letterboxd CSV: {len(rows)} diary entries, {len(films)} films")

    known = known_tmdb_ids(db_path())
    cache = TmdbCache(data_dir() / "film" / "tmdb_search_cache.json")
    api_key = os.getenv("TMDB_API_KEY", "").strip()

    if args.dry_run:
        need = {k for k in films if k not in known and k not in cache}
        print(f"[dry-run] TMDB ids: {len(films) - len(need)} films known (RSS or cache), "
              f"{len(need)} would be {'searched' if api_key else 'left null (no TMDB_API_KEY)'}")
        print("[dry-run] Would merge into letterboxd.csv_diary")
        for r in rows[-5:]:
            print(f"  {r['watched_date']}  {r['rating']}  {'↻ ' if r['is_rewatch'] else ''}{r['film_title']} ({r['film_year']})")
        return 0

    search = tmdb_search(api_key) if api_key else None
    try:
        counts = resolve_tmdb_ids(rows, known, cache, search)
    finally:
        cache.save()   # keep whatever was looked up, even if a search failed partway
    print(f"  TMDB ids by film: {counts}")

    print(f"✅ Loaded: {load(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
