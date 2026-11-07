"""
Tests for the film scene catalog (Phase 2): rules, the approve/edit/reject
flow, /api/film/queue, the suggestion step and the DuckDB mirror.

Everything writes to tmp_path (ONS_DATA_DIR, ONS_DUCKDB_PATH); no network,
no real Claude calls.

  uv run --with pytest pytest tests/test_film_catalog.py -q
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api import film_catalog as fc  # noqa: E402


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


suggest_mod = _load("film_suggest_scenes", "scripts/film_suggest_scenes.py")
cli = _load("film_catalog_cli", "scripts/film_catalog.py")
pipeline = _load("film_catalog_pipeline", "pipelines/film_catalog_pipeline.py")


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ONS_DUCKDB_PATH", str(tmp_path / "ons.duckdb"))
    monkeypatch.setenv("DLT_DATA_DIR", str(tmp_path / "dlt"))
    monkeypatch.setenv("ONS_TZ", "America/Denver")
    return tmp_path


TCSM = {"film_key": "tmdb:30497", "tmdb_id": 30497, "title": "The Texas Chain Saw Massacre",
        "year": 1974, "plex_file": "/movies/tcsm.mkv"}
NOSFERATU = {"film_key": "tmdb:653", "tmdb_id": 653, "title": "Nosferatu", "year": 1922, "plex_file": None}
HEAT = {"film_key": "tmdb:949", "tmdb_id": 949, "title": "Heat", "year": 1995, "plex_file": None}
SCENE = {"scene_label": "Leatherface at the door", "scene_note": "The steel door slams shut",
         "timestamp_s": 1800, "confidence": "high"}


# ── rules ────────────────────────────────────────────────────────────────────

def test_public_domain_moves_with_the_year():
    assert fc.public_domain_through(date(2026, 11, 7)) == 1930
    assert fc.is_public_domain("Anything", 1930, date(2026, 11, 7))
    assert not fc.is_public_domain("Anything", 1931, date(2026, 11, 7))
    assert fc.is_public_domain("Anything", 1931, date(2027, 1, 1))
    assert fc.is_public_domain("Night of the Living Dead", 1968, date(2026, 11, 7))
    assert not fc.is_public_domain("Night of the Living Dead", 1990, date(2026, 11, 7))   # the remake
    assert not fc.is_public_domain("Unknown year", None)


def test_default_render_mode():
    today = date(2026, 11, 7)
    assert fc.default_render_mode("Nosferatu", 1922, "/m/n.mkv", today) == "sprite"   # PD beats having a file
    assert fc.default_render_mode("Heat", 1995, "/m/heat.mkv", today) == "plex_clip"
    assert fc.default_render_mode("Heat", 1995, None, today) == "motif"


# ── catalog flow ─────────────────────────────────────────────────────────────

def test_add_suggestion_sets_mode_and_clip_window():
    row = fc.add_suggestion(TCSM, SCENE, "claude-haiku-5-5")
    assert row["status"] == "suggested" and row["render_mode"] == "plex_clip"
    assert (row["clip_start"], row["clip_end"]) == (1800.0, 1805.0)
    assert row["suggestion_confidence"] == "high" and row["suggested_by"] == "claude-haiku-5-5"

    assert fc.add_suggestion(NOSFERATU, SCENE, "m")["render_mode"] == "sprite"
    motif = fc.add_suggestion(HEAT, None, "m")   # model offered nothing
    assert motif["render_mode"] == "motif" and motif["scene_label"] is None and motif["clip_start"] is None

    with pytest.raises(fc.CatalogError) as e:
        fc.add_suggestion(TCSM, SCENE, "m")
    assert e.value.status == 409


def test_approve_edit_reject_flow_keeps_latest_snapshot():
    fc.add_suggestion(TCSM, SCENE, "m")
    fc.edit("tmdb:30497", {"scene_label": "  The dinner table  ", "clip_start": 4000, "clip_end": 4005})
    row = fc.approve("tmdb:30497")
    assert row["status"] == "approved" and row["approved_at"]
    assert row["scene_label"] == "The dinner table" and row["clip_start"] == 4000

    with pytest.raises(fc.CatalogError) as e:
        fc.approve("tmdb:30497")
    assert e.value.status == 409

    assert fc.reject("tmdb:30497")["status"] == "rejected"
    assert fc.approve("tmdb:30497")["status"] == "approved"   # a rejected row can come back
    assert len(fc.CATALOG_LOG.rows()) == 5 and len(fc.catalog()) == 1   # every change kept, one current row


def test_render_mode_rules_are_enforced():
    fc.add_suggestion(HEAT, SCENE, "m")
    with pytest.raises(fc.CatalogError, match="public domain"):
        fc.edit("tmdb:949", {"render_mode": "sprite"})
    with pytest.raises(fc.CatalogError, match="needs the film's file"):
        fc.edit("tmdb:949", {"render_mode": "plex_clip"})

    fc.add_suggestion(TCSM, SCENE, "m")
    for bad in ({"clip_start": 10, "clip_end": 5}, {"clip_start": 0, "clip_end": 30}, {"clip_start": 5, "clip_end": None}):
        with pytest.raises(fc.CatalogError):
            fc.edit("tmdb:30497", bad)
    # Switching away from plex_clip drops the clip window.
    row = fc.edit("tmdb:30497", {"render_mode": "motif"})
    assert row["clip_start"] is None and row["clip_end"] is None


def test_approve_needs_label_and_clip():
    fc.add_suggestion(HEAT, None, "m")
    with pytest.raises(fc.CatalogError, match="label"):
        fc.approve("tmdb:949")
    assert fc.approve("tmdb:949", {"scene_label": "Rain on the window"})["status"] == "approved"

    fc.add_suggestion(TCSM, {**SCENE, "timestamp_s": None}, "m")
    with pytest.raises(fc.CatalogError, match="clip_start"):
        fc.approve("tmdb:30497")


def test_unknown_film_is_404():
    with pytest.raises(fc.CatalogError) as e:
        fc.approve("tmdb:1")
    assert e.value.status == 404


# ── API ──────────────────────────────────────────────────────────────────────

@pytest.fixture()
def client():
    from api.main import app
    return TestClient(app)   # no `with`: the lifespan (real DuckDB) never runs


def test_api_queue_approve_edit_reject(client):
    fc.add_suggestion(TCSM, SCENE, "m")
    fc.add_suggestion(HEAT, SCENE, "m")
    face_off = fc.add_suggestion({"film_key": "title:face/off:1997", "tmdb_id": None, "title": "Face/Off",
                                  "year": 1997, "plex_file": None}, SCENE, "m")

    assert {r["film_key"] for r in client.get("/api/film/queue").json()} == {"tmdb:30497", "tmdb:949", face_off["film_key"]}

    r = client.patch("/api/film/queue/tmdb:949", json={"scene_note": "Coffee cup steam"})
    assert r.status_code == 200 and r.json()["scene_note"] == "Coffee cup steam"

    r = client.post("/api/film/queue/tmdb:30497/approve", json={"clip_start": 60, "clip_end": 65})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert client.post("/api/film/queue/tmdb:30497/approve").status_code == 409

    assert client.post("/api/film/queue/title:face/off:1997/reject").json()["status"] == "rejected"   # '/' in the key

    assert [r["film_key"] for r in client.get("/api/film/queue").json()] == ["tmdb:949"]
    assert len(client.get("/api/film/queue?status=all").json()) == 3

    r = client.patch("/api/film/queue/tmdb:949", json={"render_mode": "sprite"})
    assert r.status_code == 422 and "public domain" in r.json()["detail"]
    assert client.post("/api/film/queue/tmdb:1/approve").status_code == 404


def test_api_is_owner_only_through_the_tunnel(client, monkeypatch):
    monkeypatch.delenv("ONS_WRITE_TOKEN", raising=False)
    assert client.get("/api/film/queue", headers={"CF-Connecting-IP": "1.2.3.4"}).status_code == 403
    monkeypatch.setenv("ONS_WRITE_TOKEN", "s3cret")
    assert client.get("/api/film/queue", headers={"CF-Connecting-IP": "1.2.3.4"}).status_code == 401
    ok = client.get("/api/film/queue", headers={"CF-Connecting-IP": "1.2.3.4", "X-ONS-Write-Token": "s3cret"})
    assert ok.status_code == 200


# ── CLI ──────────────────────────────────────────────────────────────────────

def test_cli_approve_and_list(capsys):
    fc.add_suggestion(TCSM, SCENE, "m")
    assert cli.main(["approve", "tmdb:30497", "--label", "Hitchhiker", "--clip", "100", "104"]) == 0
    assert fc.get("tmdb:30497")["clip_end"] == 104
    assert cli.main(["edit", "tmdb:30497", "--mode", "sprite"]) == 1
    assert "public domain" in capsys.readouterr().err
    cli.main(["list", "--status", "approved"])
    assert "Hitchhiker" in capsys.readouterr().out


# ── suggestion step ──────────────────────────────────────────────────────────

def fake_suggest(answers):
    calls = []

    def suggest(film):
        calls.append(film["film_key"])
        answer = answers[film["film_key"]]
        if isinstance(answer, Exception):
            raise answer
        return answer, 40, 60, "success" if answer else "refusal"

    suggest.calls = calls
    return suggest


def test_run_writes_rows_logs_costs_and_retries_failures():
    films = [TCSM, HEAT, NOSFERATU]
    suggest = fake_suggest({"tmdb:30497": SCENE, "tmdb:949": RuntimeError("overloaded"), "tmdb:653": None})
    counts = suggest_mod.run(films, suggest, limit=10)

    assert counts == {"suggested": 1, "empty": 1, "failed": 1, "skipped_budget": 0}
    assert set(fc.catalog()) == {"tmdb:30497", "tmdb:653"}   # the failed film gets no row, so it's retried
    assert suggest_mod.films_needing_suggestion(films) == [HEAT]

    log = suggest_mod.GENERATIONS_LOG.rows()
    assert [r["status"] for r in log] == ["success", "error", "refusal"]
    assert log[0]["cost_usd"] == pytest.approx(40 * 0.10e-6 + 60 * 0.50e-6)
    assert log[0]["analyzer_name"] == "film_scene_suggest" and log[0]["model"] == "claude-haiku-5-5"
    assert log[1]["cost_usd"] == 0 and "overloaded" in log[1]["error_message"]


def test_run_respects_limit_and_monthly_budget():
    month = datetime.now().strftime("%Y-%m")
    suggest_mod.GENERATIONS_LOG.append({"timestamp": f"{month}-01T09:00:00", "cost_usd": 4.99})
    suggest_mod.GENERATIONS_LOG.append({"timestamp": "2020-01-01T09:00:00", "cost_usd": 100})   # other month
    assert suggest_mod.month_spend() == pytest.approx(4.99)

    suggest = fake_suggest({"tmdb:30497": SCENE, "tmdb:949": SCENE, "tmdb:653": SCENE})
    assert suggest_mod.run([TCSM, HEAT, NOSFERATU], suggest, limit=2, budget=5.00)["suggested"] == 2
    assert suggest.calls == ["tmdb:30497", "tmdb:949"]

    counts = suggest_mod.run([NOSFERATU], suggest, limit=10, budget=4.99)
    assert counts["skipped_budget"] == 1 and suggest.calls == ["tmdb:30497", "tmdb:949"]


def test_claude_suggest_request_and_parsing():
    sent = {}

    def response(stop_reason, text=None):
        content = [SimpleNamespace(type="text", text=text)] if text else []
        return SimpleNamespace(stop_reason=stop_reason, content=content,
                               usage=SimpleNamespace(input_tokens=55, output_tokens=33))

    class Messages:
        def __init__(self, resp): self.resp = resp
        def create(self, **kw):
            sent.update(kw)
            return self.resp

    ok = SimpleNamespace(messages=Messages(response("end_turn", json.dumps(SCENE))))
    assert suggest_mod.claude_suggest(ok)(TCSM) == (SCENE, 55, 33, "success")
    assert sent["model"] == "claude-haiku-5-5"
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert "The Texas Chain Saw Massacre (1974)" in sent["messages"][0]["content"]

    long = SimpleNamespace(messages=Messages(response("end_turn", json.dumps({**SCENE, "timestamp_s": 9999}))))
    out = suggest_mod.claude_suggest(long)({**TCSM, "duration_ms": 4980000})
    assert out[0]["timestamp_s"] is None   # past the 83-minute runtime: dropped
    assert "Runtime of this copy: 83 min (4980 s)" in sent["messages"][0]["content"]

    refused = SimpleNamespace(messages=Messages(response("refusal")))
    assert suggest_mod.claude_suggest(refused)(TCSM) == (None, 55, 33, "refusal")


def test_watched_films_finds_plex_files(env):
    db = str(env / "ons.duckdb")
    with duckdb.connect(db) as con:
        con.execute("create schema main_marts; create schema main_staging")
        con.execute("""create table main_marts.mart_film_watches as select * from (values
            ('tmdb:30497', 30497, 'The Texas Chain Saw Massacre', 1974, date '2026-10-30'),
            ('tmdb:30497', 30497, 'The Texas Chain Saw Massacre', 1974, date '2025-10-30'),
            ('title:carnival of souls:1962', null, 'Carnival of Souls', 1962, date '2026-11-01'),
            ('tmdb:949', 949, 'Heat', 1995, date '2025-01-07')
        ) t(film_key, tmdb_id, title, film_year, watch_date)""")
        con.execute("""create table main_staging.stg_plex__history as select * from (values
            (30497, 'The Texas Chain Saw Massacre', 1974, '/m/tcsm.mkv', true, 4980000),
            (null, 'Carnival of Souls', 1962, '/m/cos.mkv', true, 4700000),
            (949, 'Heat', 1995, '/m/heat.mkv', false, 10200000)
        ) t(tmdb_id, title, film_year, file_path, in_library, duration_ms)""")

    films = suggest_mod.watched_films(db)
    assert [(f["film_key"], f["plex_file"]) for f in films] == [
        ("title:carnival of souls:1962", "/m/cos.mkv"),   # most recent watch first; matched on title + year
        ("tmdb:30497", "/m/tcsm.mkv"),
        ("tmdb:949", None),                               # file no longer in the library
    ]
    assert [f["duration_ms"] for f in films] == [4700000, 4980000, None]


# ── DuckDB mirror ────────────────────────────────────────────────────────────

def test_pipeline_mirrors_latest_rows(env):
    fc.add_suggestion(TCSM, SCENE, "m")
    fc.add_suggestion(HEAT, None, "m")
    fc.approve("tmdb:30497", {"scene_label": "Final"})
    db = str(env / "ons.duckdb")
    pipeline.run(destination_path=db, pipelines_dir=str(env / "dlt"))
    fc.reject("tmdb:949")
    pipeline.run(destination_path=db, pipelines_dir=str(env / "dlt"))

    with duckdb.connect(db, read_only=True) as con:
        rows = con.sql("select film_key, status, scene_label, clip_start from film.scene_catalog order by 1").fetchall()
    assert rows == [("tmdb:30497", "approved", "Final", 1800.0), ("tmdb:949", "rejected", None, None)]
