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
    # 00:30Z on Jan 16 is 7:30pm ET on Jan 15: game_date is the US/Eastern date.
    assert g["went_ot"] is True and g["game_date"] == "2024-01-15"
    assert g["start_time"] == "2024-01-16T00:30Z"


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


# ---------------------------------------------------------------------------
# Real ESPN responses (trimmed) from the Phase 0 probes, tests/fixtures/espn/
# ---------------------------------------------------------------------------

import json
from pathlib import Path

FIX = Path(__file__).parent / "fixtures" / "espn"


def _fixture(name):
    return json.loads((FIX / name).read_text())


def test_real_2019_late_tip_uses_eastern_date():
    # Pacers v Suns, 7pm ET on 2019-01-15 = 2019-01-16T00:00Z. ESPN's scoreboard for
    # dates=20190115 returns it, so its game_date must be 2019-01-15.
    g = eo.parse_game(_fixture("nba_2019_event.json"), "nba")
    assert g["start_time"] == "2019-01-16T00:00Z"
    assert g["game_date"] == "2019-01-15"


def test_real_2019_zero_moneyline_is_null():
    g = eo.parse_game(_fixture("nba_2019_event.json"), "nba")
    r = eo.parse_odds_item(_fixture("nba_2019_items.json")["Wynn"], g)
    assert r["home_spread"] == -10.5 and r["home_spread_price"] == -110
    assert r["home_ml"] is None and r["away_ml"] is None


def test_real_2015_initial_line_is_the_open():
    # Rockets home v Thunder. Opened HOU -2 / 206, closed OKC -3 / 208.5 at 5Dimes.
    # initialSpread is home-signed and is the only open data before ~2019.
    g = eo.parse_game(_fixture("nba_2015_event.json"), "nba")
    items = _fixture("nba_2015_items.json")
    r = eo.parse_odds_item(items["5Dimes.eu"], g)
    assert r["home_spread"] == 3.0 and r["total"] == 208.5
    assert r["open_home_spread"] == -2.0 and r["open_total"] == 206.0
    assert r["current_home_spread"] == 3.0
    assert r["close_home_spread"] is None  # no close snapshot in this era
    op = eo.parse_odds_item(items["Opening"], g)
    assert op["home_spread"] == op["open_home_spread"] == -2.0


def test_real_2015_impossible_prices_are_null():
    g = eo.parse_game(_fixture("nba_2015_event.json"), "nba")
    items = _fixture("nba_2015_items.json")
    bov = eo.parse_odds_item(items["BOVADA.lv"], g)
    assert bov["home_ml"] is None and bov["away_ml"] is None  # posted as 0
    assert bov["home_spread"] == 2.5
    nf = eo.parse_odds_item(items["numberfire"], g)  # a projection site, not a book
    assert nf["home_spread_price"] is None  # 63.13 is not an American price
    assert nf["home_ml"] == 121 and nf["away_ml"] == -134
    # real prices, including EVEN, survive
    assert eo._price("EVEN") == 100 and eo._price("-110") == -110 and eo._price(0) is None


def test_real_2023_junk_close_snapshot_is_null():
    # 2022-23 ESPN BET: close.pointSpread and close.total both hold the price "-115".
    # The item-level line (BOS -7.5 on the road, 232.5) is fine and must survive.
    g = eo.parse_game(EVENT, "nba")
    r = eo.parse_odds_item(_fixture("nba_2023_espnbet_junk_close.json"), g)
    assert r["home_spread"] == 7.5 and r["total"] == 232.5
    assert r["close_home_spread"] is None and r["close_total"] is None
    assert r["close_home_ml"] == 240 and r["close_away_ml"] == -330  # MLs are real
    assert r["close_home_spread_price"] == -115


def test_line_bounds_by_league():
    assert eo._line(-7.5, "nba") == -7.5 and eo._line(-115, "nba") is None
    assert eo._line(1.5, "nhl") == 1.5 and eo._line(-115, "nhl") is None
    assert eo._total(232.5, "nba") == 232.5 and eo._total(-115, "nba") is None
    assert eo._total(6.5, "nhl") == 6.5 and eo._total(115, "nhl") is None
    assert eo._total(None, "nba") is None
