"""Offline tests for the NBA/NHL ingestion parsers (no network).

Fixtures mirror the two ESPN core-odds shapes seen in the wild:
  * multi-book era (<=2023): item-level numbers, empty-ish snapshots
  * partner-book era (2024+): open / close / current snapshots per team
Run `python pipelines/espn_odds_pipeline.py --probe nba --date ...` on the
Mac mini to confirm the live shape still matches.
"""

from pipelines import espn_odds_pipeline as eo

EVENT = {
    "id": "401585183",
    "date": "2024-01-16T00:30Z",
    "season": {"year": 2024, "type": 2},
    "competitions": [{
        "neutralSite": False,
        "venue": {"fullName": "Ball Arena"},
        "status": {"period": 5, "type": {"completed": True, "name": "STATUS_FINAL",
                                         "shortDetail": "Final/OT"}},
        "competitors": [
            {"homeAway": "home", "score": "117",
             "team": {"id": "7", "displayName": "Denver Nuggets", "abbreviation": "DEN"}},
            {"homeAway": "away", "score": "110",
             "team": {"id": "13", "displayName": "Los Angeles Lakers", "abbreviation": "LAL"}},
        ],
    }],
}

OLD_ITEM = {  # multi-book era
    "provider": {"id": "40", "name": "consensus", "priority": 0},
    "details": "DEN -6.5", "overUnder": 228.5, "spread": 6.5,
    "overOdds": -110, "underOdds": -110,
    "homeTeamOdds": {"favorite": True, "moneyLine": -260, "spreadOdds": -110},
    "awayTeamOdds": {"favorite": False, "moneyLine": 210, "spreadOdds": -110},
}

NEW_ITEM = {  # partner-book era, home underdog
    "provider": {"id": "58", "name": "ESPN BET", "priority": 1},
    "details": "LAL -2.5", "overUnder": 230.5, "spread": 2.5,
    "homeTeamOdds": {
        "favorite": False, "moneyLine": 115, "spreadOdds": -108,
        "open": {"pointSpread": {"american": "+1.5"}, "spread": {"american": "-110"},
                 "moneyLine": {"american": "+105"}},
        "close": {"pointSpread": {"american": "+2.5"}, "spread": {"american": "-108"},
                  "moneyLine": {"american": "+115"}},
    },
    "awayTeamOdds": {
        "favorite": True, "moneyLine": -135, "spreadOdds": -112,
        "close": {"pointSpread": {"american": "-2.5"}, "spread": {"american": "-112"},
                  "moneyLine": {"american": "-135"}},
    },
    "open": {"total": {"alternateDisplayValue": "228.5"}, "over": {"american": "-110"}},
    "close": {"total": {"alternateDisplayValue": "230.5"}, "over": {"american": "-105"},
              "under": {"american": "-115"}},
}


def test_num():
    assert eo._num("-110") == -110
    assert eo._num("+135") == 135
    assert eo._num("EVEN") == 100
    assert eo._num("o215.5") == 215.5
    assert eo._num("PK") == 0
    assert eo._num(None) is None and eo._num(True) is None


def test_parse_game():
    g = eo.parse_game(EVENT, "nba")
    assert g["game_id"] == "401585183" and g["season"] == 2024
    assert g["home_abbr"] == "DEN" and g["home_score"] == 117 and g["away_score"] == 110
    assert g["went_ot"] is True and g["game_date"] == "2024-01-16"


def test_old_item_home_favorite():
    g = eo.parse_game(EVENT, "nba")
    r = eo.parse_odds_item(OLD_ITEM, g)
    assert r["home_spread"] == -6.5 and r["home_ml"] == -260 and r["total"] == 228.5


def test_new_item_home_dog_with_snapshots():
    g = eo.parse_game(EVENT, "nba")
    r = eo.parse_odds_item(NEW_ITEM, g)
    assert r["home_favorite"] is False and r["home_spread"] == 2.5
    assert r["open_home_spread"] == 1.5 and r["close_home_spread"] == 2.5
    assert r["close_home_ml"] == 115 and r["close_away_spread_price"] == -112
    assert r["open_total"] == 228.5 and r["close_total"] == 230.5 and r["close_under_price"] == -115


def test_favorite_from_details_when_flags_missing():
    g = eo.parse_game(EVENT, "nba")
    item = {**OLD_ITEM, "homeTeamOdds": {"moneyLine": -260}, "awayTeamOdds": {"moneyLine": 210}}
    assert eo.parse_odds_item(item, g)["home_spread"] == -6.5


def test_dlt_load_roundtrip(tmp_path, monkeypatch):
    import duckdb
    db = tmp_path / "t.duckdb"
    monkeypatch.setattr(eo, "DB_PATH", str(db))
    monkeypatch.setenv("DLT_DATA_DIR", str(tmp_path / "dlt"))
    monkeypatch.setenv("DLT_PIPELINE_DIR", str(tmp_path / "dlt_pipes"))
    g = eo.parse_game(EVENT, "nba")
    odds = [eo.parse_odds_item(OLD_ITEM, g), eo.parse_odds_item(NEW_ITEM, g)]
    eo.load("nba", [g], odds)
    eo.load("nba", [g], odds)  # merge: rerun must not duplicate
    con = duckdb.connect(str(db))
    assert con.execute("select count(*) from nba.games").fetchone()[0] == 1
    assert con.execute("select count(*) from nba.odds").fetchone()[0] == 2
    assert con.execute(
        "select close_home_spread from nba.odds where provider_id='58'").fetchone()[0] == 2.5
