"""
YouTube clips for film GIFs: link and time parsing, the catalog rules
(set_youtube_clip, mark_rendered's stale check, mark_failed), rendering through
film.render, and the API's render worker. yt-dlp and ffmpeg are faked; nothing
touches the network.

  uv run --with pytest pytest tests/test_film_youtube.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api import film_catalog as fc  # noqa: E402
from api import film_render_jobs as jobs  # noqa: E402
from film import FRAMES, H, W, clip, youtube  # noqa: E402
from film import render as film_render  # noqa: E402

HEAT = {"film_key": "tmdb:949", "tmdb_id": 949, "title": "Heat", "year": 1995}
LINK = "https://youtu.be/dQw4w9WgXcQ?t=83"
CANON = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path / "data"))
    return tmp_path


@pytest.fixture()
def fake_youtube(monkeypatch):
    seen = {}

    def stream(url, start=None):
        seen.update(url=url, start=start)
        return "https://googlevideo/x", "User-Agent: t\r\n"

    def extract(source, start, headers=None):
        seen.update(source=source, ffmpeg_start=start, headers=headers)
        return np.full((FRAMES, H, W, 3), 120, np.uint8)

    monkeypatch.setattr(youtube, "stream", stream)
    monkeypatch.setattr(clip, "extract_frames", extract)
    return seen


# ── parsing ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,seconds", [
    ("83", 83.0), ("83.5", 83.5), ("1:23", 83.0), ("1:02:03", 3723.0), ("0:05", 5.0),
    ("1m23s", 83.0), ("83s", 83.0), ("1h2m3s", 3723.0), ("2m", 120.0), (" 1:23 ", 83.0), (90, 90.0),
])
def test_parse_time(value, seconds):
    assert youtube.parse_time(value) == seconds


@pytest.mark.parametrize("value", ["1:75", "abc", "1:2:3:4", "-5", "1.2.3"])
def test_parse_time_rejects(value):
    with pytest.raises(ValueError):
        youtube.parse_time(value)


def test_parse_time_blank_is_none():
    assert youtube.parse_time("") is None and youtube.parse_time(None) is None


@pytest.mark.parametrize("url,start", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", None),
    ("https://www.youtube.com/watch?list=PL1&v=dQw4w9WgXcQ&t=1m23s", 83.0),
    ("https://youtu.be/dQw4w9WgXcQ?t=83", 83.0),
    ("https://youtu.be/dQw4w9WgXcQ?si=abc", None),
    ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", None),
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", None),
    ("https://www.youtube.com/embed/dQw4w9WgXcQ?start=42", 42.0),
    ("http://youtube.com/live/dQw4w9WgXcQ", None),
])
def test_parse_url(url, start):
    assert youtube.parse_url(url) == (CANON, start)


@pytest.mark.parametrize("url", [
    "https://vimeo.com/123", "https://www.youtube.com/watch?v=short", "https://www.youtube.com/",
    "youtube.com/watch?v=dQw4w9WgXcQ", "https://evil.com/?u=youtube.com/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com.evil.com/watch?v=dQw4w9WgXcQ", "", "javascript:alert(1)",
])
def test_parse_url_rejects(url):
    with pytest.raises(ValueError):
        youtube.parse_url(url)


def test_friendly_errors():
    assert youtube._friendly("ERROR: [youtube] abc: Private video. Sign in") == "the video is private"
    assert "unavailable" in youtube._friendly("ERROR: [youtube] abc: Video unavailable")
    assert youtube._friendly("ERROR: [youtube] abc: This video is unavailable").startswith("the video is unavailable")
    assert youtube._friendly("ERROR: [youtube] abc: something odd") == "abc: something odd"


# ── catalog ──────────────────────────────────────────────────────────────────

def test_set_clip_creates_an_approved_row_for_a_new_film():
    row = fc.set_youtube_clip(HEAT, LINK, 83)
    assert row["status"] == "approved" and row["render_mode"] == "youtube"
    assert row["youtube_url"] == CANON and (row["clip_start"], row["clip_end"]) == (83.0, 88.0)
    assert row["title"] == "Heat" and row["suggested_by"] == "owner" and row["approved_at"]
    assert fc.get("tmdb:949")["youtube_url"] == CANON


@pytest.mark.parametrize("url,start", [("https://vimeo.com/1", 0), (LINK, -1), (LINK, None)])
def test_set_clip_rejects(url, start):
    with pytest.raises(fc.CatalogError):
        fc.set_youtube_clip(HEAT, url, start)


def test_youtube_rows_are_owner_only():
    fc.set_youtube_clip(HEAT, LINK, 0)
    fc.mark_rendered("tmdb:949", "film/gifs/a.gif", "film/gifs/b.gif")
    row = fc.get("tmdb:949")
    assert fc.is_visible(row, owner=True) and not fc.is_visible(row, owner=False)


def test_repicking_keeps_the_old_gif_until_the_new_one_renders():
    fc.add_suggestion({**HEAT, "plex_file": None}, {"scene_label": "Tarmac"}, "t")
    fc.approve("tmdb:949")
    fc.mark_rendered("tmdb:949", "film/gifs/old_web.gif", "film/gifs/old_matrix.gif")
    row = fc.set_youtube_clip(fc.get("tmdb:949"), LINK, 10)
    assert row["status"] == "approved" and row["gif_web"] == "film/gifs/old_web.gif"
    assert row["scene_label"] == "Tarmac"               # the rest of the row is kept
    assert fc.is_visible(row, owner=True)


def test_stale_render_does_not_mark_rendered():
    fc.set_youtube_clip(HEAT, LINK, 10)
    rendered_from = fc.get("tmdb:949")
    fc.set_youtube_clip(HEAT, LINK, 20)                   # re-picked while it rendered
    with pytest.raises(fc.CatalogError) as e:
        fc.mark_rendered("tmdb:949", "w", "m", source=rendered_from)
    assert e.value.status == 409
    assert fc.get("tmdb:949")["status"] == "approved"


def test_failure_is_recorded_and_cleared():
    fc.set_youtube_clip(HEAT, LINK, 10)
    fc.mark_failed("tmdb:949", "the video is private")
    assert fc.get("tmdb:949")["render_error"] == "the video is private"
    assert fc.get("tmdb:949")["status"] == "approved"
    fc.set_youtube_clip(HEAT, LINK, 12)                   # trying again clears it
    assert fc.get("tmdb:949")["render_error"] is None
    fc.mark_failed("tmdb:949", "boom")
    fc.mark_rendered("tmdb:949", "w", "m")
    assert fc.get("tmdb:949")["render_error"] is None


def test_edit_to_youtube_needs_a_link():
    fc.add_suggestion({**HEAT, "plex_file": None}, {"scene_label": "Tarmac"}, "t")
    with pytest.raises(fc.CatalogError):
        fc.edit("tmdb:949", {"render_mode": "youtube"})
    row = fc.edit("tmdb:949", {"render_mode": "youtube", "youtube_url": LINK, "clip_start": 5})
    assert row["youtube_url"] == CANON


# ── rendering ────────────────────────────────────────────────────────────────

def test_render_youtube_row(env, fake_youtube):
    fc.set_youtube_clip(HEAT, LINK, 83)
    out = film_render.render_and_record(fc.get("tmdb:949"))
    assert out["status"] == "rendered" and out["gif_web"] == "film/gifs/tmdb-949_web.gif"
    assert (env / "data" / out["gif_web"]).exists() and (env / "data" / out["gif_matrix"]).exists()
    assert fake_youtube == {"url": CANON, "start": 83.0, "source": "https://googlevideo/x",
                            "ffmpeg_start": 83.0, "headers": "User-Agent: t\r\n"}
    assert not list((env / "data" / "film" / "gifs").glob(".*"))   # no temp files left behind


def test_failed_rerender_keeps_the_old_files(env, fake_youtube, monkeypatch):
    fc.set_youtube_clip(HEAT, LINK, 83)
    film_render.render_and_record(fc.get("tmdb:949"))
    old = (env / "data" / "film/gifs/tmdb-949_web.gif").read_bytes()
    fc.set_youtube_clip(HEAT, LINK, 90)
    monkeypatch.setattr(youtube, "stream", lambda *a: (_ for _ in ()).throw(clip.ClipError("the video is private")))
    jobs.render_one("tmdb:949")
    row = fc.get("tmdb:949")
    assert row["render_error"] == "the video is private" and row["status"] == "approved"
    assert (env / "data" / row["gif_web"]).read_bytes() == old


def test_worker_renders_and_reports(fake_youtube):
    fc.set_youtube_clip(HEAT, LINK, 83)
    jobs.submit("tmdb:949")
    jobs._q.join()
    assert jobs.state("tmdb:949") is None
    assert fc.get("tmdb:949")["status"] == "rendered"


def test_worker_records_crashes(monkeypatch):
    fc.set_youtube_clip(HEAT, LINK, 83)
    monkeypatch.setattr(film_render, "render_and_record", lambda row: 1 / 0)
    jobs.render_one("tmdb:949")
    assert fc.get("tmdb:949")["render_error"].startswith("render crashed")


def test_sync_script_records_failures(monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("film_gif_render", ROOT / "scripts/film_gif_render.py")
    script = importlib.util.module_from_spec(spec); sys.modules["film_gif_render"] = script
    spec.loader.exec_module(script)
    fc.set_youtube_clip(HEAT, LINK, 83)
    monkeypatch.setattr(youtube, "stream", lambda *a: (_ for _ in ()).throw(clip.ClipError("gone")))
    assert script.main([]) == 1
    assert fc.get("tmdb:949")["render_error"] == "gone"


def test_with_retries_rides_out_403s(monkeypatch):
    monkeypatch.setattr(youtube.time, "sleep", lambda s: None)
    calls = []

    def read():
        calls.append(1)
        if len(calls) < 3:
            raise clip.ClipError("ffmpeg failed: https://rr1.googlevideo.com/x?sig=1 Server returned 403 Forbidden")
        return "frames"

    assert youtube.with_retries(read) == "frames" and len(calls) == 3


def test_with_retries_gives_up_with_a_clean_message(monkeypatch):
    monkeypatch.setattr(youtube.time, "sleep", lambda s: None)
    with pytest.raises(clip.ClipError) as e:
        youtube.with_retries(lambda: (_ for _ in ()).throw(clip.ClipError("https://g/x?sig=1 403 Forbidden")))
    assert "googlevideo" not in str(e.value) and "403" in str(e.value) and "https" not in str(e.value)
    with pytest.raises(clip.ClipError) as e:
        youtube.with_retries(lambda: (_ for _ in ()).throw(clip.ClipError("ffmpeg failed: https://g/x?sig=1 broken")))
    assert str(e.value) == "ffmpeg failed: <stream> broken"
