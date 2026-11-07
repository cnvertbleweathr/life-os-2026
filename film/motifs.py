"""render_mode "motif": an original mood loop with the film's title in the
3×5 font. The fallback for films with no Plex file and no public-domain scene.

Three loops, each exactly 40 frames and seamless (every moving thing travels a
whole number of cycles in 40 frames):
  rain        rain running down a window, the title on the sill
  projector   a flickering projector beam with drifting dust, the title on the screen
  vhs         a paused tape with a tracking band rolling down through the title

The motif is picked from the film_key, so a film always gets the same one.
"""

from __future__ import annotations

import zlib

from film import FRAMES, H, W
from film.canvas import BAYER4, Frame
from film import font

MOTIFS = ("rain", "projector", "vhs")


def pick(film_key: str) -> str:
    return MOTIFS[zlib.crc32(film_key.encode()) % len(MOTIFS)]


def _seeded(film_key: str, n: int, salt: str) -> list[int]:
    """n stable pseudo-random ints for this film (positions, phases)."""
    out, seed = [], zlib.crc32((salt + film_key).encode())
    for _ in range(n):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        out.append(seed >> 8)
    return out


def _title(frame: Frame, lines: list[str], top: int, role: str) -> None:
    for i, line in enumerate(lines):
        frame.text_centered(line, top + i * (font.HEIGHT + 1), role)


def rain(title: str, film_key: str) -> list[Frame]:
    lines = font.wrap(title, 15)
    sill_top = H - (len(lines) * (font.HEIGHT + 1) + 3)
    drops = [(r % (W - 4) + 2, r % H, 1 + r % 2) for r in _seeded(film_key, 26, "rain")]   # x, y0, speed cycles
    frames = []
    for f in range(FRAMES):
        fr = Frame("sky-o")
        for y in range(sill_top):                                  # glass: lighter towards the top-left
            for x in range(W):
                if (x + y * 2) / (W + 2 * sill_top) < 0.45 - BAYER4[y % 4][x % 4] / 40:
                    fr.set(x, y, "cloud-o")
        fr.rect(0, 0, W, 2, "wood"); fr.rect(0, 0, 2, sill_top, "wood"); fr.rect(W - 2, 0, 2, sill_top, "wood")
        fr.rect(W // 2 - 1, 0, 2, sill_top, "wood-d")              # the window's centre bar
        for x, y0, cycles in drops:                                # each drop falls `cycles` window heights per loop
            y = (y0 + f * cycles * sill_top // FRAMES) % sill_top
            fr.set(x, y, "rain"); fr.set(x, y - 1, "rain")
            if cycles == 2:
                fr.set(x, y - 2, "rain")                           # faster drops leave a longer streak
        fr.rect(0, sill_top, W, H - sill_top, "wood")
        fr.rect(0, sill_top, W, 1, "wood-d")
        _title(fr, lines, sill_top + 2, "white")
        frames.append(fr)
    return frames


def projector(title: str, film_key: str) -> list[Frame]:
    lines = font.wrap(title, 9, 3)
    sx, sw = 26, W - 28                                            # the screen
    flicker = [0, 0, 1, 0, 0, 0, 1, 1, 0, 0]                       # 10-frame pattern, 4 repeats
    motes = [(r % 22 + 4, r % 18 + 6) for r in _seeded(film_key, 7, "dust")]
    frames = []
    for f in range(FRAMES):
        fr = Frame("board")
        dim = flicker[f % len(flicker)]
        for x in range(4, sx):                                     # the beam widens from the lens to the screen
            half = 1 + (x - 4) * 11 // (sx - 4)
            for y in range(16 - half, 16 + half + 1):
                if dim and BAYER4[y % 4][x % 4] < 6:
                    continue                                       # a dimmer frame drops some beam pixels
                fr.set(x, y, "glow")
        fr.rect(0, 13, 4, 7, "stand"); fr.rect(3, 15, 2, 3, "lamp")   # the projector and its lens
        fr.rect(sx, 3, sw, H - 6, "white-d" if dim else "white")
        for i, (mx, my) in enumerate(motes):                       # dust drifts right, one beam length per loop
            x = 4 + (mx + f * (sx - 4) // FRAMES) % (sx - 4)
            y = my + (1 if (f + i * 5) % 20 < 10 else 0)
            if fr.get(x, y) == "glow":
                fr.set(x, y, "lamp")
        top = 3 + (H - 6 - (len(lines) * (font.HEIGHT + 1) - 1)) // 2
        for i, line in enumerate(lines):
            fr.text(line, sx + (sw - font.width(line)) // 2, top + i * (font.HEIGHT + 1), "outline")
        frames.append(fr)
    return frames


def vhs(title: str, film_key: str) -> list[Frame]:
    lines = font.wrap(title, 15)
    band = 6
    noise = _seeded(film_key, 64, "noise")
    frames = []
    for f in range(FRAMES):
        base = Frame("navy")
        base.text("PLAY", 3, 3, "white")
        base.rect(W - 9, 3, 2, 5, "white"); base.rect(W - 6, 3, 2, 5, "white")   # pause bars
        _title(base, lines, 13, "white")
        base.text("SP", 3, H - 8, "white-d")
        fr = Frame("navy")
        top = (f * (H + band)) // FRAMES - band                    # rolls from above the top to below the bottom
        for y in range(H):
            shift = (2 if (y - top) % 2 else -1) if top <= y < top + band else 0
            for x in range(W):
                fr.set(x, y, base.get((x - shift) % W, y))
            if top <= y < top + band:                              # snow in the tracking band
                for k in range(6):
                    fr.set(noise[(y * 7 + k + f * 3) % len(noise)] % W, y, "white-d" if k % 2 else "navy-d")
        frames.append(fr)
    return frames


RENDERERS = {"rain": rain, "projector": projector, "vhs": vhs}


def render(title: str, film_key: str, motif: str | None = None) -> list[Frame]:
    return RENDERERS[motif or pick(film_key)](title, film_key)
