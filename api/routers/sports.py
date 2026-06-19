"""
/api/sports — live streams, team news, sports headlines.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter

router       = APIRouter()
ROOT         = Path(__file__).resolve().parents[2]
STREAMS_PATH = ROOT / "data" / "streams" / "today.json"


@router.get("/streams")
async def streams():
    """Today's sports streams from streamed.pk."""
    if not STREAMS_PATH.exists():
        return {"my_teams": [], "top5": [], "popular": [], "fetched_at": None}
    try:
        return json.loads(STREAMS_PATH.read_text())
    except Exception:
        return {"my_teams": [], "top5": [], "popular": [], "fetched_at": None}


@router.get("/news")
async def sports_news(q: str = "NFL OR NBA OR CFB OR college football OR MLB"):
    """Sports news via NewsAPI."""
    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        return []
    import httpx
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q":        q,
                    "language": "en",
                    "sortBy":   "publishedAt",
                    "pageSize": 10,
                    "apiKey":   api_key,
                }
            )
            if r.status_code == 200:
                articles = r.json().get("articles", [])
                return [
                    {
                        "title":     a.get("title"),
                        "source":    a.get("source", {}).get("name"),
                        "url":       a.get("url"),
                        "published": a.get("publishedAt"),
                    }
                    for a in articles if a.get("title")
                ]
    except Exception:
        pass
    return []
