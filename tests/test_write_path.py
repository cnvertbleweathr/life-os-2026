"""
Tests for the web write path: api/store.py, the habits/check-in/inbox
endpoints, and the pipelines that load their logs into DuckDB.

Everything runs against a temp data dir and a temp DuckDB file, so this is
safe to run on the Mac mini with FastAPI up and the real warehouse in place.

  uv run pytest tests/test_write_path.py -q
"""

from __future__ import annotations

import json
import threading
from datetime import timedelta

import duckdb
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ONS_DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("DLT_DATA_DIR", str(tmp_path / "dlt"))
    monkeypatch.setenv("ONS_TZ", "America/Denver")
    return tmp_path


@pytest.fixture()
def client(env):
    from api.main import app
    # No `with`: lifespan (which opens the real DuckDB) never runs.
    # The write-path routes don't touch DuckDB.
    return TestClient(app)


# ── store ─────────────────────────────────────────────────────────────────────

def test_today_follows_configured_timezone(monkeypatch):
    from api import store
    monkeypatch.setenv("ONS_TZ", "Pacific/Kiritimati")   # UTC+14
    ahead = store.today_local()
    monkeypatch.setenv("ONS_TZ", "Pacific/Pago_Pago")    # UTC-11
    behind = store.today_local()
    assert ahead - behind == timedelta(days=1)


def test_concurrent_appends_never_interleave(env):
    from api.store import JsonlLog
    log = JsonlLog("t", "t.jsonl")

    def write(n):
        for i in range(50):
            log.append({"writer": n, "i": i, "pad": "x" * 2000})

    threads = [threading.Thread(target=write, args=(n,)) for n in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()

    lines = log.path.read_text().splitlines()
    assert len(lines) == 400
    assert all(json.loads(line)["pad"] == "x" * 2000 for line in lines)


def test_corrupt_lines_are_skipped(env):
    from api.store import JsonlLog
    log = JsonlLog("t", "t.jsonl")
    log.append({"date": "2026-10-01", "v": 1})
    with log.path.open("a") as f:
        f.write("{not json\n\n[1,2]\n")
    log.append({"date": "2026-10-01", "v": 2})
    assert log.latest_by("date") == {"2026-10-01": {"date": "2026-10-01", "v": 2}}


# ── habits ────────────────────────────────────────────────────────────────────

def test_habit_toggle_persists_and_latest_wins(client):
    r = client.post("/api/habits/log", json={"habit": "meditation", "done": True})
    assert r.status_code == 200
    assert r.json()["done_count"] == 1

    client.post("/api/habits/log", json={"habit": "pushups_100", "done": True})
    client.post("/api/habits/log", json={"habit": "meditation", "done": False})

    today = client.get("/api/habits/today").json()
    done = {h["key"]: h["done"] for h in today["habits"]}
    assert done == {
        "meditation": False, "pushups_100": True,
        "nonfiction_pages_10": False, "fiction_pages_10": False,
    }


def test_habit_validation(client):
    from api.store import today_local
    tomorrow = (today_local() + timedelta(days=1)).isoformat()
    long_ago = (today_local() - timedelta(days=30)).isoformat()
    assert client.post("/api/habits/log", json={"habit": "juggling", "done": True}).status_code == 422
    assert client.post("/api/habits/log", json={"habit": "meditation", "done": True, "date": tomorrow}).status_code == 422
    assert client.post("/api/habits/log", json={"habit": "meditation", "done": True, "date": long_ago}).status_code == 422
    assert client.post("/api/habits/log", json={"habit": "meditation", "done": True, "date": "10/21/2026"}).status_code == 422


def test_habit_recent_strip_includes_backfill(client):
    from api.store import today_local
    yesterday = (today_local() - timedelta(days=1)).isoformat()
    client.post("/api/habits/log", json={"habit": "fiction_pages_10", "done": True, "date": yesterday})

    strip = client.get("/api/habits/recent?days=21").json()
    assert len(strip) == 21
    assert strip[-1]["date"] == today_local().isoformat()
    assert strip[-2]["date"] == yesterday and strip[-2]["fiction_pages_10"] is True
    assert strip[0]["logged"] is False and strip[0]["done_count"] == 0


def test_streamlit_format_still_reads(client, env):
    """Rows written by the old Streamlit page (naive timestamps) still count."""
    from api.store import HABITS_LOG, today_local
    HABITS_LOG.append({
        "date": today_local().isoformat(), "logged_at": "2026-10-21T08:00:00",
        "meditation": True, "pushups_100": True,
        "nonfiction_pages_10": True, "fiction_pages_10": False,
    })
    assert client.get("/api/habits/today").json()["done_count"] == 3


# ── check-in ──────────────────────────────────────────────────────────────────

GOOD = {"energy": 4, "mood": 5, "focus": 3, "sleep": 4, "soreness": 2, "stress": 1, "note": " long run tomorrow "}


def test_checkin_roundtrip_and_readiness(client):
    assert client.get("/api/checkin/today").json() is None
    r = client.post("/api/checkin/log", json=GOOD)
    assert r.status_code == 200
    body = r.json()
    # (4+5+3+4 + (6-2) + (6-1)) / 30
    assert body["readiness"] == round(25 / 30, 3)
    assert body["note"] == "long run tomorrow"

    resubmit = {**GOOD, "mood": 2}
    client.post("/api/checkin/log", json=resubmit)
    assert client.get("/api/checkin/today").json()["mood"] == 2
    assert len(client.get("/api/checkin/history?days=7").json()) == 1


def test_checkin_rejects_out_of_range(client):
    assert client.post("/api/checkin/log", json={**GOOD, "energy": 0}).status_code == 422
    assert client.post("/api/checkin/log", json={**GOOD, "stress": 6}).status_code == 422
    missing = {k: v for k, v in GOOD.items() if k != "sleep"}
    assert client.post("/api/checkin/log", json=missing).status_code == 422


# ── inbox ─────────────────────────────────────────────────────────────────────

def test_inbox_capture_and_list(client):
    a = client.post("/api/inbox", json={"text": "Try Open-Meteo for run weather", "kind": "idea", "domain": " Fitness "}).json()
    b = client.post("/api/inbox", json={"text": "Renew CFBD token"}).json()
    assert a["status"] == "new" and a["domain"] == "fitness" and len(a["capture_id"]) == 32
    assert b["kind"] == "note" and b["domain"] is None

    items = client.get("/api/inbox").json()
    assert {i["capture_id"] for i in items} == {a["capture_id"], b["capture_id"]}


def test_inbox_validation(client):
    assert client.post("/api/inbox", json={"text": "   "}).status_code == 422
    assert client.post("/api/inbox", json={"text": "x", "kind": "spam"}).status_code == 422


# ── owner guard (public tunnel) ───────────────────────────────────────────────

TUNNEL = {"CF-Connecting-IP": "203.0.113.7"}


def test_local_requests_need_no_key(client, monkeypatch):
    monkeypatch.setenv("ONS_WRITE_TOKEN", "s3cret")
    assert client.post("/api/inbox", json={"text": "from the mac mini"}).status_code == 200


def test_tunnel_fails_closed_without_server_token(client, monkeypatch):
    monkeypatch.delenv("ONS_WRITE_TOKEN", raising=False)
    assert client.post("/api/inbox", json={"text": "x"}, headers=TUNNEL).status_code == 403
    assert client.get("/api/checkin/today", headers=TUNNEL).status_code == 403


def test_tunnel_requires_matching_key(client, monkeypatch):
    monkeypatch.setenv("ONS_WRITE_TOKEN", "s3cret")
    ok = {**TUNNEL, "X-ONS-Write-Token": "s3cret"}
    bad = {**TUNNEL, "X-ONS-Write-Token": "guess"}
    body = {"habit": "meditation", "done": True}

    assert client.post("/api/habits/log", json=body, headers=TUNNEL).status_code == 401
    assert client.post("/api/habits/log", json=body, headers=bad).status_code == 401
    assert client.post("/api/habits/log", json=body, headers=ok).status_code == 200
    # Personal reads are guarded too; public habit reads are not.
    assert client.get("/api/inbox", headers=TUNNEL).status_code == 401
    assert client.get("/api/checkin/history", headers=ok).status_code == 200
    assert client.get("/api/habits/today", headers=TUNNEL).status_code == 200


# ── pipelines → DuckDB ────────────────────────────────────────────────────────

def test_pipelines_load_latest_rows_only(client, env):
    from api.store import today_local
    year = today_local().year

    # Toggle meditation on/off/on: three lines, one day, must count once.
    for done in (True, False, True):
        client.post("/api/habits/log", json={"habit": "meditation", "done": done})
    client.post("/api/checkin/log", json=GOOD)
    client.post("/api/checkin/log", json={**GOOD, "focus": 5})
    client.post("/api/inbox", json={"text": "hello", "kind": "task"})

    from pipelines import checkin_pipeline, habits_pipeline, inbox_pipeline
    habits_pipeline.run(year=year)
    checkin_pipeline.run()
    inbox_pipeline.run()
    inbox_pipeline.run()  # merge must be idempotent

    con = duckdb.connect(str(env / "test.duckdb"), read_only=True)
    summary = dict(con.execute(
        "SELECT habit, done_days FROM habits.habit_summary WHERE year = ?", [year]
    ).fetchall())
    assert summary["meditation"] == 1
    assert con.execute("SELECT count(*) FROM habits.habit_log").fetchone()[0] == 4

    rows = con.execute("SELECT focus, readiness, note FROM checkin.daily_checkin").fetchall()
    assert rows == [(5, round(27 / 30, 3), "long run tomorrow")]

    assert con.execute("SELECT count(*), any_value(kind) FROM raw.capture_inbox").fetchone() == (1, "task")
    con.close()
