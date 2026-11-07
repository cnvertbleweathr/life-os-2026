"""Nosferatu (1922, public domain): the shadow on the stairs.

Ported from docs/film/samples/nosferatu.py to palette roles, so the dark-theme
matrix GIF follows the site's tokens. The shadow climbs from off the left edge
to past the doorway in one loop, so the last frame flows into the first.
The shadow is a shadow, not a character, so it gets no outline.
"""

from __future__ import annotations

from film import FRAMES, H, W
from film.canvas import BAYER4, Frame

BODY = ["..X.XXX.........", "..XXXXXX........", "..XXXXXXX.......", ".XXXXXXXXX......",
        ".XXXXXXXXXX.....", "..XXXXXXXX......", "..XXXXXXX.......", "...XXXXX........",
        "..XXXXXX........", ".XXXXXXXX.......", "XXXXXXXXXX......", "XXXXXXXXX.......",
        "XXXXXXXX........", "XXXXXXXX........", "XXXXXXXX........", ".XXXXXXX........",
        ".XXXXXXX........", ".XXXXXXXX.......", ".XXXXXXXX.......", "XXXXXXXXX......."]
LEGS = [["XXXX..XXX.......", "XXX....XXX......", "XX......XXX.....", "XX.......XX....."],
        ["XXXXXXXX........", ".XXXXXXX........", ".XXX.XXX........", ".XX...XX........"]]


def _line(a, b):
    (x0, y0), (x1, y1) = a, b
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    e, out = dx + dy, []
    while True:
        out.append((x0, y0))
        if (x0, y0) == (x1, y1):
            return out
        e2 = 2 * e
        if e2 >= dy:
            e += dy; x0 += sx
        if e2 <= dx:
            e += dx; y0 += sy


def _arm(k: int):
    pts = []
    for a, b in (((7, 10), (11, 13)), ((11, 13), (13, 10))):
        for x, y in _line(a, b):
            pts += [(x, y), (x, y + 1)]
    tips = [[(18, 7), (18, 10), (17, 13)], [(17, 9), (17, 12), (15, 14)]][k]   # fingers spread / curl
    for t in tips:
        pts += _line((14, 10), t)
    return pts


def _wall(x: int, y: int) -> str:
    d = (x / W) ** 2 * 0.9 + (y / H) ** 2 * 0.5            # light from the top-left
    t = BAYER4[y % 4][x % 4] / 16
    return "ground2" if d > 0.75 + t * 0.35 else "wall-d" if d > 0.25 + t * 0.35 else "wall"


def _rail(x: int) -> int:
    return 30 - int(x * 0.22)


def render() -> list[Frame]:
    frames = []
    for f in range(FRAMES):
        fr = Frame("wall")
        for y in range(H):
            for x in range(W):
                fr.set(x, y, _wall(x, y))
            fr.set(57, y, "ground2"); fr.set(58, y, "wall-d")          # doorway edge
        x0 = round(-18 + 86 * f / FRAMES)
        foot = _rail(x0 + 6) - 2 + (1 if f % 4 < 2 else 0)            # rides above the rail, 1px step bob
        top = foot - 23
        shadow = set()
        for r, row in enumerate(BODY + LEGS[(f // 4) % 2]):
            shadow |= {(x0 + c, top + r) for c, ch in enumerate(row) if ch == "X"}
        shadow |= {(x0 + c, top + r) for c, r in _arm((f // 5) % 2)}
        fr.points(shadow, "outline")
        for x in range(W):                                           # handrail + balusters, in front
            ry = _rail(x)
            fr.set(x, ry, "stand"); fr.set(x, ry + 1, "stand")
            if x % 6 == 2:
                for yy in range(ry + 2, H):
                    fr.set(x, yy, "stand")
        frames.append(fr)
    return frames
