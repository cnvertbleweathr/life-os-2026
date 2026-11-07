"""
Tests for the LED panel (Phase 5): score frames, playlist curation, the
/api/display routes, and the Pi player (with a fake panel and a fake clock).

No network: ESPN and the player's HTTP are faked. Writes go to tmp_path.

  uv run --with pytest pytest tests/test_display.py -q
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api import display  # noqa: E402
from api import film_catalog as fc  # noqa: E402
from api.routers import display as route  # noqa: E402
from film import canvas, motifs, palette  # noqa: E402

spec = importlib.util.spec_from_file_location("ons_display", ROOT / "ops/pi/display/ons_display.py")
player_mod = importlib.util.module_from_spec(spec)
sys.modules["ons_display"] = player_mod
spec.loader.exec_module(player_mod)

NOW = datetime(2026, 11, 7, 23, 30, tzinfo=timezone.utc)   # 4:30 pm in Denver
DARK = palette.tokens("dark")


def game(state="in", away=("ORL", "98"), home=("GS", "104"), detail="8:57 - 2nd", mine="Orlando Magic",
         start="2026-11-08T01:30:00Z", gid="1"):
    side = lambda abbr, score, name: {"id": abbr, "name": name, "abbr": abbr, "logo": None, "score": score}
    return {"id": gid, "league": "nba", "league_label": "NBA", "short_name": f"{away[0]} @ {home[0]}",
            "state": state, "status_detail": detail, "start_utc": start, "my_team": mine,
            "away": side(*away, "Orlando Magic"), "home": side(*home, "Golden State Warriors")}


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("DISPLAY_QUIET_HOURS", raising=False)
    route._frames.clear()
    return tmp_path


# ── frames ───────────────────────────────────────────────────────────────────

def test_score_frame_live_marks_leader_and_live_dot():
    img = display.score_frame(game(), NOW)
    assert img.size == (64, 32)
    px = img.load()
    colours = {px[x, y] for x in range(64) for y in range(32)}
    assert colours <= set(DARK.values())                           # no logos here: palette only
    assert DARK["collar"] in colours                               # the red live dot
    assert DARK["post"] in colours                                 # my team's abbreviation in gold
    away_score = {px[x, y] for x in range(40, 64) for y in range(1, 13)} - {DARK["board"]}
    home_score = {px[x, y] for x in range(40, 64) for y in range(14, 26)} - {DARK["board"]}
    assert away_score == {DARK["white-d"]} and home_score == {DARK["white"]}   # trailing side dims


def test_pre_and_post_status():
    assert display.kickoff(game(state="pre"), NOW) == "6:30P"                     # same Denver day
    assert display.kickoff(game(state="pre", start="2026-11-09T01:20:00Z"), NOW) == "SUN 6:20P"
    assert display.short_status(game(detail="Final/OT")) == "FINAL OT"
    assert display.short_status(game(detail="8:57 - 2nd")) == "8:57 2ND"
    pre = display.score_frame(game(state="pre", away=("ORL", "0"), home=("GS", "0")), NOW)
    assert DARK["collar"] not in set(pre.getdata())
    assert not ({pre.getpixel((x, y)) for x in range(44, 64) for y in range(1, 26)} - {DARK["board"]})   # no scores before tip


def test_text_2x_and_dark_logo_urls():
    fr = canvas.Frame("board")
    display.text_2x(fr, "104", 62, 0, "white")
    lit = [(x, y) for y in range(32) for x in range(64) if fr.get(x, y) == "white"]
    assert max(x for x, _ in lit) == 62 and min(x for x, _ in lit) == 62 - (3 * 8 - 2) + 1
    assert display.dark_variants("https://a.espncdn.com/i/teamlogos/nhl/500/scoreboard/wsh.png") == [
        "https://a.espncdn.com/i/teamlogos/nhl/500-dark/wsh.png", "https://a.espncdn.com/i/teamlogos/nhl/500/scoreboard/wsh.png"]
    assert display.dark_variants("https://x/logo.png") == ["https://x/logo.png"]


def test_idle_frame():
    img = display.idle_frame(NOW)
    assert img.size == (64, 32) and len(set(img.getdata())) > 1


# ── curation ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("spec, hour, expect", [
    ("23-7", 23, True), ("23-7", 3, True), ("23-7", 7, False), ("23-7", 12, False),
    ("1-5", 2, True), ("1-5", 6, False), ("", 2, False), ("junk", 2, False),
])
def test_quiet_hours(spec, hour, expect):
    local = datetime(2026, 11, 7, hour, 0, tzinfo=route.TZ)
    assert route.quiet(local, spec) is expect


FILMS = [{"film_key": f"tmdb:{i}", "title": f"Film {i}", "year": 2000} for i in range(5)]


def test_live_preempts_films():
    pl = route.build(NOW, {"live": [game()], "today": [game(state="pre", gid="2")]}, FILMS)
    assert pl["mode"] == "live" and pl["refresh_s"] == 30
    assert [i["type"] for i in pl["items"]] == ["png"] and pl["items"][0]["seconds"] == route.LIVE_SECONDS


def test_rotation_interleaves_a_card_after_every_two_films():
    cards = {"today": [game(state="pre", gid="2")], "final": [game(state="post", gid="3", detail="Final")]}
    pl = route.build(NOW, cards, FILMS)
    assert pl["mode"] == "rotation"
    assert [i["type"] for i in pl["items"]] == ["gif", "gif", "png", "gif", "gif", "png", "gif"]
    assert pl["items"][0]["url"] == "/api/display/gif/tmdb:0" and pl["items"][0]["seconds"] == 15
    assert route.build(NOW, cards, [])["items"][0]["type"] == "png"            # no films: cards alone


def test_nothing_to_show_is_the_clock_and_quiet_is_off(monkeypatch):
    assert route.build(NOW, {}, [])["mode"] == "idle"
    monkeypatch.setenv("DISPLAY_QUIET_HOURS", "0-23")
    assert route.build(NOW, {"live": [game()]}, FILMS) == {"mode": "off", "refresh_s": 300, "items": []}


def test_films_for_rotates_daily_and_skips_missing_files(env):
    for i in range(3):
        key = f"tmdb:{i}"
        fc.add_suggestion({"film_key": key, "tmdb_id": i, "title": f"F{i}", "year": 1999, "plex_file": None},
                          {"scene_label": "S", "scene_note": "", "timestamp_s": None, "confidence": "low"}, "t")
        fc.approve(key)
        gif = f"film/gifs/tmdb-{i}_matrix.gif"
        if i < 2:   # the third row's file is missing
            canvas.save_gif(canvas.render_frames(motifs.render("F", key), "dark"), env / "data" / gif)
        fc.mark_rendered(key, gif.replace("matrix", "web"), gif)
    today = route.films_for(0)
    assert len(today) == 2 and [r["film_key"] for r in route.films_for(1)] == [r["film_key"] for r in today[1:] + today[:1]]


# ── routes ───────────────────────────────────────────────────────────────────

def test_routes_and_owner_only(env, monkeypatch):
    from api.main import app
    client = TestClient(app)

    async def fake_games(c, now, today):
        return {"live": [], "today": [game(state="pre")], "final": [], "next": [], "ids": {}, "errors": []}
    monkeypatch.setattr(route.espn, "my_games", fake_games)

    pl = client.get("/api/display/playlist").json()
    assert pl["panel"] == {"w": 64, "h": 32} and pl["mode"] == "rotation"
    frame = client.get(pl["items"][0]["url"])
    assert frame.status_code == 200 and Image.open(io.BytesIO(frame.content)).size == (64, 32)
    assert client.get("/api/display/frame/deadbeef.png").status_code == 404
    assert client.get("/api/display/gif/tmdb:1").status_code == 404

    monkeypatch.setenv("ONS_WRITE_TOKEN", "k")
    assert client.get("/api/display/playlist", headers={"CF-Connecting-IP": "1.2.3.4"}).status_code == 401


# ── the Pi player ────────────────────────────────────────────────────────────

class Clock:
    def __init__(self): self.t = 0.0
    def now(self): return self.t
    def sleep(self, s): self.t += s


class Panel:
    def __init__(self): self.shown, self.cleared = [], 0
    def show(self, img): self.shown.append(img.getpixel((0, 0)))
    def clear(self): self.cleared += 1


def png(colour):
    buf = io.BytesIO(); Image.new("RGB", (64, 32), colour).save(buf, "PNG"); return buf.getvalue()


def gif(colours):
    buf = io.BytesIO()
    frames = [Image.new("RGB", (64, 32), c) for c in colours]
    frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:], duration=[130, 120] * (len(frames) // 2), loop=0)
    return buf.getvalue()


def serve(playlists, assets):
    calls = []

    def get(url):
        calls.append(url)
        if url.endswith("/api/display/playlist"):
            nxt = playlists.pop(0) if playlists else None
            if nxt is None:
                raise OSError("connection refused")
            return json.dumps(nxt).encode()
        return assets[url.split(":8000", 1)[1]]
    return get, calls


def test_player_plays_items_for_their_seconds_and_loops_gifs():
    clock, panel = Clock(), Panel()
    pl = {"mode": "rotation", "refresh_s": 600, "items": [
        {"type": "gif", "url": "/g.gif", "seconds": 1},
        {"type": "png", "url": "/s.png", "seconds": 3}]}
    get, calls = serve([pl], {"/g.gif": gif([(255, 0, 0), (0, 0, 255)]), "/s.png": png((0, 255, 0))})
    p = player_mod.Player("http://mini:8000", panel, get=get, sleep=clock.sleep, now=clock.now)
    p.run(once=True)
    reds = panel.shown.count((255, 0, 0)); blues = panel.shown.count((0, 0, 255))
    assert reds == blues == 4                                  # 1 s of a 250 ms loop: 4 passes
    assert panel.shown[-1] == (0, 255, 0) and clock.t == pytest.approx(1 + 3)


def test_player_refetches_at_deadline_and_keeps_last_playlist_when_offline():
    clock, panel = Clock(), Panel()
    pl = {"mode": "live", "refresh_s": 30, "items": [{"type": "png", "url": "/a.png", "seconds": 10}] * 5}
    get, calls = serve([pl, None], {"/a.png": png((1, 2, 3))})
    p = player_mod.Player("http://mini:8000", panel, get=get, sleep=clock.sleep, now=clock.now)
    p.cycle()
    assert clock.t == pytest.approx(30)                        # stopped at the 30 s refresh, not after 50 s
    p.cycle()                                                  # API down: plays the last playlist again
    assert clock.t == pytest.approx(60) and p.playlist == pl
    assert sum(c.endswith("/a.png") for c in calls) == 1       # media cached across cycles


def test_player_off_mode_and_nothing_yet_blank_the_panel():
    clock, panel = Clock(), Panel()
    get, _ = serve([{"mode": "off", "refresh_s": 300, "items": []}], {})
    p = player_mod.Player("http://mini:8000", panel, get=get, sleep=clock.sleep, now=clock.now)
    p.cycle()
    assert panel.cleared == 1 and clock.t == 300 and not panel.shown
    p2 = player_mod.Player("http://mini:8000", Panel(), get=serve([None], {})[0], sleep=clock.sleep, now=clock.now)
    p2.cycle()
    assert p2.panel.cleared == 1


def test_player_cli_emulate(tmp_path, monkeypatch):
    pl = {"mode": "idle", "refresh_s": 60, "items": [{"type": "png", "url": "/c.png", "seconds": 0}]}
    get, _ = serve([pl], {"/c.png": png((9, 9, 9))})
    monkeypatch.setattr(player_mod, "http_get", get)
    assert player_mod.main(["--api", "http://mini:8000", "--emulate", str(tmp_path / "p"), "--once"]) == 0
    assert (tmp_path / "p" / "frame-000001.png").exists() and (tmp_path / "p" / "current.png").exists()
