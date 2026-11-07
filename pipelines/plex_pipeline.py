#!/usr/bin/env python3
"""
pipelines/plex_pipeline.py: films watched on the Plex server, from its watch history.

Polls the server (no webhooks, so no Plex Pass needed):
  GET /status/sessions/history/all     watch history, newest first, paged
  GET /library/metadata/{ratingKey}    per film, for its tmdb:// GUID

Only movies are kept. Each history row is resolved to a TMDB id, the key that
mart_film_watches joins on with Letterboxd. A film deleted from the library
since it was watched has no metadata any more; it is still loaded, with
tmdb_id NULL.

Usage:
  python pipelines/plex_pipeline.py
  python pipelines/plex_pipeline.py --dry-run     # fetch and print, write nothing
  python pipelines/plex_pipeline.py --full        # ignore the cursor, re-read all history

Tables created in DuckDB (schema: plex):
  plex.history   one row per movie play, merged on history_key

Config (.env):
  PLEX_URL         e.g. http://127.0.0.1:32400
  PLEX_TOKEN       X-Plex-Token
  PLEX_ACCOUNT_ID  whose plays to keep: 1 (the server owner, default) or "all"

Without PLEX_URL and PLEX_TOKEN the pipeline prints a notice and exits 0, so
the daily sync carries on; stg_plex__history is then empty.
"""
from __future__ import annotations

import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

import dlt
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

LOCAL_TZ = ZoneInfo("America/Denver")   # watch dates are the user's local day, like Letterboxd's
PAGE_SIZE = 200


def db_path() -> str:
    return os.getenv("ONS_DUCKDB_PATH", str(ROOT / "data" / "warehouse" / "ons.duckdb"))


class PlexClient:
    def __init__(self, base_url: str, token: str, session: requests.Session | None = None):
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.session.headers.update({
            "X-Plex-Token": token,
            "Accept": "application/json",
            "X-Plex-Product": "ONS",
            "X-Plex-Client-Identifier": "ons-plex-pipeline",
        })

    def get(self, path: str, params: dict | None = None) -> dict:
        resp = self.session.get(f"{self.base_url}{path}", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json().get("MediaContainer", {})

    def history(self, account_id: str | None, since: int = 0) -> Iterator[dict]:
        """Every history row with viewedAt >= since, newest first."""
        start = 0
        while True:
            params = {
                "sort": "viewedAt:desc",
                "X-Plex-Container-Start": start,
                "X-Plex-Container-Size": PAGE_SIZE,
            }
            if account_id:
                params["accountID"] = account_id
            page = self.get("/status/sessions/history/all", params).get("Metadata") or []
            for row in page:
                if int(row.get("viewedAt") or 0) < since:
                    return
                yield row
            if len(page) < PAGE_SIZE:
                return
            start += PAGE_SIZE

    def metadata(self, rating_key: str) -> dict | None:
        try:
            items = self.get(f"/library/metadata/{rating_key}", {"includeGuids": 1}).get("Metadata") or []
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None   # removed from the library since it was watched
            raise
        return items[0] if items else None


def tmdb_id_from_guids(meta: dict | None) -> int | None:
    """Pull the TMDB id out of a metadata item's Guid list (`tmdb://12345`).

    Older agents put it in the main `guid` instead
    (`com.plexapp.agents.themoviedb://12345?lang=en`); that is checked too."""
    if not meta:
        return None
    for g in meta.get("Guid") or []:
        gid = str(g.get("id", ""))
        if gid.startswith("tmdb://"):
            try:
                return int(gid.removeprefix("tmdb://"))
            except ValueError:
                return None
    legacy = re.match(r"com\.plexapp\.agents\.themoviedb://(\d+)", str(meta.get("guid", "")))
    return int(legacy.group(1)) if legacy else None


def imdb_id_from_guids(meta: dict | None) -> str | None:
    for g in (meta or {}).get("Guid") or []:
        gid = str(g.get("id", ""))
        if gid.startswith("imdb://"):
            return gid.removeprefix("imdb://")
    return None


def _str_or_none(value) -> str | None:
    return None if value is None else str(value)


def to_row(item: dict, meta: dict | None) -> dict:
    """One history item (+ its library metadata, if still there) → one plex.history row."""
    viewed_at = int(item.get("viewedAt") or 0)
    viewed_utc = datetime.fromtimestamp(viewed_at, tz=timezone.utc)
    media = ((meta or {}).get("Media") or [{}])[0]
    part = (media.get("Part") or [{}])[0]
    year = (meta or {}).get("year") or item.get("year")
    if not year and item.get("originallyAvailableAt"):
        year = str(item["originallyAvailableAt"])[:4]
    return {
        "history_key":   str(item.get("historyKey") or f"{item.get('ratingKey')}_{viewed_at}"),
        "rating_key":    str(item.get("ratingKey") or ""),
        "title":         (meta or {}).get("title") or item.get("title"),
        "film_year":     int(year) if year else None,
        "tmdb_id":       tmdb_id_from_guids(meta),
        "imdb_id":       imdb_id_from_guids(meta),
        "viewed_at":     viewed_at,
        "viewed_at_utc": viewed_utc.isoformat(),
        "watched_date":  viewed_utc.astimezone(LOCAL_TZ).date().isoformat(),
        "account_id":    _str_or_none(item.get("accountID")),
        "device_id":     _str_or_none(item.get("deviceID")),
        "library_section_id": _str_or_none(item.get("librarySectionID")),
        "duration_ms":   (meta or {}).get("duration"),
        "file_path":     part.get("file"),   # the renderer's plex_clip mode needs this later
        "in_library":    meta is not None,
        "ingested_at":   datetime.now(timezone.utc).isoformat(),
    }


def movie_rows(client: PlexClient, account_id: str | None, since: int) -> Iterator[dict]:
    cache: dict[str, dict | None] = {}
    for item in client.history(account_id, since):
        if item.get("type") != "movie":
            continue
        key = str(item.get("ratingKey") or "")
        if key and key not in cache:
            cache[key] = client.metadata(key)
        yield to_row(item, cache.get(key))


def plex_history_resource(client: PlexClient, account_id: str | None, full: bool):
    @dlt.resource(
        name="history",
        write_disposition="merge",
        primary_key="history_key",
        # Every column is declared: dlt drops a column that is null in every row of a
        # load, and stg_plex__history selects them all by name.
        columns={
            "history_key":        {"data_type": "text"},
            "rating_key":         {"data_type": "text"},
            "title":              {"data_type": "text"},
            "film_year":          {"data_type": "bigint"},
            "tmdb_id":            {"data_type": "bigint"},
            "imdb_id":            {"data_type": "text"},
            "viewed_at":          {"data_type": "bigint"},
            "viewed_at_utc":      {"data_type": "text"},
            "watched_date":       {"data_type": "text"},
            "account_id":         {"data_type": "text"},
            "device_id":          {"data_type": "text"},
            "library_section_id": {"data_type": "text"},
            "duration_ms":        {"data_type": "bigint"},
            "file_path":          {"data_type": "text"},
            "in_library":         {"data_type": "bool"},
            "ingested_at":        {"data_type": "text"},
        },
    )
    def history(
        viewed_at=dlt.sources.incremental("viewed_at", initial_value=0),
    ) -> Iterator[dict]:
        since = 0 if full else int(viewed_at.last_value or 0)
        yield from movie_rows(client, account_id, since)

    return history


def run(client: PlexClient, account_id: str | None, full: bool = False,
        destination_path: str | None = None, pipelines_dir: str | None = None):
    """Load plex.history.

    full=True re-reads all history. Passing since=0 to the generator isn't enough:
    dlt's incremental still drops rows older than its stored last_value. So a full
    run uses refresh="drop_resources", which drops plex.history and the resource's
    state (the cursor) before loading, and every play is reloaded."""
    pipeline = dlt.pipeline(
        pipeline_name="plex",
        destination=dlt.destinations.duckdb(destination_path or db_path()),
        dataset_name="plex",
        pipelines_dir=pipelines_dir,
    )
    return pipeline.run(
        plex_history_resource(client, account_id, full)(),
        refresh="drop_resources" if full else None,
    )


def _account_id() -> str | None:
    raw = os.getenv("PLEX_ACCOUNT_ID", "1").strip()
    return None if raw.lower() in ("", "all") else raw


def main() -> int:
    p = argparse.ArgumentParser(description="Load Plex movie watch history into DuckDB.")
    p.add_argument("--dry-run", action="store_true", help="fetch and print; write nothing")
    p.add_argument("--full", action="store_true", help="drop plex.history and its cursor, then reload all history")
    args = p.parse_args()

    url, token = os.getenv("PLEX_URL", "").strip(), os.getenv("PLEX_TOKEN", "").strip()
    if not url or not token:
        print("Plex pipeline: PLEX_URL / PLEX_TOKEN not set in .env; skipping.")
        return 0

    client = PlexClient(url, token)
    account_id = _account_id()
    print(f"Plex pipeline: {url} (account {account_id or 'all'})")

    if args.dry_run:
        rows = list(movie_rows(client, account_id, since=0))
        print(f"[dry-run] {len(rows)} movie plays; would merge into plex.history")
        for r in rows[:10]:
            print(f"  {r['watched_date']}  tmdb={r['tmdb_id']}  {r['title']} ({r['film_year']})")
        return 0

    load_info = run(client, account_id, full=args.full)
    print(f"✅ Loaded: {load_info}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
