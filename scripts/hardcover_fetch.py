#!/usr/bin/env python3
import argparse
import csv
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

DEFAULT_API_URL = "https://api.hardcover.app/v1/graphql"

ME_QUERY = """
query Me {
  me {
    id
    username
  }
}
"""

# status_id 3 = Read (per Hardcover Books schema)
# Pulls updated_at as our "marked read" timestamp (good enough for year-based tracking)
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
      tags
      contributions {
        author { name }
      }
    }
  }
}
"""


def hc_post(api_url: str, token: str, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    headers = {
        "authorization": token,  # Hardcover docs use lowercase 'authorization'
        "content-type": "application/json",
        "user-agent": "life-os-2026 (personal goal tracking script)",
    }   
    payload = {
        "query": query,
        "variables": variables or {},
    }
    resp = requests.post(api_url, headers=headers, json=payload, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Hardcover API HTTP {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(
            f"Hardcover API GraphQL errors: {json.dumps(data['errors'], indent=2)[:1000]}"
        )
    return data["data"]

def classify_from_tags(tags) -> str:
    """
    Heuristic:
    - Nonfiction if tags contain 'nonfiction' (case-insensitive)
    - Fiction if tags contain 'fiction' (case-insensitive)
    - Otherwise unknown (we'll refine once we confirm schema fields)
    """
    if not tags:
        return "unknown"
    lowered = [str(t).lower() for t in tags]
    if any("nonfiction" in t for t in lowered):
        return "nonfiction"
    if any("fiction" in t for t in lowered):
        return "fiction"
    return "unknown"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    token = os.getenv("HARDCOVER_TOKEN")
    api_url = os.getenv("HARDCOVER_API_URL", DEFAULT_API_URL)

    if not token:
        print("Missing HARDCOVER_TOKEN. Add it to your .env file.", file=sys.stderr)
        sys.exit(1)

    me_resp = hc_post(api_url, token, ME_QUERY)["me"]

    # Hardcover sometimes returns `me` as an object or a single-item list
    if isinstance(me_resp, list):
        if not me_resp:
            raise RuntimeError("Hardcover `me` query returned an empty list")
        me = me_resp[0]
    elif isinstance(me_resp, dict):
        me = me_resp
    else:
        raise RuntimeError(f"Unexpected Hardcover `me` response type: {type(me_resp)}")

    user_id = int(me["id"])
   

    all_rows: List[Dict[str, Any]] = []
    offset = 0
    limit = args.limit

    while True:
        page = hc_post(api_url, token, USER_BOOKS_READ_QUERY, {"user_id": user_id, "limit": limit, "offset": offset})
        rows = page.get("user_books", [])
        if not rows:
            break
        all_rows.extend(rows)
        offset += limit

    os.makedirs("data/hardcover/raw", exist_ok=True)
    os.makedirs("data/hardcover/processed", exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d")
    raw_path = f"data/hardcover/raw/user_books_read_{ts}.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump({"me": me, "user_books": all_rows}, f, ensure_ascii=False, indent=2)

    csv_path = "data/hardcover/processed/books_read_clean.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
        "marked_read_at",
        "book_id",
        "title",
        "authors",
        "tags",
        "classification",
    ])
        for ub in all_rows:
            book = ub.get("book") or {}
            authors = []
            for c in (book.get("contributions") or []):
                a = (c.get("author") or {}).get("name")
                if a:
                    authors.append(a)
            tags = book.get("tags") or []
            classification = classify_from_tags(tags)
            w.writerow([
                ub.get("updated_at") or "",
                book.get("id") or "",
                book.get("title") or "",
                "; ".join(authors),
                "; ".join(tags) if isinstance(tags, list) else str(tags),
                classification,
            ])

    print(f"User: {me.get('username')} (id={user_id})")
    print(f"Fetched read books: {len(all_rows)}")
    print(f"Wrote raw: {raw_path}")
    print(f"Wrote clean: {csv_path}")

if __name__ == "__main__":
    main()

