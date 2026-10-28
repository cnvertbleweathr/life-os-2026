"""
/api/sports ESPN endpoints — parsing and assembly against ESPN-shaped fixtures.

No network: api.espn.get_json is replaced with a URL router over canned
payloads shaped like site.api.espn.com responses.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import espn
from api.routers import sports

NOW = datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%MZ")


def team(id_, name, abbr):
    return {"id": id_, "displayName": name, "shortDisplayName": name.split()[-1],
            "abbreviation": abbr, "logo": f"https://a.espncdn.com/i/teamlogos/{abbr}.png"}


def event(id_, home, away, start, state="pre", detail="7:00 PM ET", home_score=None, away_score=None,
          national=False, season_type=2, note=None, home_rank=None):
    comp = {
        "status": {"type": {"state": state, "shortDetail": detail}},
        "competitors": [
            {"homeAway": "home", "team": home, "score": home_score,
             "records": [{"summary": "3-1"}], "curatedRank": {"current": home_rank or 99}},
            {"homeAway": "away", "team": away, "score": away_score, "records": [{"summary": "1-3"}]},
        ],
        "broadcasts": [{"market": "national" if national else "home", "names": ["ESPN" if national else "Altitude"]}],
        "notes": [{"headline": note}] if note else [],
        "venue": {"fullName": "Ball Arena"},
    }
    return {"id": id_, "date": _iso(start), "name": f"{away['displayName']} at {home['displayName']}",
            "shortName": f"{away['abbreviation']} @ {home['abbreviation']}",
            "season": {"type": season_type}, "competitions": [comp],
            "links": [{"rel": ["summary", "desktop", "event"], "href": f"https://www.espn.com/game/_/gameId/{id_}"}]}


DEN = team("7", "Denver Nuggets", "DEN")
ORL = team("19", "Orlando Magic", "ORL")
LAL = team("13", "Los Angeles Lakers", "LAL")
BOS = team("2", "Boston Celtics", "BOS")
COL = team("17", "Colorado Avalanche", "COL")
FLA = team("26", "Florida Panthers", "FLA")
TB = team("27", "Tampa Bay Buccaneers", "TB")
OCSC = team("12011", "Orlando City SC", "ORL")
MIA = team("28", "Miami Marlins", "MIA")
COLR = team("27", "Colorado Rockies", "COL")
LAD = team("19", "Los Angeles Dodgers", "LAD")
NYY = team("10", "New York Yankees", "NYY")


def teams_payload(*ts):
    return {"sports": [{"leagues": [{"teams": [{"team": t} for t in ts]}]}]}


ROUTES = {
    # team listings
    "basketball/nba/teams": teams_payload(DEN, ORL, LAL, BOS),
    "hockey/nhl/teams": teams_payload(COL, FLA),
    "football/nfl/teams": teams_payload(TB),
    "soccer/usa.1/teams": teams_payload(OCSC),
    "baseball/mlb/teams": teams_payload(MIA, COLR, LAD, NYY),
    # scoreboards
    "basketball/nba/scoreboard": {"events": [
        event("401", DEN, LAL, NOW - timedelta(hours=1), state="in", detail="Q3 4:12",
              home_score="78", away_score="71"),
        event("402", BOS, ORL, NOW + timedelta(hours=2), national=True),
    ]},
    "baseball/mlb/scoreboard": {"events": [
        event("501", LAD, NYY, NOW + timedelta(hours=3), season_type=3, national=True,
              note="World Series - Game 3"),
    ]},
    "hockey/nhl/scoreboard": {"events": []},
    "football/nfl/scoreboard": {"events": []},
    "football/college-football/scoreboard": {"events": []},
    "soccer/usa.1/scoreboard": {"events": []},
    # schedules (Avalanche plays tomorrow; Marlins/Rockies offseason)
    "hockey/nhl/teams/17/schedule": {"events": [
        event("601", COL, FLA, NOW - timedelta(days=2), state="post", detail="Final"),
        event("602", COL, FLA, NOW + timedelta(days=1)),
    ]},
    "hockey/nhl/teams/26/schedule": {"events": [event("602", COL, FLA, NOW + timedelta(days=1))]},
    "basketball/nba/teams/7/schedule": {"events": [
        event("401", DEN, LAL, NOW - timedelta(hours=1), state="in", detail="Q3 4:12")]},
    "basketball/nba/teams/19/schedule": {"events": [event("402", BOS, ORL, NOW + timedelta(hours=2))]},
    "football/nfl/teams/27/schedule": {"events": [event("701", TB, TB, NOW + timedelta(days=5))]},
    "soccer/usa.1/teams/12011/schedule": {"events": []},
    "baseball/mlb/teams/28/schedule": {"events": []},
    "baseball/mlb/teams/27/schedule": {"events": []},
    # news: ESPN tags articles with team categories
    "basketball/nba/news": {"articles": [
        {"headline": "Jokic triple-double", "published": "2026-10-27T05:00:00Z",
         "links": {"web": {"href": "https://espn.com/a/1"}}, "categories": [{"type": "team", "teamId": 7}]},
        {"headline": "Celtics news, not ours", "published": "2026-10-27T06:00:00Z",
         "links": {"web": {"href": "https://espn.com/a/2"}}, "categories": [{"type": "team", "teamId": 2}]},
        {"headline": "Banchero injury update", "published": "2026-10-27T07:00:00Z",
         "links": {"web": {"href": "https://espn.com/a/3"}}, "categories": [{"type": "team", "teamId": 19}]},
    ]},
}


@pytest.fixture()
def client(monkeypatch):
    calls = []

    async def fake_get_json(_client, url, params, ttl):
        path = url.replace(espn.SITE + "/", "")
        calls.append((path, params))
        if params and params.get("seasontype") == 3:
            raise RuntimeError("404")
        if path not in ROUTES:
            return {"events": [], "articles": []}
        return ROUTES[path]

    monkeypatch.setattr(espn, "get_json", fake_get_json)
    monkeypatch.setattr(sports, "today_local", lambda: date(2026, 10, 27))
    app = FastAPI()
    app.include_router(sports.router, prefix="/api/sports")
    c = TestClient(app)
    c.calls = calls
    return c


def test_today_assembles_my_teams_upcoming_and_top(client):
    r = client.get("/api/sports/today")
    assert r.status_code == 200
    d = r.json()
    assert d["errors"] == []
    assert d["any_live"] is True

    mine = {g["my_team"] for g in d["my_teams"]}
    assert mine == {"Denver Nuggets", "Orlando Magic"}
    live = d["my_teams"][0]  # live games sort first
    assert live["is_live"] and live["home"]["score"] == "78" and live["status_detail"] == "Q3 4:12"
    assert live["link"].endswith("/401")

    # Nuggets/Magic play today so aren't repeated in upcoming; Avs+Panthers share game 602
    up_ids = [g["id"] for g in d["upcoming"]]
    assert "401" not in up_ids and "402" not in up_ids
    assert "602" in up_ids and "701" in up_ids
    assert "601" not in up_ids  # finished game excluded
    assert up_ids.count("602") == 1  # Avs vs Panthers listed once
    avs_fla = next(g for g in d["upcoming"] if g["id"] == "602")
    assert set(avs_fla["my_team"].split(" / ")) == {"Colorado Avalanche", "Florida Panthers"}

    # World Series (postseason + national + note) outranks everything
    assert d["top"][0]["id"] == "501"
    assert d["top"][0]["postseason"] is True

    # CFB scoreboard asks for all FBS
    cfb = [p for path, p in client.calls if path == "football/college-football/scoreboard"]
    assert cfb and cfb[0]["groups"] == 80 and cfb[0]["dates"] == "20261027"


def test_team_news_filters_to_my_teams(client):
    d = client.get("/api/sports/team-news").json()
    titles = [a["title"] for a in d["articles"]]
    assert "Celtics news, not ours" not in titles
    assert titles[:2] == ["Banchero injury update", "Jokic triple-double"]  # newest first
    assert d["articles"][0]["team"] == "Orlando Magic"
    assert len(d["teams"]) == 8


def test_team_news_single_team(client):
    d = client.get("/api/sports/team-news", params={"team": "Denver Nuggets"}).json()
    assert [a["title"] for a in d["articles"]] == ["Jokic triple-double"]


def test_one_league_failing_does_not_break_page(client, monkeypatch):
    real = espn.get_json

    async def flaky(c, url, params, ttl):
        if "hockey/nhl/scoreboard" in url:
            raise RuntimeError("ESPN 503")
        return await real(c, url, params, ttl)

    monkeypatch.setattr(espn, "get_json", flaky)
    d = client.get("/api/sports/today").json()
    assert any("503" in e for e in d["errors"])
    assert len(d["all"]) == 3


def test_ttl_cache_hits(monkeypatch):
    espn.clear_cache()
    hits = {"n": 0}

    class Resp:
        def raise_for_status(self): ...
        def json(self): return {"ok": 1}

    class C:
        async def get(self, *a, **k):
            hits["n"] += 1
            return Resp()

    import asyncio
    asyncio.run(espn.get_json(C(), "u", {"a": 1}, ttl=60))
    asyncio.run(espn.get_json(C(), "u", {"a": 1}, ttl=60))
    assert hits["n"] == 1
    espn.clear_cache()
