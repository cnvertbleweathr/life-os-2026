"""
Tests for the public /api/film endpoints (Phase 4): watches, library, scene and
frame strips, including that plex_clip GIFs reach only the owner.

Temp data dir and a temp DuckDB; the app's lifespan (real warehouse) never runs.

  uv run --with pytest pytest tests/test_film_api.py -q
"""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

import duckdb
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api import film_catalog as fc  # noqa: E402

TUNNEL = {"CF-Connecting-IP": "1.2.3.4"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ONS_WRITE_TOKEN", "s3cret")
    con = duckdb.connect(str(tmp_path / "ons.duckdb"))
    con.execute("create schema main_marts")
    con.execute("""create table main_marts.mart_film_watches as select * from (values
        ('w1', 'tmdb:949', 949, 'Heat', 1995, date '2026-10-01', 2026, 'letterboxd', 4.5, true, false, false, 1, 'https://lb/heat', 0, null::timestamptz),
        ('w2', 'tmdb:30497', 30497, 'The Texas Chain Saw Massacre', 1974, date '2026-10-30', 2026, 'both', 5.0, true, false, false, 1, 'https://lb/tcsm', 1, null),
        ('w3', 'tmdb:170', 170, '28 Days Later', 2002, date '2026-10-29', 2026, 'plex', null, false, false, false, 1, null, 1, null)
    ) t(watch_id, film_key, tmdb_id, title, film_year, watch_date, watch_year, source, rating, liked,
        has_review, is_rewatch, watch_number, letterboxd_url, plex_plays, plex_last_viewed_at_utc)""")

    # Heat rendered as a motif (public); 28 Days Later rendered from the owner's copy (private).
    spec = importlib.util.spec_from_file_location("film_gif_render", ROOT / "scripts/film_gif_render.py")
    render = importlib.util.module_from_spec(spec); sys.modules["film_gif_render"] = render; spec.loader.exec_module(render)
    from film import clip, render as film_render
    monkeypatch.setattr(clip, "extract_frames", lambda *a, **k: np.full((40, 32, 64, 3), 90, np.uint8))
    monkeypatch.setattr(film_render, "plex_stream", lambda f: ("http://plex/x", None))
    for key, title, year, plex in (("tmdb:949", "Heat", 1995, None), ("tmdb:170", "28 Days Later", 2002, "/m/28.mkv")):
        fc.add_suggestion({"film_key": key, "tmdb_id": None, "title": title, "year": year, "plex_file": plex},
                          {"scene_label": "Scene", "scene_note": "", "timestamp_s": 480, "confidence": "high"}, "t")
        fc.approve(key)
    assert render.main([]) == 0
    fc.add_suggestion({"film_key": "tmdb:30497", "tmdb_id": 30497, "title": "The Texas Chain Saw Massacre",
                       "year": 1974, "plex_file": None}, None, "t")

    from api.main import app
    app.state.db = con
    yield TestClient(app)
    con.close()


def test_watches_flags_only_visible_gifs(client):
    local = {r["film_key"]: r["gif"] for r in client.get("/api/film/watches").json()}
    assert local == {"tmdb:30497": False, "tmdb:170": True, "tmdb:949": True}
    public = {r["film_key"]: r["gif"] for r in client.get("/api/film/watches", headers=TUNNEL).json()}
    assert public == {"tmdb:30497": False, "tmdb:170": False, "tmdb:949": True}
    assert [r["film_key"] for r in client.get("/api/film/watches").json()][0] == "tmdb:30497"   # newest first


def test_library_hides_plex_clips_from_visitors(client):
    owner = client.get("/api/film/library").json()
    assert {f["film_key"] for f in owner["films"]} == {"tmdb:949", "tmdb:170"}
    assert owner["counts"] == {"suggested": 1, "approved": 0, "rejected": 0, "rendered": 2}
    public = client.get("/api/film/library", headers=TUNNEL).json()
    assert [f["film_key"] for f in public["films"]] == ["tmdb:949"]
    keyed = client.get("/api/film/library", headers={**TUNNEL, "X-ONS-Write-Token": "s3cret"}).json()
    assert len(keyed["films"]) == 2


def test_scene_uses_latest_watch_with_motif_fallback(client):
    scene = client.get("/api/film/scene").json()
    assert scene["film_key"] == "tmdb:30497" and scene["strip"] == "motif" and scene["version"] is None


def test_strips(client):
    r = client.get("/api/film/strip/tmdb:949?theme=dark")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(r.content)).size == (64 * 40, 32)
    assert "public" in r.headers["cache-control"]

    assert client.get("/api/film/strip/tmdb:170?theme=light").status_code == 200
    assert client.get("/api/film/strip/tmdb:170?theme=light", headers=TUNNEL).status_code == 403
    keyed = client.get("/api/film/strip/tmdb:170", headers={**TUNNEL, "X-ONS-Write-Token": "s3cret"})
    assert keyed.status_code == 200 and "private" in keyed.headers["cache-control"]

    motif = client.get("/api/film/strip/tmdb:30497?theme=light&fallback=motif")
    assert motif.status_code == 200 and Image.open(io.BytesIO(motif.content)).size == (64 * 40, 32)
    assert client.get("/api/film/strip/tmdb:30497").status_code == 404
    assert client.get("/api/film/strip/tmdb:1?fallback=motif").status_code == 404


# ── YouTube clips (owner only) ───────────────────────────────────────────────

LINK = "https://youtu.be/dQw4w9WgXcQ?t=83"


@pytest.fixture()
def submitted(monkeypatch):
    from api import film_render_jobs as jobs
    keys = []
    monkeypatch.setattr(jobs, "submit", keys.append)
    return keys


def test_set_clip_for_a_film_with_no_catalog_row(client, submitted, tmp_path):
    con = client.app.state.db
    con.execute("""insert into main_marts.mart_film_watches values
        ('w4', 'tmdb:1700', 1700, 'Misery', 1990, date '2026-10-02', 2026, 'letterboxd', 4.0, false, false, false, 1, null, 0, null)""")
    r = client.put("/api/film/clip/tmdb:1700", json={"youtube_url": LINK, "start": 83})
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "waiting" and r.json()["clip_start"] == 83.0
    assert submitted == ["tmdb:1700"]
    row = fc.get("tmdb:1700")
    assert (row["title"], row["year"], row["status"], row["render_mode"]) == ("Misery", 1990, "approved", "youtube")


def test_set_clip_over_a_rendered_motif_keeps_it_visible(client, submitted):
    r = client.put("/api/film/clip/tmdb:949", json={"youtube_url": LINK, "start": 10})
    assert r.status_code == 200
    watches = {w["film_key"]: w for w in client.get("/api/film/watches").json()}
    assert watches["tmdb:949"]["gif"] is True                       # old motif still up for the owner
    assert watches["tmdb:949"]["clip"]["youtube_url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    public = {w["film_key"]: w for w in client.get("/api/film/watches", headers=TUNNEL).json()}
    assert "clip" not in public["tmdb:949"] and public["tmdb:949"]["gif"] is False   # youtube rows are private


def test_clip_status_states(client, submitted):
    assert client.get("/api/film/clip/tmdb:949").json()["state"] == "done"
    assert client.get("/api/film/clip/tmdb:30497").json()["state"] == "none"   # suggested, not approved
    client.put("/api/film/clip/tmdb:949", json={"youtube_url": LINK, "start": 10})
    fc.mark_failed("tmdb:949", "the video is private")
    s = client.get("/api/film/clip/tmdb:949").json()
    assert s["state"] == "failed" and s["error"] == "the video is private"


def test_set_clip_rejects_bad_input(client, submitted):
    assert client.put("/api/film/clip/tmdb:949", json={"youtube_url": "https://vimeo.com/1", "start": 0}).status_code == 422
    assert client.put("/api/film/clip/tmdb:949", json={"youtube_url": LINK, "start": -1}).status_code == 422
    assert client.put("/api/film/clip/tmdb:nope", json={"youtube_url": LINK, "start": 0}).status_code == 404
    assert submitted == []


def test_set_clip_needs_the_key_from_outside(client, submitted):
    r = client.put("/api/film/clip/tmdb:949", json={"youtube_url": LINK, "start": 0}, headers=TUNNEL)
    assert r.status_code in (401, 403)
    ok = client.put("/api/film/clip/tmdb:949", json={"youtube_url": LINK, "start": 0},
                    headers={**TUNNEL, "X-ONS-Write-Token": "s3cret"})
    assert ok.status_code == 200
