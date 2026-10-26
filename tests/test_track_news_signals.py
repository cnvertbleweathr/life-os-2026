"""track_news_signals.load_movers against cfbd.line_history's real schema."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def tns(monkeypatch):
    monkeypatch.setenv("NEWS_API_KEY", "test")
    spec = importlib.util.spec_from_file_location("track_news_signals", ROOT / "scripts/track_news_signals.py")
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "track_news_signals", mod)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def con():
    c = duckdb.connect()
    c.execute("CREATE SCHEMA cfbd")
    # Same columns as scripts/track_lines.py creates.
    c.execute("""
        CREATE TABLE cfbd.line_history (
            game_id BIGINT, season INTEGER, week INTEGER, home_team VARCHAR, away_team VARCHAR,
            home_conference VARCHAR, away_conference VARCHAR, provider VARCHAR,
            spread DOUBLE, over_under DOUBLE, home_moneyline INTEGER, away_moneyline INTEGER,
            spread_open DOUBLE, over_under_open DOUBLE, spread_movement DOUBLE, ou_movement DOUBLE,
            line_type VARCHAR, snapshot_date DATE, snapshot_ts TIMESTAMP, day_of_week INTEGER
        )
    """)

    def snap(game, provider, day, spread, opened, home="Utah", away="BYU", week=9):
        c.execute(
            "INSERT INTO cfbd.line_history (game_id, season, week, home_team, away_team, provider,"
            " spread, spread_open, spread_movement, line_type, snapshot_date, snapshot_ts)"
            " VALUES (?, 2026, ?, ?, ?, ?, ?, ?, ?, 'current', ?, ?)",
            [game, week, home, away, provider, spread, opened, spread - opened,
             f"2026-10-{day:02d}", f"2026-10-{day:02d} 09:00:00"],
        )

    # Game 1: both books moved 2.5 toward home by the latest snapshot.
    snap(1, "DraftKings", 19, -3.5, -3.0)
    snap(1, "DraftKings", 21, -5.5, -3.0)
    snap(1, "Bovada",     21, -5.5, -3.0)
    # Game 2: barely moved.
    snap(2, "DraftKings", 21, -7.0, -7.0, home="Ohio State", away="Penn State")
    # A different week must be ignored.
    snap(3, "DraftKings", 21, 3.0, 10.0, week=8)
    return c


def test_movers_use_latest_snapshot_per_provider(tns, con):
    df = tns.load_movers(con, 2026, 9, min_move=0.5)
    assert list(df["game_id"]) == [1]
    row = df.iloc[0]
    assert row["spread_latest"] == -5.5 and row["spread_open"] == -3.0
    assert row["spread_movement"] == -2.5


def test_all_games_ordered_by_movement(tns, con):
    df = tns.load_movers(con, 2026, 9, min_move=None)
    assert list(df["game_id"]) == [1, 2]
    assert {"spread_latest", "spread_open", "spread_movement", "home_team", "away_team"} <= set(df.columns)
