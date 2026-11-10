"""
Tests for the film GIF renderer (Phase 3): palette, font, motifs, sprites,
the clip quantizer, and scripts/film_gif_render.py end to end.

Everything writes to tmp_path; no ffmpeg or Plex calls (the clip source is faked).

  uv run --with pytest pytest tests/test_film_render.py -q
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageSequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api import film_catalog as fc  # noqa: E402
from film import FRAMES, H, W, canvas, clip, font, motifs, palette, sprites  # noqa: E402
from film import render as film_render  # noqa: E402

spec = importlib.util.spec_from_file_location("film_gif_render", ROOT / "scripts/film_gif_render.py")
render = importlib.util.module_from_spec(spec)
sys.modules["film_gif_render"] = render
spec.loader.exec_module(render)


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ONS_DUCKDB_PATH", str(tmp_path / "ons.duckdb"))
    monkeypatch.delenv("PLEX_MEDIA_PATH_MAP", raising=False)
    return tmp_path


def gif_frames(path: Path) -> list[Image.Image]:
    """Every 125 ms frame, re-expanding frames Pillow merged."""
    out = []
    for f in ImageSequence.Iterator(Image.open(path)):
        out += [f.convert("RGB")] * max(1, round(f.info["duration"] / 125))
    return out


# ── palette / font ───────────────────────────────────────────────────────────

def test_palette_reads_both_themes_from_globals_css():
    light, dark = palette.tokens("light"), palette.tokens("dark")
    assert light["outline"] == (0x1d, 0x22, 0x30) and dark["outline"] == (0x07, 0x09, 0x0d)
    assert set(light) == set(dark) and len(light) > 50


def test_font_wraps_titles():
    assert font.wrap("The Texas Chain Saw Massacre", 15) == ["TEXAS CHAIN SAW", "MASSACRE"]
    assert font.wrap("Heat", 15) == ["HEAT"]
    assert font.wrap("Amélie", 15) == ["AMELIE"]
    assert all(len(line) <= 9 for line in font.wrap("Pearl: An X-traordinary Origin Story", 9, 3))
    assert font.width("HEAT") == 15


# ── frames ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("motif", motifs.MOTIFS)
def test_motifs_are_40_frame_seamless_loops_in_the_palette(motif):
    frames = motifs.render("Blade Runner 2049", "tmdb:335984", motif)
    assert len(frames) == FRAMES and all((f.w, f.h) == (W, H) for f in frames)
    roles = set().union(*(f.roles() for f in frames))
    assert roles <= set(palette.tokens("light"))
    assert len({str(f.px) for f in frames}) > 10              # it moves (sub-pixel speeds repeat some frames)
    # Seamless: re-rendering "frame 40" would equal frame 0, so the step 39 → 0 is a normal step.
    assert sum(a != b for a, b in zip(sum(frames[39].px, []), sum(frames[0].px, []))) < W * H // 4


def test_motif_pick_is_stable():
    assert motifs.pick("tmdb:949") == motifs.pick("tmdb:949")
    assert {motifs.pick(f"tmdb:{i}") for i in range(30)} == set(motifs.MOTIFS)


def test_nosferatu_sprite_registered_and_loops():
    scene = sprites.find("Nosferatu", 1922)
    assert scene is not None and sprites.find("Nosferatu", 2024) is None
    frames = scene()
    assert len(frames) == FRAMES
    shadow = lambda f: sum(r.count("outline") for r in f.px)
    # enters from the left (fingertips first) and has left by the last frame
    assert shadow(frames[0]) < 5 and shadow(frames[39]) == 0 and shadow(frames[20]) > 100


def test_outline_rule():
    fr = canvas.Frame("sky")
    fr.outlined({(5, 5), (6, 5)}, "team")
    assert fr.get(5, 5) == "team" and fr.get(4, 5) == "outline" and fr.get(5, 4) == "outline"
    assert fr.get(4, 4) == "sky"   # 4-connected ring only


def test_save_gif_loops_5_seconds(tmp_path):
    frames = motifs.render("Heat", "tmdb:949", "vhs")
    path = canvas.save_gif(canvas.render_frames(frames, "dark"), tmp_path / "x.gif")
    im = Image.open(path)
    durations = [f.info["duration"] for f in ImageSequence.Iterator(im)]
    assert sum(durations) == 5000 and im.info["loop"] == 0
    assert im.size == (W, H) and len(gif_frames(path)) == FRAMES


# ── clip ─────────────────────────────────────────────────────────────────────

def test_quantize_uses_only_theme_tokens_and_dithers():
    gradient = np.zeros((2, H, W, 3), np.uint8)
    gradient[..., :] = np.linspace(0, 255, W, dtype=np.uint8)[None, None, :, None]
    for theme in ("light", "dark"):
        out = clip.quantize(gradient, theme)
        allowed = set(palette.tokens(theme).values())
        used = {tuple(p) for im in out for p in np.asarray(im).reshape(-1, 3)}
        assert used <= allowed and len(used) > 3


def test_local_path_mapping(tmp_path, monkeypatch):
    real = tmp_path / "Movies" / "Heat.mkv"
    real.parent.mkdir(); real.write_bytes(b"x")
    assert clip.local_path("/mnt/media/Movies/Heat.mkv") is None
    monkeypatch.setenv("PLEX_MEDIA_PATH_MAP", f"/mnt/media={tmp_path}")
    assert clip.local_path("/mnt/media/Movies/Heat.mkv") == str(real)


# ── the script ───────────────────────────────────────────────────────────────

def approved(film, mode_fix=None, **edits):
    fc.add_suggestion(film, {"scene_label": "A scene", "scene_note": "", "timestamp_s": 100, "confidence": "high"}, "t")
    return fc.approve(film["film_key"], edits)


NOSFERATU = {"film_key": "tmdb:653", "tmdb_id": 653, "title": "Nosferatu", "year": 1922, "plex_file": None}
METROPOLIS = {"film_key": "tmdb:19", "tmdb_id": 19, "title": "Metropolis", "year": 1927, "plex_file": None}
HEAT = {"film_key": "tmdb:949", "tmdb_id": 949, "title": "Heat", "year": 1995, "plex_file": None}
TCSM = {"film_key": "tmdb:30497", "tmdb_id": 30497, "title": "The Texas Chain Saw Massacre", "year": 1974,
        "plex_file": "/mnt/media/tcsm.mkv"}


def test_render_all_approved(env, monkeypatch):
    approved(NOSFERATU); approved(HEAT); approved(METROPOLIS); approved(TCSM)
    fake = np.full((FRAMES, H, W, 3), 128, np.uint8)
    seen = {}

    def fake_extract(source, start, headers=None):
        seen.update(source=source, start=start, headers=headers)
        return fake

    monkeypatch.setattr(clip, "extract_frames", fake_extract)
    monkeypatch.setattr(film_render, "plex_stream", lambda f: ("http://plex/library/parts/1/file.mkv", "X-Plex-Token: t\r\n"))

    assert render.main([]) == 0
    cat = fc.catalog()
    assert cat["tmdb:653"]["status"] == "rendered" and cat["tmdb:949"]["status"] == "rendered"
    assert cat["tmdb:30497"]["status"] == "rendered"
    assert cat["tmdb:19"]["status"] == "approved"           # PD, but no sprite written yet: skipped, not failed
    assert seen == {"source": "http://plex/library/parts/1/file.mkv", "start": 100.0, "headers": "X-Plex-Token: t\r\n"}

    for key in ("tmdb:653", "tmdb:949", "tmdb:30497"):
        for field in ("gif_web", "gif_matrix"):
            path = env / "data" / cat[key][field]
            assert path.exists() and len(gif_frames(path)) == FRAMES
    assert cat["tmdb:949"]["gif_web"] == "film/gifs/tmdb-949_web.gif"

    # Nothing left to render; a re-run is a no-op.
    assert render.main([]) == 0 and len(fc.CATALOG_LOG.rows()) == 4 * 2 + 3


def test_edit_after_render_requeues(env):
    approved(HEAT)
    render.main([])
    assert fc.get("tmdb:949")["status"] == "rendered"
    row = fc.edit("tmdb:949", {"scene_label": "Coffee shop"})
    assert row["status"] == "approved" and row["gif_web"] is None
    assert render.main([]) == 0 and fc.get("tmdb:949")["status"] == "rendered"


def test_clip_failure_keeps_row_approved_and_exits_1(env, monkeypatch):
    approved(TCSM)
    monkeypatch.setattr(film_render, "plex_stream", lambda f: (_ for _ in ()).throw(clip.ClipError("Plex is down")))
    assert render.main([]) == 1
    assert fc.get("tmdb:30497")["status"] == "approved"


def test_preview_only_writes_nothing_to_catalog(env, tmp_path):
    approved(HEAT)
    assert render.main(["--film", "tmdb:949", "--mode", "motif", "--preview", str(tmp_path / "prev"), "--no-write"]) == 0
    assert (tmp_path / "prev" / "tmdb-949_web@8x.gif").exists()
    assert Image.open(tmp_path / "prev" / "tmdb-949_web@8x.gif").size == (W * 8, H * 8)
    assert fc.get("tmdb:949")["status"] == "approved"
    assert not (env / "data" / "film" / "gifs").exists()


def test_force_rules(env):
    approved(HEAT)
    render.main([])
    assert render.main(["--film", "tmdb:949"]) == 1             # rendered: needs --force
    assert render.main(["--film", "tmdb:949", "--force"]) == 0
