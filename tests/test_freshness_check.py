"""
Tests for scripts/freshness_check.py against a temp DuckDB and data dir.

  uv run --with pytest pytest tests/test_freshness_check.py -q
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("America/Denver")
NOW = datetime(2026, 10, 22, 21, 0, tzinfo=TZ)   # a Thursday in CFB season


@pytest.fixture()
def fc(tmp_path, monkeypatch):
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ONS_DUCKDB_PATH", str(tmp_path / "ons.duckdb"))
    spec = importlib.util.spec_from_file_location("freshness_check", ROOT / "scripts/freshness_check.py")
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "freshness_check", mod)   # dataclasses need this
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def con(tmp_path):
    c = duckdb.connect(str(tmp_path / "ons.duckdb"))
    c.execute("CREATE SCHEMA ops")
    c.execute("CREATE TABLE ops.pipeline_runs (source_name VARCHAR, started_at VARCHAR, status VARCHAR)")
    yield c
    c.close()


def add_runs(con, name, days_ago_status):
    for days_ago, status in days_ago_status:
        ts = (NOW - timedelta(days=days_ago)).replace(hour=9, tzinfo=None).isoformat(timespec="seconds")
        con.execute("INSERT INTO ops.pipeline_runs VALUES (?, ?, ?)", [name, ts, status])


def by_subject(findings):
    return {f.subject: f for f in findings}


def test_healthy_daily_step_and_sync(fc, con):
    add_runs(con, "strava", [(d, "ok") for d in range(0, 10)])
    f = by_subject(fc.check_steps(con, NOW))
    assert f["strava"].status == fc.OK
    assert f["daily_sync"].status == fc.OK


def test_repeated_failures_alert(fc, con):
    # The Oct 15–21 sync_playlist_artists case.
    add_runs(con, "sync_playlist_artists", [(9, "ok"), (8, "ok"), (7, "failed"),
                                            (6, "failed"), (1, "failed"), (0, "failed")])
    f = by_subject(fc.check_steps(con, NOW))["sync_playlist_artists"]
    assert f.status == fc.ALERT and "failed 4 runs in a row" in f.detail


def test_single_failure_is_not_an_alert(fc, con):
    add_runs(con, "spotify_ingest", [(3, "ok"), (2, "ok"), (1, "ok"), (0, "failed")])
    assert by_subject(fc.check_steps(con, NOW))["spotify_ingest"].status == fc.OK


def test_twice_weekly_step_learns_its_schedule(fc, con):
    # Mon/Thu step: last ran 3 days ago is normal, 9 days ago is not.
    add_runs(con, "calendar_export", [(31, "ok"), (28, "ok"), (24, "ok"), (21, "ok"),
                                      (17, "ok"), (14, "ok"), (10, "ok"), (7, "ok"), (3, "ok")])
    assert by_subject(fc.check_steps(con, NOW))["calendar_export"].status == fc.OK

    con.execute("DELETE FROM ops.pipeline_runs WHERE started_at > ?",
                [(NOW - timedelta(days=9)).replace(tzinfo=None).isoformat()])
    add_runs(con, "strava", [(0, "ok")])          # keep the sync itself alive
    f = by_subject(fc.check_steps(con, NOW))["calendar_export"]
    assert f.status == fc.ALERT and "last success" in f.detail


def test_sync_stopped(fc, con):
    add_runs(con, "strava", [(3, "ok"), (2, "ok")])
    f = by_subject(fc.check_steps(con, NOW))["daily_sync"]
    assert f.status == fc.ALERT and "hasn't run" in f.detail


def test_cfb_scores_stalled(fc, con):
    # The Week-4 stall: newest final score three weeks old.
    con.execute("CREATE SCHEMA cfbd")
    con.execute("CREATE TABLE cfbd.games (season BIGINT, week BIGINT, start_date VARCHAR, home_points BIGINT)")
    con.execute("INSERT INTO cfbd.games VALUES (2026, 4, '2026-09-26T19:30:00.000Z', 31)")
    con.execute("INSERT INTO cfbd.games VALUES (2026, 8, '2026-10-24T19:30:00.000Z', NULL)")
    f = fc.check_cfb(con, NOW)
    assert f.status == fc.ALERT and "week 4" in f.detail

    con.execute("INSERT INTO cfbd.games VALUES (2026, 7, '2026-10-17T19:30:00.000Z', 24)")
    assert fc.check_cfb(con, NOW).status == fc.OK
    assert fc.check_cfb(con, datetime(2026, 2, 1, tzinfo=TZ)) is None   # off-season


def test_file_checks(fc, tmp_path):
    data = tmp_path / "data"
    assert fc.check_backups(NOW).status == fc.ALERT

    bdir = data / "backups" / "duckdb"
    bdir.mkdir(parents=True)
    old = bdir / "ons_2026-10-19_020000.duckdb"
    old.write_bytes(b"x")
    os.utime(old, ((NOW - timedelta(days=3)).timestamp(),) * 2)
    assert fc.check_backups(NOW).status == fc.ALERT
    new = bdir / "ons_2026-10-22_020000.duckdb"
    new.write_bytes(b"x")
    os.utime(new, ((NOW - timedelta(hours=19)).timestamp(),) * 2)
    assert fc.check_backups(NOW).status == fc.OK

    d10 = data / "spotify" / "processed"
    d10.mkdir(parents=True)
    (d10 / "daily10_latest.json").write_text(json.dumps({"updated_at_utc": "2026-10-20T15:00:00Z"}))
    assert fc.check_daily10(NOW).status == fc.WARN
    (d10 / "daily10_latest.json").write_text(json.dumps({"updated_at_utc": "2026-10-22T15:05:00Z"}))
    assert fc.check_daily10(NOW).status == fc.OK


def test_cli_records_and_stays_non_blocking(fc, con, tmp_path, monkeypatch, capsys):
    add_runs(con, "strava", [(5, "failed"), (4, "failed")])
    con.close()
    monkeypatch.setattr("sys.argv", ["freshness_check.py", "--no-notify"])
    assert fc.main() == 0                       # ALERTs don't fail the sync step
    assert "✗" in capsys.readouterr().out

    c = duckdb.connect(str(tmp_path / "ons.duckdb"), read_only=True)
    assert c.execute("SELECT count(*) FROM ops.freshness_checks WHERE status = 'alert'").fetchone()[0] >= 2
    c.close()
    assert list((tmp_path / "data" / "daily").glob("*/freshness.json"))

    monkeypatch.setattr("sys.argv", ["freshness_check.py", "--no-notify", "--no-record", "--strict"])
    assert fc.main() == 1
