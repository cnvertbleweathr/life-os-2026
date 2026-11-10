"""
/api/progeny: owner-only access (reads too), the JSONL write path, re-read detection, weekly focus.

Writes go to a tmp ONS_DATA_DIR; the marts are small stand-in tables in a tmp DuckDB. Sample kids are fake.
"""

from __future__ import annotations

import json

import duckdb
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

KIDS_YAML = """kids:
  - kid_id: kid1
    display_name: Sample Kid
    birthdate: 2022-06-01
  - kid_id: kid2
    display_name: Baby
    birthdate: null
    due_date: 2027-06-01
"""

CF = {"CF-Connecting-IP": "203.0.113.9"}  # what Cloudflare adds to every tunnelled request


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("ONS_DEV", raising=False)
    monkeypatch.setenv("ONS_WRITE_TOKEN", "sekrit")
    from progeny import store
    store.progeny_dir().mkdir(parents=True, exist_ok=True)
    store.kids_path().write_text(KIDS_YAML)

    db = duckdb.connect(str(tmp_path / "t.duckdb"))
    db.execute("CREATE SCHEMA main_marts")
    db.execute("""CREATE TABLE main_marts.mart_progeny_reading_titles AS
                  SELECT 'kid1' AS kid_id, 'goodnight moon' AS title_key, 'Goodnight Moon' AS title,
                         NULL::VARCHAR AS author, 3 AS times_read, DATE '2026-10-01' AS first_read,
                         DATE '2026-11-01' AS last_read, 1 AS rank_by_reads""")
    db.execute("""CREATE TABLE main_marts.mart_progeny_paths AS
                  SELECT 'kid1' AS kid_id, 'Sample Kid' AS display_name, k AS path_key, k AS path_name, o AS path_order,
                         5 AS total_levels, 1 AS focus_level, 'Lvl' AS focus_level_name, 'a\nb\n' AS focus_activities,
                         false AS is_complete
                  FROM (VALUES ('literacy', 1), ('numeracy', 2), ('music', 3)) t(k, o)""")
    db.execute("""CREATE TABLE main_marts.mart_progeny_kids AS
                  SELECT 'kid1' AS kid_id, 'Sample Kid' AS display_name, DATE '2022-06-01' AS birthdate,
                         NULL::DATE AS due_date, true AS is_born""")

    from api.auth import require_owner
    from api.routers import progeny
    app = FastAPI()
    app.state.db = db
    app.include_router(progeny.router, prefix="/api/progeny", dependencies=[Depends(require_owner)])
    yield TestClient(app)
    db.close()


def _log(kind: str, tmp_env) -> list[dict]:
    from progeny import store
    path = store.progeny_dir() / f"{kind}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


# ── privacy ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", ["/api/progeny/overview", "/api/progeny/timeline", "/api/progeny/options"])
def test_reads_need_the_key_through_the_tunnel(client, path):
    assert client.get(path, headers=CF).status_code == 401
    assert client.get(path, headers={**CF, "X-ONS-Write-Token": "wrong"}).status_code == 401
    assert client.get(path, headers={**CF, "X-ONS-Write-Token": "sekrit"}).status_code == 200
    assert client.get(path).status_code == 200  # local / Tailscale


def test_reads_fail_closed_without_a_server_token(client, monkeypatch):
    monkeypatch.delenv("ONS_WRITE_TOKEN")
    assert client.get("/api/progeny/overview", headers=CF).status_code == 403


def test_writes_need_the_key_through_the_tunnel(client):
    body = {"fields": {"kid": "kid1", "date": "2026-11-01", "quote": "hi"}}
    assert client.post("/api/progeny/quotes", json=body, headers=CF).status_code == 401
    assert _log("quotes", client) == []


# ── writes ───────────────────────────────────────────────────────────────────

def test_post_appends_to_jsonl(client):
    r = client.post("/api/progeny/quotes", json={"fields": {"kid": "kid1", "date": "2026-11-01", "quote": " hi "}})
    assert r.status_code == 200
    [row] = _log("quotes", client)
    assert row["quote"] == "hi" and row["source"] == "web" and len(row["id"]) == 36


def test_post_rejects_bad_input(client):
    assert client.post("/api/progeny/quotes", json={"fields": {"kid": "nobody", "date": "2026-11-01", "quote": "x"}}).status_code == 422
    assert client.post("/api/progeny/milestones", json={"fields": {"kid": "kid1", "milestone_id": "x", "observed_date": "2026-11-01"}}).status_code == 422
    assert client.post("/api/progeny/photos", json={"fields": {}}).status_code == 422


def test_books_flag_rereads_from_warehouse_and_unsynced_log(client):
    post = lambda title: client.post("/api/progeny/books", json={"fields": {"kid": "kid1", "date": "2026-11-02", "title": title}}).json()
    assert post("goodnight  MOON")["repeat"] is True   # in the warehouse already
    assert post("The Snowy Day")["repeat"] is False    # brand new
    assert post("the snowy day")["repeat"] is True     # logged a minute ago, not synced yet


def test_edit_with_entry_id(client):
    t = client.post("/api/progeny/prep_tasks", json={"fields": {"task": "Car seat"}}).json()
    client.post("/api/progeny/prep_tasks", json={"fields": {"task": "Car seat", "done_date": "2026-11-03"}, "entry_id": t["id"]})
    rows = _log("prep_tasks", client)
    assert [r["id"] for r in rows] == [t["id"], t["id"]] and rows[-1]["done_date"] == "2026-11-03"


# ── reads ────────────────────────────────────────────────────────────────────

def test_overview_and_weekly_focus(client):
    o = client.get("/api/progeny/overview").json()
    assert o["configured"] and [k["kid_id"] for k in o["config_kids"]] == ["kid1", "kid2"]
    assert o["kids"][0]["birthdate"] == "2022-06-01"  # dates come back as plain ISO strings
    [focus] = o["focus"]
    from api.store import today_local
    assert focus["path_order"] == today_local().isocalendar().week % 3 + 1
    assert focus["activities"] == ["a", "b"]


def test_missing_marts_read_as_empty(client):
    assert client.get("/api/progeny/timeline").json() == []
    assert client.get("/api/progeny/prep").json() == {"tasks": [], "burndown": []}


def test_weekly_focus_cycles_through_every_path():
    from api.routers.progeny import weekly_focus
    paths = [{"kid_id": "k", "path_order": o, "focus_activities": ""} for o in (2, 1, 3)]
    assert [weekly_focus(paths, w)[0]["path_order"] for w in range(6)] == [1, 2, 3, 1, 2, 3]
