"""Frames drawn in palette roles, written out as the two GIFs.

A Frame holds one --px-* role name per pixel. The same frames become gif_web
(light tokens) and gif_matrix (dark tokens), so a scene is drawn once and
follows the site's theme colours.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image

from film import H, W, font
from film.palette import RGB, colour

BAYER4 = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))


class Frame:
    def __init__(self, ground: str, w: int = W, h: int = H):
        self.w, self.h = w, h
        self.px = [[ground] * w for _ in range(h)]

    def set(self, x: int, y: int, role: str) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y][x] = role

    def get(self, x: int, y: int) -> str | None:
        return self.px[y][x] if 0 <= x < self.w and 0 <= y < self.h else None

    def rect(self, x: int, y: int, w: int, h: int, role: str) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.set(xx, yy, role)

    def points(self, pts: Iterable[tuple[int, int]], role: str) -> None:
        for x, y in pts:
            self.set(x, y, role)

    def outlined(self, pts: set[tuple[int, int]], fill: str, outline: str = "outline") -> None:
        """A character: `pts` in `fill` with a generated 1px outer outline (DESIGN.md)."""
        ring = {(x + dx, y + dy) for x, y in pts for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))} - pts
        self.points(ring, outline)
        self.points(pts, fill)

    def text(self, text: str, x: int, y: int, role: str) -> None:
        self.points(((x + dx, y + dy) for dx, dy in font.pixels(text)), role)

    def text_centered(self, text: str, y: int, role: str) -> None:
        self.text(text, (self.w - font.width(text)) // 2, y, role)

    def roles(self) -> set[str]:
        return {r for row in self.px for r in row}


def to_image(frame: Frame, theme: str) -> Image.Image:
    im = Image.new("RGB", (frame.w, frame.h))
    rgb: dict[str, RGB] = {r: colour(r, theme) for r in frame.roles()}
    im.putdata([rgb[r] for row in frame.px for r in row])
    return im


def frame_durations(n: int) -> list[int]:
    """GIF stores delays in hundredths of a second, so 125 ms can't be written
    exactly (it rounds to 120 ms and the loop runs 4.8 s). Alternating 130/120 ms
    averages 125 ms and keeps the loop at exactly n × 125 ms."""
    return [130 if i % 2 == 0 else 120 for i in range(n)]


def save_gif(images: list[Image.Image], path: Path, scale: int = 1) -> Path:
    """An infinite 125 ms-per-frame loop (see frame_durations). scale > 1 is for
    previews only (nearest neighbour). Pillow merges identical consecutive frames
    and adds their delays together, so a file can hold fewer than 40 frames; the
    loop is still 5 s."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if scale > 1:
        images = [im.resize((im.width * scale, im.height * scale), Image.NEAREST) for im in images]
    # optimize=False and disposal=1 keep every pixel exact, frame after frame
    images[0].save(path, save_all=True, append_images=images[1:], duration=frame_durations(len(images)),
                   loop=0, optimize=False, disposal=1)
    return path


def render_frames(frames: list[Frame], theme: str) -> list[Image.Image]:
    return [to_image(f, theme) for f in frames]
