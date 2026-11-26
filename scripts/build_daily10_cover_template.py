#!/usr/bin/env python3
"""
Build the Daily 10 cover template in VectorCraft (headless, over MCP) and save it
to assets/templates/daily10_cover.vectorcraft.

    uv run python scripts/build_daily10_cover_template.py

640×640 artboard in the ONS cover palette: a vector redraw of the ONS globe
stamp (the PNG logo is green on cream paper, which reads as a pale box on the
dark ground), a terminal frame, and four named text objects that
spotify_daily10_cover.py fills each run, each bound to a VectorCraft text
variable of the same name:

    date · title · headliners · mix

The orbit is two named groups, drawn level, that the renderer fills and tilts:
`orbit_back` (the far half, under the globe) and `orbit_front` (the near half,
over the globe but under the ONS plate). Track ticks and the satellite go into
whichever half they fall on. Stacking, bottom to top:

    background · grid · frame · top bar · orbit_back · globe · orbit_front · plate · text

Fonts: Alfa Slab One / Josefin Sans / Share Tech Mono aren't installed, so
Rockwell / Futura / JetBrains Mono stand in (owner's choice, Nov 2026).
"""
from __future__ import annotations

import asyncio
import base64
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vectorcraft_client import VectorCraft  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "templates" / "daily10_cover.vectorcraft"

SIZE = 640
BG, SECONDARY, CYAN, ORANGE, AMBER, CREAM = "#061820", "#0a2a36", "#4db8d4", "#c8501a", "#ffcc44", "#e8dcc8"
HEADLINE, LABEL, DATA = ("Rockwell", "Bold"), ("Futura", "Medium"), ("JetBrains Mono", "Regular")

# Globe geometry, shared with spotify_daily10_cover.py (it imports these).
S = 0.92                          # the globe group at 92% of the first draft
GLOBE_C = (320.0, 222.0)          # globe centre; the orbit tilts about it
GLOBE_RX, GLOBE_RY = 140.0 * S, 100.0 * S
RING_RX, RING_RY = 186.0 * S, 132.0 * S
ORBIT_A, ORBIT_B = 238.0 * S, 54.0 * S
HEADLINER = {"x": 44, "y": 512, "w": SIZE - 88, "h": 34, "size": 22, "min_size": 16, "tracking": 80}
GRID_STEP = 40

SAMPLE = {"date": "2026.11.25 // WED", "title": "DAILY 10",
          "headliners": "KING GIZZARD · GOJIRA · CELIA CRUZ", "mix": "5 FAMILIAR · 5 NEW"}


async def shape(vc: VectorCraft, **kw) -> int:
    return (await vc.tool("draw_shape", kw))["id"]


async def path(vc: VectorCraft, d: str, *, stroke: str, width: float, fill: str = "none") -> int:
    return (await vc.tool("draw_path", {"d": d, "stroke": stroke, "strokeWidth": width, "fill": fill}))["id"]


async def group(vc: VectorCraft, ids: list[int], name: str) -> int:
    await vc.run("select.set", {"ids": ids})
    gid = (await vc.run("object.group"))["id"]
    await vc.run("object.setProps", {"id": gid, "name": name})
    return gid


async def text(vc: VectorCraft, name: str, value: str, *, font: tuple[str, str], size: float, color: str,
               x: float, y: float, w: float, h: float, justify: str = "center", tracking: int = 0,
               fit: str = "none", fit_min: int = 55) -> int:
    tid = (await vc.run("text.create", {
        "x": x, "y": y, "text": value, "size": size, "font": font[0], "style": font[1], "color": color,
        "area": {"width": w, "height": h, "fit": fit, **({"fitMinPercent": fit_min} if fit == "shrinkText" else {})},
    }))["id"]
    await vc.run("text.setStyle", {"id": tid, "justify": justify, "tracking": tracking})
    await vc.run("object.setProps", {"id": tid, "name": name})
    return tid


def ring_point(deg: float, rx: float, ry: float) -> tuple[float, float]:
    """A point on an ellipse about the globe centre; deg counter-clockwise from 3 o'clock, y down."""
    cx, cy = GLOBE_C
    return cx + rx * math.cos(math.radians(deg)), cy - ry * math.sin(math.radians(deg))


async def build(vc: VectorCraft) -> None:
    await vc.run("file.new", {"name": "daily10_cover", "width": SIZE, "height": SIZE, "units": "Pixels"})
    cx, cy = GLOBE_C

    bg = await shape(vc, shape="rectangle", x=0, y=0, width=SIZE, height=SIZE, fill=BG, stroke="none")
    await vc.run("object.setProps", {"id": bg, "name": "background", "locked": True})
    lines = []
    for v in range(0, SIZE + 1, GRID_STEP):
        lines.append(await shape(vc, shape="line", x1=v, y1=0, x2=v, y2=SIZE, stroke=SECONDARY, strokeWidth=1))
        lines.append(await shape(vc, shape="line", x1=0, y1=v, x2=SIZE, y2=v, stroke=SECONDARY, strokeWidth=1))
    await group(vc, lines, "grid")

    # terminal frame + amber corner brackets
    frame = await shape(vc, shape="rectangle", x=18, y=18, width=SIZE - 36, height=SIZE - 36,
                        fill="none", stroke=CYAN, strokeWidth=1.5)
    await vc.run("object.setProps", {"id": frame, "opacity": 55})
    k, a, b = 26, 12, SIZE - 12
    brackets = [await path(vc, d, stroke=AMBER, width=3) for d in (
        f"M{a} {a + k} L{a} {a} L{a + k} {a}", f"M{b - k} {a} L{b} {a} L{b} {a + k}",
        f"M{a} {b - k} L{a} {b} L{a + k} {b}", f"M{b - k} {b} L{b} {b} L{b} {b - k}")]
    await group(vc, [frame, *brackets], "frame")

    # top bar
    await text(vc, "date", SAMPLE["date"], font=DATA, size=16, color=CYAN, x=40, y=38, w=300, h=26,
               justify="left")
    await text(vc, "label", "ONS · AUDIO TERMINAL", font=LABEL, size=11, color=CREAM, x=330, y=42,
               w=270, h=20, justify="right", tracking=220)
    rule = await shape(vc, shape="line", x1=40, y1=70, x2=SIZE - 40, y2=70, stroke=CYAN, strokeWidth=1)
    await vc.run("object.setProps", {"id": rule, "opacity": 40})

    # orbit, far half (drawn level; the renderer adds ticks and the satellite, then tilts it)
    back = await path(vc, f"M{cx - ORBIT_A} {cy} A{ORBIT_A} {ORBIT_B} 0 0 1 {cx + ORBIT_A} {cy}",
                      stroke=AMBER, width=2)
    await group(vc, [back], "orbit_back")

    # globe stamp (vector redraw of app/static/ons_logo.png), at S scale
    ring = await shape(vc, shape="ellipse", x=cx - RING_RX, y=cy - RING_RY, width=2 * RING_RX, height=2 * RING_RY,
                       fill="none", stroke=CYAN, strokeWidth=3)
    globe = await shape(vc, shape="ellipse", x=cx - GLOBE_RX, y=cy - GLOBE_RY, width=2 * GLOBE_RX,
                        height=2 * GLOBE_RY, fill=SECONDARY, stroke=CYAN, strokeWidth=4.6)
    parts = [ring, globe]
    for w in (190 * S, 84 * S):    # meridians
        parts.append(await shape(vc, shape="ellipse", x=cx - w / 2, y=cy - GLOBE_RY, width=w,
                                 height=2 * GLOBE_RY, fill="none", stroke=CYAN, strokeWidth=3.2))
    parts.append(await shape(vc, shape="line", x1=cx, y1=cy - GLOBE_RY, x2=cx, y2=cy + GLOBE_RY,
                             stroke=CYAN, strokeWidth=3.2))
    for dy in (-78 * S, -44 * S, 44 * S, 78 * S):   # latitudes, clipped to the globe's outline
        half = GLOBE_RX * math.sqrt(1 - (dy / GLOBE_RY) ** 2) - 3
        parts.append(await shape(vc, shape="line", x1=cx - half, y1=cy + dy, x2=cx + half, y2=cy + dy,
                                 stroke=CYAN, strokeWidth=3.2))
    # the stamp's arrow: outside the ring across the top, where a ±32° orbit never reaches
    arx, ary = RING_RX + 14, RING_RY + 14
    (x0, y0), (x1, y1) = ring_point(124, arx, ary), ring_point(72, arx, ary)
    parts.append(await path(vc, f"M{x0:.1f} {y0:.1f} A{arx:.1f} {ary:.1f} 0 0 1 {x1:.1f} {y1:.1f}",
                            stroke=AMBER, width=3.5))
    # head: a triangle pointing along the arc's tangent at its end (clockwise on screen)
    t = math.radians(72)
    tx, ty = arx * math.sin(t), ary * math.cos(t)          # d/d(-deg) of ring_point, y down
    n = math.hypot(tx, ty)
    ux, uy = tx / n, ty / n
    tip = (x1 + ux * 12, y1 + uy * 12)
    left = (x1 - uy * 8, y1 + ux * 8)
    right = (x1 + uy * 8, y1 - ux * 8)
    parts.append(await path(vc, f"M{tip[0]:.1f} {tip[1]:.1f} L{left[0]:.1f} {left[1]:.1f} "
                                f"L{right[0]:.1f} {right[1]:.1f} Z", stroke="none", width=0, fill=AMBER))
    await group(vc, parts, "globe")

    # orbit, near half: over the globe
    front = await path(vc, f"M{cx + ORBIT_A} {cy} A{ORBIT_A} {ORBIT_B} 0 0 1 {cx - ORBIT_A} {cy}",
                       stroke=AMBER, width=2)
    await group(vc, [front], "orbit_front")

    # nameplate, always on top of the orbit
    pw, ph = 184 * S, 64 * S
    px, py = cx - pw / 2, cy - ph / 2
    plate = await shape(vc, shape="rectangle", x=px, y=py, width=pw, height=ph, radius=9,
                        fill=BG, stroke=CYAN, strokeWidth=3.7)
    rivets = [await shape(vc, shape="ellipse", x=rx - 2.8, y=ry - 2.8, width=5.6, height=5.6, fill=CYAN,
                          stroke="none")
              for rx in (px + 10, px + pw - 10) for ry in (py + 10, py + ph - 10)]
    ons = await text(vc, "ons", "ONS", font=HEADLINE, size=40, color=CYAN, x=px, y=py + 6, w=pw, h=52,
                     tracking=60)
    await group(vc, [plate, *rivets, ons], "plate")

    # fill-in text
    await text(vc, "title", SAMPLE["title"], font=HEADLINE, size=96, color=AMBER, x=20, y=396, w=SIZE - 40,
               h=112, tracking=20)
    h = HEADLINER
    await text(vc, "headliners", SAMPLE["headliners"], font=LABEL, size=h["size"], color=CREAM, x=h["x"],
               y=h["y"], w=h["w"], h=h["h"], tracking=h["tracking"], fit="shrinkText",
               fit_min=math.ceil(100 * h["min_size"] / h["size"]))
    div = await shape(vc, shape="line", x1=250, y1=558, x2=390, y2=558, stroke=ORANGE, strokeWidth=2)
    await vc.run("object.setProps", {"id": div, "name": "divider"})
    await text(vc, "mix", SAMPLE["mix"], font=DATA, size=17, color=ORANGE, x=40, y=570, w=SIZE - 80, h=28,
               tracking=60)

    for name in SAMPLE:   # bind the fill-in objects to text variables of the same names
        hits = (await vc.run("document.find", {"name": name, "kind": "Type"}))["matches"]
        if not hits:
            raise SystemExit(f"text object {name!r} not found after building")
        await vc.run("variable.define", {"name": name, "kind": "text"})
        await vc.run("variable.bind", {"variable": name, "ids": [hits[0]["id"]]})
    await vc.run("select.none")


async def main() -> int:
    async with VectorCraft() as vc:
        await build(vc)
        for f in await vc.run("text.fonts", {}):
            print(f"font {f['family']} {f['style']}: {f['status']}"
                  + ("" if f["status"] == "exact" else f" → {f['resolved']}"))
        print("variables:", await vc.run("variable.list", {}))
        saved = await vc.run("file.saveCopy", {"format": "vectorcraft"})
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_bytes(base64.b64decode(saved["dataBase64"]))
        print(f"saved {OUT} ({OUT.stat().st_size} bytes)", saved.get("warnings") or "")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
