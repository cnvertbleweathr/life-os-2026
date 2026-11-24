"""
scripts/calendar_export.py: every calendar, a rolling window, a warehouse table,
and a loud "Calendar unavailable today" when Google sign-in fails.

Google is faked; the warehouse is a temp DuckDB file; ONS_DATA_DIR is a temp dir.

  uv run --with pytest pytest tests/test_calendar_export.py -q
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
from datetime import date, datetime
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("calendar_export", ROOT / "scripts" / "calendar_export.py")
CE = importlib.util.module_from_spec(spec)
sys.modules["calendar_export"] = CE
spec.loader.exec_module(CE)

TODAY = date(2026, 11, 27)                      # a Friday
NOW = datetime(2026, 11, 27, 4, 1, tzinfo=CE.TZ)

CALENDARS = [
    {"id": "me@example.com", "summary": "me@example.com", "primary": True},
    {"id": "family123@group.calendar.google.com", "summary": "Family"},
    {"id": CE.BIRTHDAYS_ID, "summary": "Birthdays"},
    {"id": "en.usa#holiday@group.v.calendar.google.com", "summary": "Holidays in United States"},
]
EVENTS = {
    "me@example.com": [
        {"id": "a1", "summary": "!Preschool tour", "start": {"dateTime": "2026-11-30T16:00:00-07:00"},
         "end": {"dateTime": "2026-11-30T17:00:00-07:00"}},
        {"id": "a2", "summary": "Late call", "start": {"dateTime": "2026-12-02T05:30:00Z"},   # 22:30 Dec 1 in Denver
         "end": {"dateTime": "2026-12-02T06:00:00Z"}},
        {"id": "a3", "summary": "Cancelled thing", "status": "cancelled",
         "start": {"date": "2026-12-03"}, "end": {"date": "2026-12-04"}},
        {"id": "b1", "summary": "Sam Example", "eventType": "birthday",
         "start": {"date": "2026-11-28"}, "end": {"date": "2026-11-29"}},
        {"id": "y1", "summary": "DATE NIGHT", "start": {"dateTime": "2026-03-14T18:00:00-06:00"},
         "end": {"dateTime": "2026-03-14T21:00:00-06:00"}},
    ],
    "family123@group.calendar.google.com": [
        {"id": "f1", "summary": "Pie baking", "start": {"date": "2026-11-26"}, "end": {"date": "2026-11-27"}},
    ],
    CE.BIRTHDAYS_ID: [
        {"id": "b2", "summary": "Sam Example", "eventType": "birthday",       # same birthday, other calendar
         "start": {"date": "2026-11-28"}, "end": {"date": "2026-11-29"}},
    ],
    "en.usa#holiday@group.v.calendar.google.com": [
        {"id": "h1", "summary": "Christmas Day", "start": {"date": "2026-12-25"}, "end": {"date": "2026-12-26"}},
    ],
}


class _Call:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return self.result


class FakeService:
    def __init__(self, fail=None):
        self.requests = []
        self.fail = fail

    def calendarList(self):
        svc = self

        class L:
            def list(self, **kw):
                return _Call({"items": CALENDARS})
        return L()

    def events(self):
        svc = self

        class E:
            def list(self, **kw):
                if svc.fail:
                    raise svc.fail
                svc.requests.append(kw)
                return _Call({"items": EVENTS.get(kw["calendarId"], [])})
        return E()


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("ONS_PHONE_NOTIFICATIONS", raising=False)
    return tmp_path


def events_table(db):
    con = duckdb.connect(str(db), read_only=True)
    try:
        return con.execute("SELECT calendar_kind, title, start_date, all_day FROM calendar.events "
                           "ORDER BY start_date, title").fetchall()
    finally:
        con.close()


def test_fetches_every_calendar_with_a_rolling_window(env):
    svc = FakeService()
    CE.fetch_all(svc, TODAY, 2026)
    by_cal = {r["calendarId"]: r for r in svc.requests}
    assert set(by_cal) == {c["id"] for c in CALENDARS}                 # all four, birthdays included
    fam = by_cal["family123@group.calendar.google.com"]
    assert fam["timeMin"] == "2026-11-20T07:00:00Z"                    # 7 days back, Denver midnight
    assert fam["timeMax"] == "2027-01-27T07:00:00Z"                    # through 60 days ahead
    prim = by_cal["me@example.com"]
    assert prim["timeMin"] == "2026-01-01T07:00:00Z" and prim["timeMax"] == "2027-01-27T07:00:00Z"
    assert all(r["singleEvents"] for r in svc.requests)               # recurring events expanded


def test_rows_tag_birthdays_drop_cancelled_and_use_denver_dates(env):
    rows = CE.to_rows(CE.fetch_all(FakeService(), TODAY, 2026), NOW)
    by_title = {}
    for r in rows:
        by_title.setdefault(r["title"], []).append(r)
    assert "Cancelled thing" not in by_title
    assert len(by_title["Sam Example"]) == 1 and by_title["Sam Example"][0]["calendar_kind"] == "birthdays"
    assert by_title["Christmas Day"][0]["calendar_kind"] == "holidays"
    assert by_title["Late call"][0]["start_date"] == date(2026, 12, 1)   # UTC Dec 2 is Denver Dec 1
    assert by_title["!Preschool tour"][0]["title"] == "!Preschool tour"  # the "!" is the tier's job


def test_success_writes_warehouse_status_and_primary_csv(env, capsys):
    db = env / "ons.duckdb"
    code = CE.run(lambda: FakeService(), today=TODAY, year=2026, now=NOW, warehouse=db)
    assert code == 0
    rows = events_table(db)
    assert ("birthdays", "Sam Example", date(2026, 11, 28), True) in rows
    assert ("other", "Pie baking", date(2026, 11, 26), True) in rows
    status = json.loads((env / "data" / "calendar" / "status.json").read_text())
    assert status["ok"] and status["calendars"] == 4 and status["window"] == ["2026-11-20", "2027-01-26"]
    csv_text = (env / "data" / "calendar" / "processed" / "events_clean_2026.csv").read_text()
    assert "DATE NIGHT" in csv_text and "Pie baking" not in csv_text      # primary only, for calendar_metrics
    assert "Cancelled thing" not in csv_text
    assert CE.read_status(TODAY)["ok"]


def test_expired_sign_in_says_calendar_unavailable_and_keeps_yesterdays_table(env, capsys, monkeypatch):
    db = env / "ons.duckdb"
    assert CE.run(lambda: FakeService(), today=TODAY, year=2026, now=NOW, warehouse=db) == 0
    pushed = []
    monkeypatch.setattr(CE, "_notify_reauth", lambda m: pushed.append(m) if os.getenv("ONS_PHONE_NOTIFICATIONS") == "1" else None)

    def expired():
        raise CE.AuthRequired("Google sign-in expired or was revoked (invalid_grant)")
    code = CE.run(expired, today=TODAY, year=2026, now=NOW, warehouse=db)
    assert code == 2
    last_line = capsys.readouterr().err.strip().splitlines()[-1]          # what health.txt shows
    assert last_line.startswith("✗ Calendar unavailable today: Google sign-in expired")
    assert "--auth" in last_line
    status = CE.read_status(TODAY)
    assert not status["ok"] and status["message"].startswith("Calendar unavailable today")
    assert status["last_ok_at"] == NOW.isoformat(timespec="seconds")
    assert len(events_table(db)) > 0                                      # previous events kept
    assert pushed == []                                                   # no phone push by default


def test_phone_push_is_opt_in_only(monkeypatch):
    sent = []
    fake = type(sys)("notify")
    fake.send = lambda *a, **k: sent.append(a) or True
    monkeypatch.setitem(sys.modules, "notify", fake)
    monkeypatch.delenv("ONS_PHONE_NOTIFICATIONS", raising=False)
    CE._notify_reauth("x")
    assert sent == []
    monkeypatch.setenv("ONS_PHONE_NOTIFICATIONS", "1")
    CE._notify_reauth("x")
    assert len(sent) == 1


def test_api_error_is_reported_not_silent(env, capsys):
    code = CE.run(lambda: FakeService(fail=RuntimeError("503 backend")), today=TODAY, year=2026, now=NOW,
                  warehouse=env / "ons.duckdb")
    assert code == 1
    assert "Calendar unavailable today: Google Calendar API error" in capsys.readouterr().err
    assert not CE.read_status(TODAY)["ok"]


def test_a_sync_that_did_not_run_today_counts_as_unavailable(env):
    CE.run(lambda: FakeService(), today=TODAY, year=2026, now=NOW, warehouse=env / "ons.duckdb")
    tomorrow = CE.read_status(date(2026, 11, 28))
    assert not tomorrow["ok"] and "hasn't synced since 2026-11-27" in tomorrow["message"]
    (env / "data" / "calendar" / "status.json").unlink()
    assert CE.read_status(TODAY)["message"] == "the calendar has never synced"


def test_token_is_saved_owner_only(tmp_path):
    class Creds:
        def to_json(self):
            return "{}"
    path = tmp_path / "secrets" / "token.json"
    CE._save(Creds(), str(path))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_paper_says_calendar_unavailable(env, monkeypatch):
    from agents.morning_brief import print_edition as P
    edition = json.loads((ROOT / "tests" / "fixtures" / "morning_brief" / "edition_sample.json").read_text())
    edition.pop("_comment", None)
    edition["date"] = TODAY.isoformat()
    result = {"status": "published", "edition": edition}
    CE.write_status(False, "Calendar unavailable today: Google sign-in expired or was revoked (invalid_grant).", NOW)
    page = P.render_html(result)
    assert "Calendar unavailable today: Google sign-in expired" in page
    CE.write_status(True, "ok", NOW)
    assert "Calendar unavailable" not in P.render_html(result)


def test_daily_sync_runs_calendar_every_day():
    src = (ROOT / "scripts" / "daily_sync.py").read_text()
    block = src[src.index('name="calendar_export"'):src.index('name="calendar_metrics"')]
    assert "run_on_days" not in block
