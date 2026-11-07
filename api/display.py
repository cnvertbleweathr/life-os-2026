"""
api/display.py: 64×32 frames for the LED panel (Phase 5 of docs/film/ONS_FILM_SECTION_PLAN.md).

Score frames for my teams' games, drawn with the same 3×5 font and --px-*
palette as the film GIFs, in the dark theme (on an LED panel black is "off").

  ┌──────────────────────────────────────────────────────────────┐
  │ [logo] ORL                                              98   │   away
  │ [logo] GS                                              104   │   home
  │                    ● 8:57 2ND                                │   status
  └──────────────────────────────────────────────────────────────┘

Logos: the ESPN PNG each game already carries (the site's NHL and MLS logo
sets are SVG, which nothing on the Mac mini can rasterize), in ESPN's
dark-background variant where there is one, downscaled to 12×12 once and
cached under data/display/logos/.

The idle frame is the date and time, for when there's nothing else to show.
"""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from PIL import Image

from api.store import data_dir
from film import font
from film.canvas import Frame, to_image

W, H = 64, 32
LOGO = 12
TZ = ZoneInfo("America/Denver")


# ── text ─────────────────────────────────────────────────────────────────────

def text_2x(frame: Frame, text: str, right: int, y: int, role: str) -> None:
    """3×5 glyphs doubled (6×10), right-aligned so the last pixel lands on `right`."""
    text = font.normalise(text)
    width = len(text) * 8 - 2
    x0 = right - width + 1
    for dx, dy in font.pixels(text):
        gx, gy = x0 + (dx // font.ADVANCE) * 8 + (dx % font.ADVANCE) * 2, y + dy * 2
        frame.rect(gx, gy, 2, 2, role)


def short_status(game: dict) -> str:
    """ESPN's shortDetail made to fit 15 glyphs: '8:57 - 2nd' → '8:57 2ND', 'Final/OT' → 'FINAL OT'."""
    s = (game.get("status_detail") or "").replace(" - ", " ").replace("/", " ")
    return font.normalise(s)[:15].strip()


def kickoff(game: dict, now: datetime) -> str:
    """'7:00P' today, 'SUN 7:00P' later this week (America/Denver)."""
    start = datetime.fromisoformat(str(game["start_utc"]).replace("Z", "+00:00")).astimezone(TZ)
    clock = start.strftime("%-I:%M") + ("A" if start.hour < 12 else "P")
    if start.date() == now.astimezone(TZ).date():
        return clock
    return f"{start.strftime('%a').upper()} {clock}"


# ── logos ────────────────────────────────────────────────────────────────────

def dark_variants(url: str) -> list[str]:
    """ESPN serves a dark-background version of each logo under /500-dark/
    (dark navy marks like Washington's otherwise vanish on an LED panel's black).
    Try it first, then the logo as given."""
    if "/500/" in url:
        dark = url.replace("/500/scoreboard/", "/500-dark/").replace("/500/", "/500-dark/")
        return [dark, url]
    return [url]


def _logo_path(league: str, team_id: str) -> Path:
    return data_dir() / "display" / "logos" / f"{league}-{team_id}.png"


async def ensure_logos(client: httpx.AsyncClient, games: list[dict]) -> None:
    """Download and shrink any logo not already cached. Failures leave no file (the frame shows the abbreviation only)."""
    for g in games:
        for side in ("away", "home"):
            team = g[side]
            path = _logo_path(g["league"], team["id"])
            if path.exists() or not team.get("logo"):
                continue
            try:
                resp = None
                for url in dark_variants(team["logo"]):         # ESPN's dark-background logo reads on a black panel
                    r = await client.get(url, timeout=10, follow_redirects=True)
                    if r.status_code == 200:
                        resp = r
                        break
                if resp is None:
                    continue
                im = Image.open(io.BytesIO(resp.content)).convert("RGBA")
                im.thumbnail((LOGO, LOGO), Image.LANCZOS)
                path.parent.mkdir(parents=True, exist_ok=True)
                im.save(path)
            except Exception:
                continue


def _paste_logo(img: Image.Image, league: str, team_id: str, x: int, y: int) -> bool:
    path = _logo_path(league, team_id)
    if not path.exists():
        return False
    logo = Image.open(path).convert("RGBA")
    ox, oy = x + (LOGO - logo.width) // 2, y + (LOGO - logo.height) // 2
    img.paste(logo, (ox, oy), logo)
    return True


# ── frames ───────────────────────────────────────────────────────────────────

def score_frame(game: dict, now: datetime) -> Image.Image:
    """One game: away over home, scores on the right, status along the bottom."""
    fr = Frame("board")
    state = game.get("state")
    scores = [game[s].get("score") for s in ("away", "home")]
    leader = None
    if state in ("in", "post") and all(s not in (None, "") for s in scores):
        a, h = (int(float(s)) for s in scores)
        leader = "away" if a > h else "home" if h > a else None
    mine = set((game.get("my_team") or "").split(" / "))

    for row, side in enumerate(("away", "home")):
        team, y = game[side], 1 + row * 13
        name_role = "post" if team.get("name") in mine else "white"     # my team's abbreviation in gold
        fr.text(font.normalise(team.get("abbr") or "")[:4], 15, y + 4, name_role)
        score = team.get("score")
        if state in ("in", "post") and score not in (None, ""):
            role = "white" if leader in (None, side) else "white-d"     # the trailing side dims
            text_2x(fr, str(int(float(score))), W - 2, y + 1, role)

    if state == "in":
        status, role = short_status(game) or "LIVE", "white"
    elif state == "post":
        status, role = short_status(game) or "FINAL", "white-d"
    else:
        status, role = kickoff(game, now), "white"
    width = font.width(status)
    x = (W - width) // 2 + (2 if state == "in" else 0)
    fr.text(status, x, H - 6, role)
    if state == "in":
        fr.rect(x - 4, H - 5, 2, 2, "collar")                          # the red live dot

    img = to_image(fr, "dark")
    for row, side in enumerate(("away", "home")):
        _paste_logo(img, game["league"], game[side]["id"], 1, 1 + row * 13)
    return img


def idle_frame(now: datetime) -> Image.Image:
    """Date and time, for when there's no film and no game."""
    local = now.astimezone(TZ)
    fr = Frame("board")
    fr.text_centered(font.normalise(local.strftime("%a %b %-d")), 7, "white-d")
    clock = local.strftime("%-I:%M")
    text_2x(fr, clock, (W + len(clock) * 8 - 2) // 2 - 1, 15, "white")
    return to_image(fr, "dark")


def png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
