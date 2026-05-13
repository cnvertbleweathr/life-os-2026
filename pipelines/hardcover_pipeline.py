#!/usr/bin/env python3
"""
Hardcover DLT pipeline.

Replaces scripts/hardcover_fetch.py + scripts/hardcover_metrics.py.
Loads books directly into DuckDB via DLT.

Tables produced (schema: hardcover):
  hardcover.books_read     — one row per book, merged on book_id
  hardcover.reading_summary — one row per year

Usage:
  python pipelines/hardcover_pipeline.py
  python pipelines/hardcover_pipeline.py --year 2026
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import requests
import dlt
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DB_PATH = str(ROOT / "data" / "warehouse" / "lifeos.duckdb")
DEFAULT_API_URL = "https://api.hardcover.app/v1/graphql"

ME_QUERY = """
query Me {
  me { id username }
}
"""

USER_BOOKS_READ_QUERY = """
query UserBooksRead($user_id: Int!, $limit: Int!, $offset: Int!) {
  user_books(
    where: { user_id: { _eq: $user_id }, status_id: { _eq: 3 } }
    limit: $limit
    offset: $offset
    order_by: { updated_at: desc }
  ) {
    id
    updated_at
    book {
      id
      title
      cached_tags
      contributions { author { name } }
    }
  }
}
"""


# ---------------------------------------------------------------------------
# Helpers (ported from hardcover_fetch.py)
# ---------------------------------------------------------------------------

def _hc_post(token: str, query: str, variables: Optional[Dict] = None) -> Dict:
    api_url = os.getenv("HARDCOVER_API_URL", DEFAULT_API_URL)
    resp = requests.post(
        api_url,
        headers={
            "authorization": token,
            "content-type": "application/json",
            "user-agent": "life-os-2026 (personal goal tracking)",
        },
        json={"query": query, "variables": variables or {}},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"Hardcover GraphQL error: {data['errors']}")
    return data["data"]


def _normalize_tags(val: Any) -> List[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            pass
        return [p.strip() for p in s.split(",") if p.strip()]
    return [str(val).strip()] if str(val).strip() else []


def _classify(tags: List[str]) -> str:
    lowered = [t.lower() for t in tags]
    if any("nonfiction" in t for t in lowered):
        return "nonfiction"
    if any("fiction" in t for t in lowered):
        return "fiction"
    return "unknown"


# ---------------------------------------------------------------------------
# DLT resources
# ---------------------------------------------------------------------------

@dlt.resource(
    name="books_read",
    write_disposition="merge",
    primary_key="book_id",
)
def hardcover_books_resource() -> Iterator[dict]:
    token = os.getenv("HARDCOVER_TOKEN")
    if not token:
        raise RuntimeError("Missing HARDCOVER_TOKEN in .env")

    # Get user ID
    me_raw = _hc_post(token, ME_QUERY)["me"]
    me = me_raw[0] if isinstance(me_raw, list) else me_raw
    user_id = int(me["id"])

    offset, limit = 0, 50
    while True:
        page = _hc_post(
            token,
            USER_BOOKS_READ_QUERY,
            {"user_id": user_id, "limit": limit, "offset": offset},
        )
        rows = page.get("user_books", [])
        if not rows:
            break

        for ub in rows:
            book = ub.get("book") or {}
            authors = [
                c["author"]["name"]
                for c in (book.get("contributions") or [])
                if c.get("author", {}).get("name")
            ]
            tags = _normalize_tags(book.get("cached_tags"))
            classification = _classify(tags)

            marked_read_at = ub.get("updated_at") or ""
            year = None
            if marked_read_at:
                try:
                    year = datetime.fromisoformat(
                        marked_read_at.replace("Z", "+00:00")
                    ).year
                except ValueError:
                    pass

            yield {
                "book_id": book.get("id"),
                "title": book.get("title") or "",
                "authors": "; ".join(authors),
                "cached_tags": "; ".join(tags),
                "classification": classification,
                "marked_read_at": marked_read_at,
                "year": year,
            }

        offset += limit


@dlt.resource(
    name="reading_summary",
    write_disposition="replace",
)
def reading_summary_resource(year: int) -> Iterator[dict]:
    """Reads from the DuckDB books_read table and produces a year summary."""
    import duckdb
    import yaml

    db_path = ROOT / "data" / "warehouse" / "lifeos.duckdb"
    if not db_path.exists():
        return

    goals_path = ROOT / "goals" / "2026.yaml"
    goals = yaml.safe_load(goals_path.read_text()) if goals_path.exists() else {}
    domains = goals.get("domains", {})

    nonfiction_goal = domains.get("professional", {}).get("outcomes", {}).get("nonfiction_books_goal", 0)
    fiction_goal = domains.get("personal", {}).get("outcomes", {}).get("fiction_books_goal", 0)

    try:
        con = duckdb.connect(str(db_path), read_only=True)
        df = con.execute(
            "SELECT classification FROM hardcover.books_read WHERE year = ?",
            [year],
        ).df()
        con.close()
    except Exception:
        return

    fiction = int((df["classification"] == "fiction").sum())
    nonfiction = int((df["classification"] == "nonfiction").sum())
    unknown = int((df["classification"] == "unknown").sum())
    total = len(df)

    yield {
        "year": year,
        "fiction_read": fiction,
        "fiction_goal": fiction_goal,
        "fiction_progress_pct": round((fiction / fiction_goal) * 100, 2) if fiction_goal else 0.0,
        "nonfiction_read": nonfiction,
        "nonfiction_goal": nonfiction_goal,
        "nonfiction_progress_pct": round((nonfiction / nonfiction_goal) * 100, 2) if nonfiction_goal else 0.0,
        "unknown_classification": unknown,
        "total_read": total,
    }


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run(year: int) -> None:
    pipeline = dlt.pipeline(
        pipeline_name="hardcover",
        destination=dlt.destinations.duckdb(DB_PATH),
        dataset_name="hardcover",
    )

    print("Fetching Hardcover books...")
    load_info = pipeline.run([hardcover_books_resource()])
    print(load_info)

    print("Computing reading summary...")
    load_info = pipeline.run([reading_summary_resource(year=year)])
    print(load_info)


def main() -> None:
    p = argparse.ArgumentParser(description="Load Hardcover books into DuckDB via DLT.")
    p.add_argument("--year", type=int, default=datetime.now().year)
    args = p.parse_args()
    run(args.year)


if __name__ == "__main__":
    main()
