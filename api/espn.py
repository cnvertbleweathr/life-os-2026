"""
api/espn.py — thin async client for ESPN's public (unofficial) site API.

Replaces streamed.pk (dead as of 2026-10). Used by /api/sports for:
  - today's scoreboards across the leagues we care about (live scores)
  - next scheduled game for each of MY_TEAMS
  - team news

ESPN publishes no rate limit, so everything goes through a small in-process
TTL cache: a page load costs a handful of requests at most, and repeat loads
inside the TTL cost none. No keys, no auth.

Deliberately NOT used from ESPN: odds and anything predictive (FPI, predictor,
win probability). CFB lines/ratings stay on CFBD.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

SITE = "https://site.api.espn.com/apis/site/v2/sports"
UA = {"User-Agent": "ons/1.0 (personal dashboard)"}

# league key -> (ESPN path, display label, base prominence weight)
LEAGUES: dict[str, tuple[str, str, int]] = {
    "nfl": ("football/nfl", "NFL", 30),
    "cfb": ("football/college-football", "CFB", 20),
    "nba": ("basketball/nba", "NBA", 20),
    "mlb": ("baseball/mlb", "MLB", 15),
    "nhl": ("hockey/nhl", "NHL", 12),
    "mls": ("soccer/usa.1", "MLS", 8),
}


@dataclass(frozen=True)
class MyTeam:
    league: str
    name: str  # must match ESPN displayName (case-insensitive)


MY_TEAMS: list[MyTeam] = [
    MyTeam("nba", "Orlando Magic"),
    MyTeam("nfl", "Tampa Bay Buccaneers"),
    MyTeam("mls", "Orlando City SC"),
    MyTeam("mlb", "Miami Marlins"),
    MyTeam("nhl", "Florida Panthers"),
    MyTeam("nhl", "Colorado Avalanche"),
    MyTeam("nba", "Denver Nuggets"),
    MyTeam("mlb", "Colorado Rockies"),
]

# ── TTL cache ────────────────────────────────────────────────────────────────

_cache: dict[str, tuple[float, Any]] = {}


async def get_json(client: httpx.AsyncClient, url: str, params: dict | None, ttl: int) -> Any:
    key = url + "?" + "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    r = await client.get(url, params=params, headers=UA, timeout=10)
    r.raise_for_status()
    data = r.json()
    _cache[key] = (time.monotonic() + ttl, data)
    return data


def clear_cache() -> None:
    _cache.clear()


# ── Normalisers ──────────────────────────────────────────────────────────────

def _logo(team: dict) -> str | None:
    if team.get("logo"):
        return team["logo"]
    logos = team.get("logos") or []
    return logos[0].get("href") if logos else None


def _side(comp: dict) -> dict:
    team = comp.get("team") or {}
    score = comp.get("score")
    if isinstance(score, dict):  # schedule endpoint wraps score
        score = score.get("displayValue")
    records = comp.get("records") or comp.get("record") or []
    record = records[0].get("summary") if records and isinstance(records, list) else None
    rank = (comp.get("curatedRank") or {}).get("current")
    return {
        "id": str(team.get("id", "")),
        "name": team.get("displayName") or team.get("name") or "",
        "short": team.get("shortDisplayName") or team.get("name") or "",
        "abbr": team.get("abbreviation") or "",
        "logo": _logo(team),
        "score": score if score not in ("", None) else None,
        "record": record,
        "rank": rank if rank and rank <= 25 else None,
        "winner": comp.get("winner"),
    }


def _broadcasts(comp: dict) -> tuple[list[str], bool]:
    names: list[str] = []
    national = False
    for b in comp.get("broadcasts") or []:
        if b.get("market") == "national":
            national = True
        for n in b.get("names") or []:
            if n and n not in names:
                names.append(n)
    for g in comp.get("geoBroadcasts") or []:
        n = (g.get("media") or {}).get("shortName")
        if (g.get("market") or {}).get("type") == "National":
            national = True
        if n and n not in names:
            names.append(n)
    return names, national


def _link(event: dict) -> str | None:
    for l in event.get("links") or []:
        rel = l.get("rel") or []
        if "summary" in rel or "gamecast" in rel:
            return l.get("href")
    links = event.get("links") or []
    return links[0].get("href") if links else None


def normalize_event(event: dict, league: str) -> dict | None:
    comps = event.get("competitions") or []
    if not comps:
        return None
    comp = comps[0]
    sides = {c.get("homeAway"): _side(c) for c in comp.get("competitors") or []}
    if "home" not in sides or "away" not in sides:
        return None
    status = (comp.get("status") or event.get("status") or {}).get("type") or {}
    state = status.get("state", "pre")
    broadcasts, national = _broadcasts(comp)
    notes = comp.get("notes") or []
    season_type = (event.get("season") or {}).get("type") or (event.get("seasonType") or {}).get("type")
    _, label, _ = LEAGUES[league]
    return {
        "id": str(event.get("id", "")),
        "league": league,
        "league_label": label,
        "name": event.get("name") or f"{sides['away']['name']} at {sides['home']['name']}",
        "short_name": event.get("shortName") or f"{sides['away']['abbr']} @ {sides['home']['abbr']}",
        "start_utc": event.get("date") or comp.get("date"),
        "state": state,  # pre | in | post
        "status_detail": status.get("shortDetail") or status.get("detail") or "",
        "is_live": state == "in",
        "home": sides["home"],
        "away": sides["away"],
        "broadcasts": broadcasts,
        "national_tv": national,
        "note": notes[0].get("headline") if notes else None,
        "postseason": str(season_type) == "3",
        "venue": (comp.get("venue") or {}).get("fullName"),
        "link": _link(event),
        "my_team": None,
    }


def prominence(g: dict) -> int:
    """Heuristic 'biggest games today' score — replaces the GPT top-5 pick."""
    s = LEAGUES[g["league"]][2]
    if g["postseason"]:
        s += 50
    if g["national_tv"]:
        s += 20
    if g["note"]:
        s += 10
    for side in ("home", "away"):
        r = g[side]["rank"]
        if r:
            s += 26 - r
    return s


# ── Team id resolution ───────────────────────────────────────────────────────

async def resolve_team_ids(client: httpx.AsyncClient) -> tuple[dict[MyTeam, dict], list[str]]:
    """MyTeam -> {id, logo, abbr, name} using each league's /teams listing (cached 24h)."""
    out: dict[MyTeam, dict] = {}
    errors: list[str] = []
    leagues = sorted({t.league for t in MY_TEAMS})

    async def one(league: str):
        path = LEAGUES[league][0]
        return league, await get_json(client, f"{SITE}/{path}/teams", {"limit": 500}, ttl=86400)

    results = await asyncio.gather(*(one(l) for l in leagues), return_exceptions=True)
    for res in results:
        if isinstance(res, Exception):
            errors.append(f"teams: {res}")
            continue
        league, data = res
        teams = [
            t.get("team", {})
            for s in data.get("sports", [])
            for lg in s.get("leagues", [])
            for t in lg.get("teams", [])
        ]
        for mt in (t for t in MY_TEAMS if t.league == league):
            match = next((t for t in teams if (t.get("displayName") or "").lower() == mt.name.lower()), None)
            if match is None:  # tolerate small naming drift ("Orlando City" vs "Orlando City SC")
                match = next((t for t in teams if mt.name.lower() in (t.get("displayName") or "").lower()
                              or (t.get("displayName") or "").lower() in mt.name.lower()), None)
            if match:
                out[mt] = {"id": str(match["id"]), "name": match.get("displayName"),
                           "short": match.get("shortDisplayName") or match.get("name"),
                           "abbr": match.get("abbreviation"), "logo": _logo(match)}
            else:
                errors.append(f"{mt.name}: not found in ESPN {league} teams")
    return out, errors


# ── Public API ───────────────────────────────────────────────────────────────

async def scoreboards(client: httpx.AsyncClient, day: date, ttl: int = 60) -> tuple[list[dict], list[str]]:
    errors: list[str] = []

    async def one(league: str):
        path = LEAGUES[league][0]
        params: dict[str, Any] = {"dates": day.strftime("%Y%m%d"), "limit": 300}
        if league == "cfb":
            params["groups"] = 80  # all FBS, not just the default Top 25 view
        return league, await get_json(client, f"{SITE}/{path}/scoreboard", params, ttl=ttl)

    games: list[dict] = []
    for res in await asyncio.gather(*(one(l) for l in LEAGUES), return_exceptions=True):
        if isinstance(res, Exception):
            errors.append(f"scoreboard: {res}")
            continue
        league, data = res
        for ev in data.get("events") or []:
            g = normalize_event(ev, league)
            if g:
                games.append(g)
    return games, errors


async def next_games(client: httpx.AsyncClient, ids: dict[MyTeam, dict], now: datetime) -> tuple[list[dict], list[str]]:
    """Next not-yet-finished game for each of my teams (regular season, then postseason)."""
    errors: list[str] = []

    async def one(mt: MyTeam, info: dict):
        path = LEAGUES[mt.league][0]
        url = f"{SITE}/{path}/teams/{info['id']}/schedule"
        found: list[dict] = []
        for params in ({}, {"seasontype": 3}):
            try:
                data = await get_json(client, url, params or None, ttl=3600)
            except Exception as e:  # postseason call 404s for some leagues — fine
                if not params:
                    raise e
                continue
            for ev in data.get("events") or []:
                g = normalize_event(ev, mt.league)
                if not g or g["state"] == "post" or not g["start_utc"]:
                    continue
                if _parse(g["start_utc"]) < now - timedelta(hours=6):
                    continue
                found.append(g)
            if found:
                break
        found.sort(key=lambda g: g["start_utc"])
        if found:
            found[0]["my_team"] = mt.name
            return found[0]
        return None

    by_id: dict[str, dict] = {}
    for mt, res in zip(ids, await asyncio.gather(*(one(mt, i) for mt, i in ids.items()), return_exceptions=True)):
        if isinstance(res, Exception):
            errors.append(f"{mt.name} schedule: {res}")
        elif res:
            if res["id"] in by_id:  # two of my teams playing each other (Avs vs Panthers)
                by_id[res["id"]]["my_team"] += f" / {res['my_team']}"
            else:
                by_id[res["id"]] = res
    out = sorted(by_id.values(), key=lambda g: g["start_utc"])
    return out, errors


async def team_news(client: httpx.AsyncClient, ids: dict[MyTeam, dict], limit: int = 6) -> tuple[list[dict], list[str]]:
    errors: list[str] = []

    async def one(mt: MyTeam, info: dict):
        path = LEAGUES[mt.league][0]
        data = await get_json(client, f"{SITE}/{path}/news", {"team": info["id"], "limit": 25}, ttl=900)
        arts = data.get("articles") or []
        tagged = [a for a in arts if any(str(c.get("teamId") or (c.get("team") or {}).get("id")) == info["id"]
                                         for c in a.get("categories") or [])]
        # If ESPN honoured ?team= the articles may carry no team categories; only
        # fall back to the raw list when *nothing* carries category data.
        has_cats = any(a.get("categories") for a in arts)
        chosen = tagged if has_cats else arts
        items = []
        for a in chosen[:limit]:
            url = ((a.get("links") or {}).get("web") or {}).get("href")
            if not a.get("headline") or not url:
                continue
            imgs = a.get("images") or []
            items.append({
                "title": a["headline"],
                "description": a.get("description"),
                "url": url,
                "published": a.get("published") or a.get("lastModified"),
                "image": imgs[0].get("url") if imgs else None,
                "source": "ESPN",
                "team": mt.name,
                "team_abbr": info.get("abbr"),
                "team_logo": info.get("logo"),
                "league": mt.league,
            })
        return items

    merged: dict[str, dict] = {}
    for mt, res in zip(ids, await asyncio.gather(*(one(mt, i) for mt, i in ids.items()), return_exceptions=True)):
        if isinstance(res, Exception):
            errors.append(f"{mt.name} news: {res}")
            continue
        for a in res:
            merged.setdefault(a["url"], a)
    articles = sorted(merged.values(), key=lambda a: a.get("published") or "", reverse=True)
    return articles, errors


def _parse(ts: str) -> datetime:
    # ESPN uses minute precision ("2026-10-28T01:00Z"); 3.11+ fromisoformat handles it.
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def tag_my_teams(games: list[dict], ids: dict[MyTeam, dict]) -> None:
    by_id = {(mt.league, info["id"]): mt.name for mt, info in ids.items()}
    for g in games:
        names = [by_id[k] for side in ("away", "home") if (k := (g["league"], g[side]["id"])) in by_id]
        g["my_team"] = " / ".join(names) or None
