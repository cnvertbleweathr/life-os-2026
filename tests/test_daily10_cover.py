"""Daily 10 vector cover: the date-seeded variation, the text fields, and failing soft."""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import spotify_daily10_cover as C  # noqa: E402


def test_variation_is_stable_and_in_range():
    assert C.variation("2026-11-25") == C.variation("2026-11-25")
    for i in range(60):
        v = C.variation((date(2026, 1, 1) + timedelta(days=i)).isoformat())
        assert C.TILT_MIN <= abs(v["orbit_deg"]) <= C.TILT_MAX
        assert 0 <= v["satellite_deg"] <= 360


def test_tilt_sign_alternates_day_to_day():
    signs = [C.variation((date(2026, 11, 20) + timedelta(days=i)).isoformat())["orbit_deg"] > 0
             for i in range(10)]
    assert all(a != b for a, b in zip(signs, signs[1:]))


def test_orbit_point_halves():
    # 90° is the top of the level orbit (far half, behind the globe); 270° the bottom (near half)
    _, y_top, _, _ = C.orbit_point(90)
    _, y_bottom, _, _ = C.orbit_point(270)
    assert y_top < C.GLOBE_C[1] < y_bottom


def test_headliners_rank_by_plays_then_fill_with_new_artists():
    latest = {"tracks": [{"artist": "Low"}, {"artist": "Gojira"}, {"artist": "Celia Cruz"}, {"artist": "Low"}],
              "tewnidge_artists": ["Celia Cruz"]}
    assert C.headliners(latest, {"gojira": 900, "low": 500}) == ["Gojira", "Low", "Celia Cruz"]
    assert C.headliners(latest, {}) == ["Celia Cruz", "Low", "Gojira"]


def test_fields_and_tick_colours_follow_the_buckets():
    tracks = [{"artist": f"A{i}", "bucket": "A"} for i in range(7)] + \
             [{"artist": f"B{i}", "bucket": "B"} for i in range(3)]
    latest = {"date": "2026-11-25", "tracks": tracks, "bucket_a_count": 7, "bucket_b_count": 3}
    f = C.cover_fields(latest, {})
    assert f["date"] == "2026.11.25 // WED" and f["mix"] == "7 FAMILIAR · 3 NEW"
    assert C.tick_colours(latest) == [C.AMBER] * 7 + [C.ORANGE] * 3


def test_old_pointer_without_counts_still_gets_a_mix():
    latest = {"date": "2026-11-16", "tewnidge_artists": ["a", "b", "c", "d", "e"]}
    assert C.cover_fields(latest, {})["mix"] == "5 FAMILIAR · 5 NEW"
    assert C.tick_colours(latest) == [C.AMBER] * 5 + [C.ORANGE] * 5


@pytest.mark.parametrize("value,expected", [("", "vector"), ("AI", "ai"), ("off", "off"), ("bogus", "vector")])
def test_cover_mode(monkeypatch, value, expected):
    monkeypatch.setenv("COVER_MODE", value)
    assert C.cover_mode() == expected


def test_off_does_nothing(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("COVER_MODE", "off")
    assert C.main(["--sample", "--out", str(tmp_path / "c.jpg")]) == 0
    assert not (tmp_path / "c.jpg").exists() and "COVER_MODE=off" in capsys.readouterr().out


def test_unreachable_vectorcraft_fails_soft(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("COVER_MODE", "vector")
    monkeypatch.setenv("VECTORCRAFT_CLI", str(tmp_path / "no-such-cli"))
    assert C.main(["--sample", "--date", "2026-11-25", "--out", str(tmp_path / "c.jpg")]) == 0
    assert not (tmp_path / "c.jpg").exists()
    assert "cover skipped: VectorCraft render failed" in capsys.readouterr().out


def test_stale_pointer_is_not_recovered(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("COVER_MODE", "vector")
    latest = tmp_path / "daily10_latest.json"
    latest.write_text(json.dumps({"date": "2020-01-01", "playlist_id": "x"}))
    monkeypatch.setattr(C, "LATEST_JSON", latest)
    assert C.main([]) == 0
    assert "not re-covering an old playlist" in capsys.readouterr().out


@pytest.mark.skipif(not Path(C.VectorCraft().cli).exists(), reason="vectorcraft-cli not installed")
def test_live_render_fits_spotify_limit(tmp_path):
    """Needs VectorCraft on this Mac; renders a sample and checks the JPEG and the fitted text."""
    latest = C.sample_latest("2026-11-26")
    data, info = C.render(latest, C.cover_fields(latest, {}), "jpg")
    import base64
    assert data[:3] == b"\xff\xd8\xff" and len(base64.b64encode(data)) <= C.MAX_B64
    assert info["applied"] == 4 and info["skipped"] == 0
    assert info["headliner_size"] >= C.HEADLINER["min_size"]


@pytest.mark.skipif(not Path(C.VectorCraft().cli).exists(), reason="vectorcraft-cli not installed")
def test_live_headliners_drop_to_two_then_truncate():
    import asyncio

    async def fit(names):
        async with C.VectorCraft() as vc:
            await vc.run("document.open", {"path": str(C.TEMPLATE)})
            return await C.fit_headliners(vc, names)

    long = "THE GODSPEED YOU BLACK EMPEROR ORCHESTRAL COLLECTIVE OF MONTREAL"
    text, size = asyncio.run(fit([long, "GOJIRA", "LOW"]))
    assert text.endswith("…") and "LOW" not in text and size == C.HEADLINER["min_size"]
    text, size = asyncio.run(fit(["KING GIZZARD & THE LIZARD WIZARD", "GOJIRA", "CELIA CRUZ"]))
    assert text == "KING GIZZARD & THE LIZARD WIZARD · GOJIRA" and size >= C.HEADLINER["min_size"]
