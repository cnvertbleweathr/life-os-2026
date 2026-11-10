"""/api/nba-nhl slate and record routes over synthetic pick-history files (ONS_BETS_DIR)."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import nba_nhl


def game(gid, start, season=2027, paper=None, graded=False, **kw):
    g = {"game_id": gid, "league": "nba", "season": season, "season_type": 2, "game_date": start[:10],
         "start_time": start, "matchup": f"A{gid} @ H{gid}", "home_team": f"H{gid}", "away_team": f"A{gid}",
         "captured_at": "2026-11-10T16:00:00+00:00", "captured_after_start": False, "book": "Draft Kings",
         "home_spread": -4.5, "total": 220.5, "verdict": "NO_BET", "bet": None, "rules_fired": [],
         "paper": paper}
    if graded:
        g.update(final_status="STATUS_FINAL", home_score=110, away_score=100, closing_total=222.5,
                 graded_at="2026-11-11T12:00:00+00:00")
    g.update(kw)
    return g


def paper(outcome=None, pnl=None, clv=None, fires=True):
    pe = {"test": "nba_totals_open_v1", "fires": fires, "side": "OVER" if fires else None,
          "pred_total": 233.0, "captured_total": 220.5, "gap": 12.5, "price": -110.0 if fires else None,
          "prices_in_band": True}
    if outcome:
        pe.update(outcome=outcome, pnl=pnl, clv=clv)
    return pe


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ONS_BETS_DIR", str(tmp_path))
    h = tmp_path / "nba" / "history"
    h.mkdir(parents=True)
    files = {
        "2026-11-08": [game("1", "2026-11-09T00:30:00+00:00", paper=paper("win", 0.909, 2.0), graded=True),
                       game("2", "2026-11-09T00:00:00+00:00", paper=paper("loss", -1.0, -1.0), graded=True)],
        "2026-11-09": [game("3", "2026-11-10T00:00:00+00:00", paper=paper("push", 0.0, 0.0), graded=True),
                       game("4", "2026-11-10T01:00:00+00:00", paper=paper(fires=False), graded=True)],
        "2026-11-10": [game("5", "2026-11-11T00:00:00+00:00", paper=paper())],
        "2026-04-01": [game("9", "2026-04-02T00:00:00+00:00", season=2026, paper=paper("win", 1.0, 1.0), graded=True)],
    }
    for d, gs in files.items():
        (h / f"{d}.json").write_text(json.dumps({"league": "nba", "games": gs}))
    (h / "notes.json").write_text("{}")          # not a date: ignored
    app = FastAPI()
    app.include_router(nba_nhl.router, prefix="/api/nba-nhl")
    return TestClient(app)


def test_slate_sorted_by_start_with_neighbours(client):
    r = client.get("/api/nba-nhl/nba/slate", params={"date": "2026-11-08"}).json()
    assert r["logged"] and [g["game_id"] for g in r["games"]] == ["2", "1"]
    assert r["previous_date"] == "2026-04-01" and r["next_date"] == "2026-11-09"
    g = r["games"][1]
    assert g["paper"]["outcome"] == "win" and g["home_score"] == 110 and g["rules_fired"] == []


def test_missing_day_is_empty_not_error(client):
    r = client.get("/api/nba-nhl/nhl/slate", params={"date": "2026-11-10"}).json()
    assert r == {**r, "logged": False, "games": [], "previous_date": None, "next_date": None}


def test_bad_inputs(client):
    assert client.get("/api/nba-nhl/mlb/slate").status_code == 404
    assert client.get("/api/nba-nhl/nba/slate", params={"date": "11/08/2026"}).status_code == 422
    assert client.get("/api/nba-nhl/nba/slate", params={"date": "2026-02-30"}).status_code == 422


def test_record_matches_mart_definitions(client):
    r = client.get("/api/nba-nhl/nba/record").json()
    assert r["season"] == 2027 and r["seasons"] == [2026, 2027]
    assert (r["games_logged"], r["games_graded"], r["bets"]) == (5, 4, 0)
    # entries: win, loss, push, pending. Push counts as an entry but not in win% / ROI.
    assert (r["paper_entries"], r["paper_graded"]) == (4, 3)
    assert (r["paper_wins"], r["paper_losses"], r["paper_pushes"]) == (1, 1, 1)
    assert r["paper_win_pct"] == 50.0 and r["paper_roi"] == pytest.approx(-4.5, abs=0.1)
    assert r["paper_clv_avg"] == pytest.approx(0.33, abs=0.01) and r["paper_beat_close_pct"] == pytest.approx(33.3, abs=0.1)
    assert [d["date"] for d in r["days"]] == ["2026-11-08", "2026-11-09", "2026-11-10"]


def test_record_other_season_and_empty_league(client):
    assert client.get("/api/nba-nhl/nba/record", params={"season": 2026}).json()["paper_wins"] == 1
    r = client.get("/api/nba-nhl/nhl/record").json()
    assert r["season"] is None and r["games_logged"] == 0 and r["paper_roi"] is None and r["days"] == []
