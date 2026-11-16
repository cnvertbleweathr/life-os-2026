"""Stage 1 tests: the morning-brief data tools, against a tiny fake warehouse."""

from __future__ import annotations

import json
from datetime import date, timedelta

import duckdb
import pytest

from agents.morning_brief.snapshot import build_snapshot, facts
from agents.morning_brief.tools import _streak

TODAY = date(2026, 11, 15)


@pytest.fixture
def data(tmp_path, monkeypatch):
    """A temp data dir with a habit log, shows and a calendar export."""
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ONS_TZ", "America/Denver")

    habits = tmp_path / "habits" / "habits_log.jsonl"
    habits.parent.mkdir(parents=True)
    lines = []
    for i, med in enumerate([True, True, True, False, True]):      # Nov 14 back to Nov 10
        d = TODAY - timedelta(days=i + 1)
        lines.append({"date": d.isoformat(), "meditation": med, "pushups_100": i == 0})
    habits.write_text("\n".join(json.dumps(x) for x in lines) + "\n")

    shows = tmp_path / "shows" / "my_artist_shows.json"
    shows.parent.mkdir(parents=True)
    shows.write_text(json.dumps({"fetched_at": "2026-11-15T16:00:00+00:00", "shows": [
        {"artist": "Wild Pink", "title": "Wild Pink", "venue": "Bluebird",
         "start_datetime": "2026-11-15T20:00:00-07:00"},
        {"artist": "RJD2", "title": "RJD2", "venue": "Ogden",
         "start_datetime": "2026-11-18T19:30:00-07:00"},
        {"artist": "RJD2", "title": "RJD2 - Ages 16+", "venue": "Ogden - Denver",
         "start_datetime": "2026-11-18T19:30:00-07:00"},   # duplicate listing
        {"artist": "Too Far", "title": "Too Far", "venue": "Gothic",
         "start_datetime": "2027-01-30T19:00:00-07:00"},
    ]}))

    cal = tmp_path / "calendar" / "processed" / "events_clean_2026.csv"
    cal.parent.mkdir(parents=True)
    cal.write_text(
        "start,end,all_day,summary,description,location\n"
        "2026-11-15T09:00:00-07:00,2026-11-15T10:00:00-07:00,False,Long run,,\n"
        "2026-11-17,2026-11-18,True,Charlie dentist,,\n"
        "2026-12-25,2026-12-26,True,Christmas,,\n"
    )
    return tmp_path


@pytest.fixture
def warehouse(tmp_path):
    path = tmp_path / "test.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE SCHEMA strava; CREATE SCHEMA main_marts")
    con.execute("CREATE TABLE strava.activities (name VARCHAR, is_run BOOLEAN, "
                "start_date TIMESTAMPTZ, distance_miles DOUBLE)")
    con.execute("""INSERT INTO strava.activities VALUES
        ('Morning Run', true,  '2026-11-14 15:00:00+00', 5.2),
        ('Evening Run', true,  '2026-11-12 01:00:00+00', 3.1),  -- Nov 11 in Denver
        ('Bike',        false, '2026-11-13 15:00:00+00', 20.0),
        ('Old Run',     true,  '2026-10-01 15:00:00+00', 6.0)""")
    con.execute("CREATE TABLE main_marts.mart_training_load "
                "(day TIMESTAMP, ctl DOUBLE, atl DOUBLE, tsb DOUBLE, readiness_signal VARCHAR)")
    con.execute("INSERT INTO main_marts.mart_training_load VALUES "
                "('2026-11-14', 13.75, 16.65, -2.9, 'yellow')")
    con.close()
    return path


def test_streak_counts_back_from_yesterday_when_today_not_done():
    done = {TODAY - timedelta(days=1): True, TODAY - timedelta(days=2): True,
            TODAY - timedelta(days=3): False}
    assert _streak(done, TODAY) == 2
    assert _streak({**done, TODAY: True}, TODAY) == 3


def test_snapshot_facts(data, warehouse):
    f = facts(build_snapshot(TODAY, warehouse))

    assert f["running.runs_7d"] == 2              # bike and the October run excluded
    assert f["running.miles_7d"] == 8.3
    assert f["running.last_run_date"] == "Sat Nov 14"
    assert f["training_load.readiness"] == "yellow"

    assert f["habits.meditation_streak"] == 3     # Nov 14, 13, 12; Nov 11 missed
    assert f["habits.done_yesterday"] == ["meditation", "pushups_100"]

    assert f["shows.tonight"] == ["Sun Nov 15: Wild Pink at Bluebird (8:00 PM)"]
    assert f["shows.next_7d"] == ["Wed Nov 18: RJD2 at Ogden (7:30 PM)"]
    assert f["calendar.today"] == ["9:00 AM: Long run"]
    assert f["calendar.next_7d"] == ["Tue Nov 17: Charlie dentist"]


def test_missing_tables_become_errors_not_crashes(data, tmp_path):
    empty = tmp_path / "empty.duckdb"
    duckdb.connect(str(empty)).close()
    snap = build_snapshot(TODAY, empty)
    s = snap["sections"]
    assert s["running"]["error"] and s["goals"]["error"]   # tables don't exist
    assert s["habits"]["error"] is None                     # file-based tools still work
    assert s["shows"]["facts"]["count_30d"] == 2
