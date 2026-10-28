"""
/api/sports — scores, schedules and team news via ESPN; generic headlines via NewsAPI.

streamed.pk died 2026-10; ESPN's public site API replaced it. Watch links are
gone until a real free stream source exists — games link to ESPN Gamecast.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter

from api import espn
from api.store import today_local

router = APIRouter()


@router.get("/today")
async def today():
    """Today's games across NFL/CFB/NBA/MLB/NHL/MLS, my teams' games, next games, top games."""
    now = datetime.now(timezone.utc)
    async with httpx.AsyncClient() as client:
        ids, id_errors = await espn.resolve_team_ids(client)
        games, sb_errors = await espn.scoreboards(client, today_local())
        espn.tag_my_teams(games, ids)
        upcoming, sched_errors = await espn.next_games(client, ids, now)

    games.sort(key=lambda g: (0 if g["is_live"] else 1 if g["state"] == "pre" else 2, g["start_utc"] or ""))
    mine = [g for g in games if g["my_team"]]
    mine_ids = {g["id"] for g in mine}
    top = sorted(games, key=espn.prominence, reverse=True)[:5]

    return {
        "fetched_at": now.isoformat(),
        "date": today_local().isoformat(),
        "any_live": any(g["is_live"] for g in games),
        "my_teams": mine,
        "upcoming": [g for g in upcoming if g["id"] not in mine_ids],
        "top": top,
        "all": games,
        "errors": id_errors + sb_errors + sched_errors,
    }


@router.get("/ticker")
async def ticker(headlines: int = 8, news: int = 8):
    """
    Everything the site-wide top ticker scrolls, in one request:
      games     — my teams: live now, later today, finals from the last ~30h,
                  then each other team's next game within a week
      team_news — ESPN news for MY_TEAMS from the last 72h, max 2 per team
      headlines — top US headlines via NewsAPI (empty without NEWS_API_KEY)

    The frontend polls every minute while anything is live, every 5 otherwise.
    ESPN calls ride the shared TTL cache; NewsAPI is cached 30 min so polling
    stays far under the free plan's 100 requests/day.
    """
    now = datetime.now(timezone.utc)
    today = today_local()
    async with httpx.AsyncClient() as client:
        ids, id_errors = await espn.resolve_team_ids(client)
        (games, sb_errors), (prev, prev_errors), (upcoming, sched_errors), \
            (articles, news_errors), (heads, head_errors) = await asyncio.gather(
                espn.scoreboards(client, today),
                espn.scoreboards(client, today - timedelta(days=1), ttl=1800),
                espn.next_games(client, ids, now),
                espn.team_news(client, ids, limit=4),
                _top_headlines(client, headlines),
            )
        espn.tag_my_teams(games, ids)
        espn.tag_my_teams(prev, ids)

    today_mine = [g for g in games if g["my_team"]]
    recent_finals = [
        g for g in prev
        if g["my_team"] and g["state"] == "post" and g["start_utc"]
        and espn._parse(g["start_utc"]) > now - timedelta(hours=30)
    ]
    order = {"in": 0, "pre": 1, "post": 2}
    today_mine.sort(key=lambda g: (order.get(g["state"], 3), g["start_utc"] or ""))
    seen = {g["id"] for g in today_mine} | {g["id"] for g in recent_finals}
    # Teams already playing today don't also need a "next game" item.
    covered = {t for g in today_mine for t in (g["my_team"] or "").split(" / ")}
    next_up = [
        g for g in upcoming
        if g["id"] not in seen and g["start_utc"]
        and espn._parse(g["start_utc"]) < now + timedelta(days=7)
        and not set(g["my_team"].split(" / ")) <= covered
    ]

    live = [g for g in today_mine if g["state"] == "in"]
    later = [g for g in today_mine if g["state"] == "pre"]
    finals = [g for g in today_mine if g["state"] == "post"] + recent_finals

    cutoff = (now - timedelta(hours=72)).isoformat()
    per_team: dict[str, int] = {}
    fresh_news = []
    for a in articles:
        if (a.get("published") or "") < cutoff[:19]:
            continue
        if per_team.get(a["team"], 0) >= 2:
            continue
        per_team[a["team"]] = per_team.get(a["team"], 0) + 1
        fresh_news.append(a)
        if len(fresh_news) >= news:
            break

    return {
        "fetched_at": now.isoformat(),
        "any_live": bool(live),
        "games": [{**g, "ticker_group": grp} for grp, gs in
                  (("live", live), ("today", later), ("final", finals), ("next", next_up)) for g in gs],
        "team_news": fresh_news,
        "headlines": heads,
        "errors": id_errors + sb_errors + prev_errors + sched_errors + news_errors + head_errors,
    }


async def _top_headlines(client: httpx.AsyncClient, limit: int) -> tuple[list[dict], list[str]]:
    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        return [], []
    try:
        data = await espn.get_json(
            client, "https://newsapi.org/v2/top-headlines",
            {"country": "us", "pageSize": 20, "apiKey": api_key}, ttl=1800,
        )
    except Exception as e:
        return [], [f"headlines: {e}"]
    out, titles = [], set()
    for a in data.get("articles") or []:
        title, url = a.get("title"), a.get("url")
        if not title or not url or title == "[Removed]":
            continue
        source = (a.get("source") or {}).get("name") or ""
        # NewsAPI titles end in " - Source"; the ticker shows the source separately.
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]
        if title in titles:
            continue
        titles.add(title)
        out.append({"title": title, "source": source, "url": url, "published": a.get("publishedAt")})
        if len(out) >= limit:
            break
    return out, []


@router.get("/team-news")
async def team_news(team: str | None = None, limit: int = 20):
    """ESPN news for MY_TEAMS, merged and newest first. ?team= filters to one team."""
    async with httpx.AsyncClient() as client:
        ids, id_errors = await espn.resolve_team_ids(client)
        if team:
            ids = {mt: i for mt, i in ids.items() if mt.name.lower() == team.lower()}
        articles, news_errors = await espn.team_news(client, ids)
    return {
        "teams": [{"name": mt.name, "short": i.get("short"), "abbr": i.get("abbr"), "logo": i.get("logo"),
                   "league": mt.league}
                  for mt, i in ids.items()],
        "articles": articles[:limit],
        "errors": id_errors + news_errors,
    }


@router.get("/news")
async def sports_news(q: str = "NFL OR NBA OR CFB OR college football OR MLB"):
    """Generic sports headlines via NewsAPI."""
    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        return []
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
