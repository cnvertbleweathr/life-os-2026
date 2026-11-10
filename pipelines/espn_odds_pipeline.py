#!/usr/bin/env python3
"""
espn_odds_pipeline.py

DLT pipeline for NBA + NHL games and betting lines from ESPN's public
(unofficial, no-auth) APIs. This is the line source for the NBA/NHL ATS
models -- the same feed we'll read live lines from in-season, so the
backtest and the live picks see identical numbers.

Sources
  site.api.espn.com   .../scoreboard?dates=YYYYMMDD     schedule, scores, status
  sports.core.api...  .../events/{id}/competitions/{id}/odds   lines per provider

Odds coverage (probed 2026-11-09; details in docs/NBA_NHL_ATS_DATA.md):
  * Lines start NBA 2013-14 (season 2014), NHL 2019-20 (season 2020).
  * NBA 2014-~2018: offshore books, `current` only; the open is item-level
           initialSpread / initialOverUnder (home-signed).
  * 2019-2023: US books, `current` only (2022-23 ESPN BET `close` is often the
           price misfiled as the line -- nulled by _line/_total).
  * 2023-24: real open / close / current on most books. 2025+: one partner book.
  * NHL "spread" is the puck line (almost always +/-1.5) and is priced at
           varying juice -- ROI must use the actual price, never flat -110.

Tables produced (schema per league: nba / nhl)
  {league}.games  -- one row per game: teams, scores, status, OT, venue
  {league}.odds   -- one row per (game, provider): spread + prices, moneylines,
                     total + prices, open/close snapshots, raw JSON

Raw responses for completed games are cached under data/raw/espn/{league}/
so backfills are resumable and the parser can be re-run without re-fetching.

Usage
  python pipelines/espn_odds_pipeline.py --probe nba --date 2024-01-15
  python pipelines/espn_odds_pipeline.py --league nba --season 2022 --end-season 2026
  python pipelines/espn_odds_pipeline.py --league nhl --season 2022 --end-season 2026
  python pipelines/espn_odds_pipeline.py --daily            # both leagues, last 3 + next 2 days

Season = ESPN season year = the year the season ends (2025-26 -> 2026).
"""

from __future__ import annotations

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")
CACHE = ROOT / "data" / "raw" / "espn"

SITE = "https://site.api.espn.com/apis/site/v2/sports"
CORE = "https://sports.core.api.espn.com/v2/sports"
UA = {"User-Agent": "ons/1.0 (personal analytics)"}
EASTERN = ZoneInfo("America/New_York")  # ESPN's scoreboard ?dates= is the Eastern day

LEAGUES = {
    # key: (sport, league, regulation periods)
    "nba": ("basketball", "nba", 4),
    "nhl": ("hockey", "nhl", 3),
}
SEASON_TYPES = {2, 3}  # 2 = regular, 3 = postseason (1 = preseason, skipped)
WORKERS = 6
_session = requests.Session()
_session.headers.update(UA)


# ---------------------------------------------------------------------------
# HTTP + cache
# ---------------------------------------------------------------------------

def get_json(url: str, params: dict | None = None, retries: int = 4) -> Any:
    for attempt in range(retries):
        try:
            r = _session.get(url, params=params or {}, timeout=30)
            if r.status_code == 404:
                return None
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(3 * (attempt + 1))
    return None


def _cache_path(league: str, kind: str, key: str) -> Path:
    return CACHE / league / kind / f"{key}.json"


def cached_json(league: str, kind: str, key: str, url: str,
                params: dict | None = None, use_cache: bool = True,
                write_cache: bool = True) -> Any:
    p = _cache_path(league, kind, key)
    if use_cache and p.exists():
        return json.loads(p.read_text())
    data = get_json(url, params)
    if write_cache and data is not None:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data))
    return data


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _num(v: Any) -> float | None:
    """'-110' / '+135' / 'EVEN' / -6.5 / 'o215.5' / 'PK' -> float."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().upper()
    if s in ("EVEN", "EV"):
        return 100.0
    if s in ("PK", "PICK", "PICK'EM"):
        return 0.0
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def _price(v: Any) -> float | None:
    """American odds, or None. |odds| < 100 is impossible: ESPN posts a missing moneyline
    as 0, and projection sites (numberfire) put win probabilities in spreadOdds."""
    n = _num(v)
    return n if n is not None and abs(n) >= 100 else None


# Plausible ranges. 2022-23 ESPN snapshots sometimes put the price ("-115") in pointSpread
# and total; anything outside these is a misfiled number, not a line.
LINE_MAX = {"nba": 40.0, "nhl": 4.0}          # |spread| / |puck line|
TOTAL_RANGE = {"nba": (150.0, 300.0), "nhl": (3.0, 12.0)}


def _line(v: Any, league: str) -> float | None:
    n = _num(v)
    return n if n is not None and abs(n) <= LINE_MAX[league] else None


def _total(v: Any, league: str) -> float | None:
    n = _num(v)
    lo, hi = TOTAL_RANGE[league]
    return n if n is not None and lo <= n <= hi else None


def _eastern_date(iso_utc: str | None) -> str | None:
    """'2019-01-16T00:00Z' -> '2019-01-15': a 7pm ET tip belongs to the Eastern day."""
    if not iso_utc:
        return None
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(EASTERN).date().isoformat()


def _first(d: dict | None, *paths: str) -> Any:
    """First non-null value among dotted paths, e.g. 'spread.american'."""
    if not isinstance(d, dict):
        return None
    for path in paths:
        cur: Any = d
        for part in path.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
            if cur is None:
                break
        if cur is not None:
            return cur
    return None


def _snapshot(team_odds: dict | None, snap: str, league: str) -> dict:
    """Spread line, spread price, moneyline from teamOdds.{open|close|current}."""
    s = (team_odds or {}).get(snap) or {}
    return {
        "line": _line(_first(s, "pointSpread.american", "pointSpread.alternateDisplayValue",
                             "pointSpread.value"), league),
        # .value is a decimal price (1.91), never American, so it is not a fallback here
        "price": _price(_first(s, "spread.american", "spread.alternateDisplayValue")),
        "ml": _price(_first(s, "moneyLine.american", "moneyLine.alternateDisplayValue")),
    }


def _total_snapshot(item: dict, snap: str, league: str) -> dict:
    s = item.get(snap) or {}
    return {
        "total": _total(_first(s, "total.alternateDisplayValue", "total.american", "total.value"),
                        league),
        "over": _price(_first(s, "over.american", "over.alternateDisplayValue")),
        "under": _price(_first(s, "under.american", "under.alternateDisplayValue")),
    }


def _signed_home(abs_line: float | None, home_fav: bool | None) -> float | None:
    """Home-perspective spread: negative when home is favored."""
    if abs_line is None or home_fav is None:
        return abs_line
    return -abs(abs_line) if home_fav else abs(abs_line)


def parse_game(event: dict, league: str) -> dict | None:
    comp = (event.get("competitions") or [{}])[0]
    sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
    home, away = sides.get("home"), sides.get("away")
    if not home or not away:
        return None
    status = (comp.get("status") or event.get("status") or {})
    stype = status.get("type") or {}
    season = event.get("season") or {}
    period = status.get("period")
    reg = LEAGUES[league][2]

    def team(c: dict, k: str) -> Any:
        return (c.get("team") or {}).get(k)

    return {
        "game_id": str(event["id"]),
        "league": league,
        "season": season.get("year"),
        "season_type": season.get("type"),
        "start_time": event.get("date"),
        "game_date": _eastern_date(event.get("date")),  # start_time stays UTC
        "home_id": team(home, "id"), "home_name": team(home, "displayName"),
        "home_abbr": team(home, "abbreviation"),
        "away_id": team(away, "id"), "away_name": team(away, "displayName"),
        "away_abbr": team(away, "abbreviation"),
        "home_score": _num(home.get("score")) if stype.get("completed") else None,
        "away_score": _num(away.get("score")) if stype.get("completed") else None,
        "completed": bool(stype.get("completed")),
        "status": stype.get("name"),
        "periods": period,
        "went_ot": bool(period and period > reg) if stype.get("completed") else None,
        "shootout": ("SO" in (stype.get("shortDetail") or "")) if league == "nhl" else None,
        "neutral_site": comp.get("neutralSite"),
        "venue": (comp.get("venue") or {}).get("fullName"),
        "attendance": comp.get("attendance"),
        "loaded_at": datetime.now(timezone.utc).isoformat(),
    }


def parse_odds_item(item: dict, game: dict) -> dict:
    prov = item.get("provider") or {}
    h, a = item.get("homeTeamOdds") or {}, item.get("awayTeamOdds") or {}
    home_fav = h.get("favorite") if isinstance(h.get("favorite"), bool) else (
        (not a.get("favorite")) if isinstance(a.get("favorite"), bool) else None)

    # Fallback: infer favorite from details string, e.g. "BOS -6.5"
    details = item.get("details") or ""
    if home_fav is None and details:
        abbr = details.split(" ")[0].upper()
        if abbr == (game.get("home_abbr") or "").upper():
            home_fav = True
        elif abbr == (game.get("away_abbr") or "").upper():
            home_fav = False

    lg = game["league"]
    spread_abs = _line(item.get("spread"), lg)
    row = {
        "game_id": game["game_id"],
        "provider_id": str(prov.get("id")),
        "provider_name": prov.get("name"),
        "provider_priority": prov.get("priority"),
        "season": game.get("season"),
        "game_date": game.get("game_date"),
        "details": details,
        "home_favorite": home_fav,
        "home_spread": _signed_home(abs(spread_abs) if spread_abs is not None else None, home_fav),
        "home_spread_price": _price(h.get("spreadOdds")),
        "away_spread_price": _price(a.get("spreadOdds")),
        "home_ml": _price(h.get("moneyLine")),
        "away_ml": _price(a.get("moneyLine")),
        "total": _total(item.get("overUnder"), lg),
        "over_price": _price(item.get("overOdds")),
        "under_price": _price(item.get("underOdds")),
        "spread_winner_home": h.get("spreadWinner"),
        "ml_winner_home": h.get("moneylineWinner"),
    }
    for snap in ("open", "close", "current"):
        hs, as_ = _snapshot(h, snap, lg), _snapshot(a, snap, lg)
        ts = _total_snapshot(item, snap, lg)
        line = hs["line"] if hs["line"] is not None else (
            -as_["line"] if as_["line"] is not None else None)
        row.update({
            f"{snap}_home_spread": line,
            f"{snap}_home_spread_price": hs["price"],
            f"{snap}_away_spread_price": as_["price"],
            f"{snap}_home_ml": hs["ml"],
            f"{snap}_away_ml": as_["ml"],
            f"{snap}_total": ts["total"],
            f"{snap}_over_price": ts["over"],
            f"{snap}_under_price": ts["under"],
        })
    # 2013-14 .. ~2017-18 items carry no team snapshots, only item-level initialSpread /
    # initialOverUnder: the "Opening" book's line, home-signed, repeated on every provider.
    if row["open_home_spread"] is None:
        row["open_home_spread"] = _line(item.get("initialSpread"), lg)
    if row["open_total"] is None:
        row["open_total"] = _total(item.get("initialOverUnder"), lg)
    row["raw_json"] = json.dumps(item, separators=(",", ":"))
    row["loaded_at"] = datetime.now(timezone.utc).isoformat()
    return row


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------

def scoreboard(league: str, day: date, use_cache: bool) -> list[dict]:
    sport, lg, _ = LEAGUES[league]
    key = day.strftime("%Y%m%d")
    # cache only days that are fully in the past (all games final)
    past = day < date.today() - timedelta(days=1)
    data = cached_json(league, "scoreboard", key, f"{SITE}/{sport}/{lg}/scoreboard",
                       {"dates": key, "limit": 100},
                       use_cache=use_cache and past, write_cache=past)
    return (data or {}).get("events", [])


def odds_items(league: str, game: dict, use_cache: bool) -> list[dict]:
    sport, lg, _ = LEAGUES[league]
    gid = game["game_id"]
    url = f"{CORE}/{sport}/leagues/{lg}/events/{gid}/competitions/{gid}/odds"
    final = game["completed"]
    data = cached_json(league, "odds", gid, url, {"limit": 100},
                       use_cache=use_cache and final, write_cache=final)
    items = (data or {}).get("items", [])
    out = []
    for it in items:
        # some responses list only {"$ref": ...}; resolve those
        if set(it.keys()) <= {"$ref"} and it.get("$ref"):
            it = get_json(it["$ref"].replace("http://", "https://")) or {}
        if it:
            out.append(it)
    return out


def season_days(season: int) -> list[date]:
    """Generous window; events are filtered on ESPN's season.year afterwards.
    Covers the 2020 bubble (ended Oct 2020) and the Dec-Jul 2021 season."""
    start, end = date(season - 1, 9, 15), min(date(season, 10, 15), date.today() + timedelta(days=2))
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def collect(league: str, days: list[date], season: int | None, use_cache: bool
            ) -> tuple[list[dict], list[dict]]:
    with ThreadPoolExecutor(WORKERS) as ex:
        boards = list(ex.map(lambda d: scoreboard(league, d, use_cache), days))
    games, seen = [], set()
    for events in boards:
        for ev in events:
            g = parse_game(ev, league)
            if not g or g["game_id"] in seen:
                continue
            if g["season_type"] not in SEASON_TYPES:
                continue
            if season is not None and g["season"] != season:
                continue
            seen.add(g["game_id"])
            games.append(g)
    print(f"  {league}: {len(games)} games across {len(days)} days")

    def odds_for(g: dict) -> list[dict]:
        try:
            return [parse_odds_item(it, g) for it in odds_items(league, g, use_cache)]
        except Exception as e:  # one bad game shouldn't kill a backfill
            print(f"    odds failed for {g['game_id']}: {e}")
            return []

    with ThreadPoolExecutor(WORKERS) as ex:
        odds = [r for rows in ex.map(odds_for, games) for r in rows]
    with_lines = len({o["game_id"] for o in odds})
    print(f"  {league}: {len(odds)} odds rows, {with_lines}/{len(games)} games have lines")
    return games, odds


# ---------------------------------------------------------------------------
# DLT
# ---------------------------------------------------------------------------

def load(league: str, games: list[dict], odds: list[dict]) -> None:
    import dlt

    pipeline = dlt.pipeline(
        pipeline_name=f"espn_{league}",
        destination=dlt.destinations.duckdb(DB_PATH),
        dataset_name=league,
    )

    @dlt.resource(name="games", write_disposition="merge", primary_key="game_id")
    def games_res() -> Iterator[dict]:
        yield from games

    @dlt.resource(name="odds", write_disposition="merge",
                  primary_key=["game_id", "provider_id"])
    def odds_res() -> Iterator[dict]:
        yield from odds

    print(pipeline.run([games_res(), odds_res()]))


def run_season(league: str, season: int, use_cache: bool = True) -> None:
    print(f"ESPN {league.upper()} season {season}")
    games, odds = collect(league, season_days(season), season, use_cache)
    if games:
        load(league, games, odds)


def run_daily(leagues: list[str]) -> None:
    today = date.today()
    days = [today + timedelta(days=i) for i in range(-3, 3)]
    for lg in leagues:
        games, odds = collect(lg, days, None, use_cache=True)
        if games:
            load(lg, games, odds)


def probe(league: str, day: date) -> None:
    """Print what ESPN actually returns -- run this first and paste the output."""
    events = scoreboard(league, day, use_cache=False)
    print(f"{league} {day}: {len(events)} events")
    if not events:
        return
    g = parse_game(events[0], league)
    print("parsed game:", json.dumps(g, indent=2))
    items = odds_items(league, g, use_cache=False)
    print(f"odds providers: {[ (it.get('provider') or {}).get('name') for it in items ]}")
    if items:
        raw = json.dumps(items[0], indent=2)
        print("raw first odds item (truncated):\n", raw[:4000])
        row = parse_odds_item(items[0], g)
        row.pop("raw_json")
        print("parsed odds row:", json.dumps(row, indent=2))


def main() -> None:
    p = argparse.ArgumentParser(description="Load ESPN NBA/NHL games + lines into DuckDB.")
    p.add_argument("--league", choices=list(LEAGUES), help="league for a season backfill")
    p.add_argument("--season", type=int, help="ESPN season year (2025-26 -> 2026)")
    p.add_argument("--end-season", type=int, default=None)
    p.add_argument("--daily", action="store_true", help="both leagues, last 3 + next 2 days")
    p.add_argument("--no-cache", action="store_true", help="ignore cached raw JSON")
    p.add_argument("--probe", choices=list(LEAGUES), help="print raw + parsed sample, no load")
    p.add_argument("--date", type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
                   default=date.today() - timedelta(days=1))
    a = p.parse_args()

    if a.probe:
        probe(a.probe, a.date)
    elif a.daily:
        run_daily(list(LEAGUES))
    elif a.league and a.season:
        for s in range(a.season, (a.end_season or a.season) + 1):
            run_season(a.league, s, use_cache=not a.no_cache)
    else:
        p.error("use --probe, --daily, or --league + --season")


if __name__ == "__main__":
    main()
