"""
/api/secretary: owner-only reads, the heads-up list with queued clicks overlaid, done / dismiss / reopen
through the JSONL log, and what's coming. Temp DuckDB + temp ONS_DATA_DIR; made-up names only.

  uv run --with pytest pytest tests/test_secretary_api.py -q
"""

from __future__ import annotations

import json
from datetime import date, datetime

import duckdb
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from secretary import config as SC
from secretary import headsups as H

CF = {"CF-Connecting-IP": "203.0.113.9"}       # what Cloudflare adds to tunnelled requests
TODAY = date(2026, 12, 2)

TEMPLATES = """
- key: robin_birthday
  name: Robin's birthday
  tier: critical
  person: Robin
  when: "12-12"
- key: towel_day
  name: Towel Day
  tier: trivia
  when: "12-05"
"""
EVENTS = [
    # event_key, source, title, tier, date, is_birthday, template_key, start_at, all_day
    ("tpl:robin_birthday:2026-12-12", "template", "Robin's birthday", "critical", date(2026, 12, 12), True,
     "robin_birthday", None, True),
    ("cal:b:sam", "calendar", "Sam Example", "important", date(2026, 12, 5), True, None, None, True),
    ("cal:p:dentist", "calendar", "Dentist", "nice_to_know", date(2026, 12, 4), False, None,
     datetime(2026, 12, 4, 15, 30, tzinfo=SC.TZ), False),
    ("tpl:towel_day:2026-12-05", "template", "Towel Day", "trivia", date(2026, 12, 5), False, "towel_day", None, True),
]
ROBIN10 = "tpl:robin_birthday:2026-12-12@10"
SAM7 = "cal:b:sam@7"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("ONS_DEV", raising=False)
    monkeypatch.setenv("ONS_WRITE_TOKEN", "sekrit")
    folder = tmp_path / "data" / "secretary"
    (folder / "templates").mkdir(parents=True)
    (folder / "secretary.yaml").write_text("nag_limit: 2\n")
    (folder / "templates" / "t.yaml").write_text(TEMPLATES)
    db_path = tmp_path / "ons.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute("CREATE SCHEMA main_intermediate")
    con.execute("""CREATE TABLE main_intermediate.int_events_tiered (event_key VARCHAR, source VARCHAR,
                   display_title VARCHAR, tier VARCHAR, event_date DATE, is_birthday BOOLEAN, template_key VARCHAR,
                   start_at TIMESTAMPTZ, all_day BOOLEAN)""")
    con.executemany("INSERT INTO main_intermediate.int_events_tiered VALUES (?,?,?,?,?,?,?,?,?)", EVENTS)
    con.close()

    from api.routers import secretary
    monkeypatch.setattr(secretary, "today_local", lambda: TODAY)

    class Env:
        app = None

        def sync(self, day=TODAY):
            """The 4am step: the API is stopped (connection closed) while it writes."""
            if self.app is not None:
                self.app.state.db.close()
            H.refresh(day, cfg=SC.load(), path=db_path, surfaces_today={"paper", "paper_lead", "checkin"},
                      now=datetime(day.year, day.month, day.day, 4, tzinfo=SC.TZ))
            self.client()

        def client(self):
            from api.auth import require_owner
            app = FastAPI()
            app.state.db = duckdb.connect(str(db_path), read_only=True)
            app.include_router(secretary.router, prefix="/api/secretary", dependencies=[Depends(require_owner)])
            self.app, self.http = app, TestClient(app)
            return self.http

        def overview(self):
            r = self.http.get("/api/secretary/overview")
            assert r.status_code == 200, r.text
            return r.json()

        def act(self, hid, action):
            return self.http.post("/api/secretary/headsups/action", json={"headsup_id": hid, "action": action})

        def log(self):
            p = tmp_path / "data" / "secretary" / "headsup_actions.jsonl"
            return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []

    e = Env()
    e.client()
    yield e
    e.app.state.db.close()


# ── privacy ──────────────────────────────────────────────────────────────────

def test_reads_and_writes_need_the_key_through_the_tunnel(env):
    http = env.http
    assert http.get("/api/secretary/overview", headers=CF).status_code == 401
    assert http.get("/api/secretary/overview", headers={**CF, "X-ONS-Write-Token": "wrong"}).status_code == 401
    assert http.get("/api/secretary/overview", headers={**CF, "X-ONS-Write-Token": "sekrit"}).status_code == 200
    assert http.post("/api/secretary/headsups/action", headers=CF,
                     json={"headsup_id": ROBIN10, "action": "done"}).status_code == 401
    assert env.log() == []


# ── reads ────────────────────────────────────────────────────────────────────

def test_before_the_first_sync_the_page_is_empty_not_broken(env):
    o = env.overview()
    assert o["headsups"] == [] and o["configured"] is True and o["nag_limit"] == 2
    assert [u["title"] for u in o["upcoming"]] == ["Dentist", "Sam Example", "Robin's birthday"]   # no trivia


def test_overview_lists_open_headsups_by_tier_with_what_the_paper_showed(env):
    env.sync()
    o = env.overview()
    assert [(h["headsup_id"], h["tier"]) for h in o["headsups"]] == [(ROBIN10, "critical"), (SAM7, "important")]
    robin = o["headsups"][0]
    assert robin["text"] == "Robin's birthday in 10 days (Sat Dec 12): order now if it has to ship."
    assert robin["shown_today"] is True and robin["queued"] is False and robin["days_to_go"] == 10
    dentist = next(u for u in o["upcoming"] if u["title"] == "Dentist")
    assert dentist["time"] == "3:30pm" and dentist["days_to_go"] == 2
    assert o["calendar"]["ok"] is False and "never synced" in o["calendar"]["message"]


def test_nag_limited_headsup_stays_listed_but_not_shown_today(env):
    env.sync(date(2026, 11, 28))
    env.sync(date(2026, 11, 29))
    env.sync(date(2026, 12, 2))
    sam = next(h for h in env.overview()["headsups"] if h["headsup_id"] == SAM7)
    assert sam["shown_count"] == 2 and sam["shown_today"] is False and sam["status"] == "open"


# ── done / dismiss / reopen ──────────────────────────────────────────────────

def test_done_shows_at_once_then_the_sync_makes_it_stick(env):
    env.sync()
    r = env.act(ROBIN10, "done")
    assert r.status_code == 200 and r.json()["status"] == "done"
    assert env.log()[-1]["by"] == "website" and env.log()[-1]["headsup_id"] == ROBIN10

    robin = next(h for h in env.overview()["headsups"] if h["headsup_id"] == ROBIN10)
    assert robin["status"] == "done" and robin["queued"] is True             # overlaid until the sync

    env.sync(date(2026, 12, 3))
    robin = next(h for h in env.overview()["headsups"] if h["headsup_id"] == ROBIN10)
    assert robin["status"] == "done" and robin["queued"] is False            # now in secretary.headsups


def test_dismiss_then_undo(env):
    env.sync()
    assert env.act(SAM7, "dismiss").json()["status"] == "dismissed"
    assert env.act(SAM7, "reopen").json()["status"] == "open"
    sam = next(h for h in env.overview()["headsups"] if h["headsup_id"] == SAM7)
    assert sam["status"] == "open" and sam["queued"] is False                 # back to what the table says


def test_table_from_before_last_action_at_still_reads_and_the_sync_upgrades_it(env, tmp_path):
    env.sync()
    env.app.state.db.close()
    con = duckdb.connect(str(tmp_path / "ons.duckdb"))
    con.execute("ALTER TABLE secretary.headsups DROP COLUMN last_action_at")     # as the first release made it
    con.close()
    env.client()
    assert {h["headsup_id"] for h in env.overview()["headsups"]} == {ROBIN10, SAM7}
    env.act(ROBIN10, "done")
    assert next(h for h in env.overview()["headsups"] if h["headsup_id"] == ROBIN10)["queued"] is True
    env.sync(date(2026, 12, 3))                                                   # adds the column, applies
    robin = next(h for h in env.overview()["headsups"] if h["headsup_id"] == ROBIN10)
    assert robin["status"] == "done" and robin["queued"] is False


def test_unknown_or_bad_action_is_refused(env):
    env.sync()
    assert env.act("cal:nope@3", "done").status_code == 404
    assert env.act(ROBIN10, "snooze").status_code == 422
    assert env.log() == []
