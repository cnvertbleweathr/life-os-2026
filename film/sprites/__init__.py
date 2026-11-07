"""render_mode "sprite": hand-built pixel scenes, one module per film.

Only films in the US public domain get a sprite (api/film_catalog.py enforces
it), so the scene can be recreated faithfully. Each module exposes
render() -> list[Frame] (40 frames, roles from the --px-* palette).

To add one: write film/sprites/<slug>.py and register it below by
(lower-case title, release year).
"""

from __future__ import annotations

from typing import Callable

from film.canvas import Frame
from film.sprites import nosferatu

REGISTRY: dict[tuple[str, int], Callable[[], list[Frame]]] = {
    ("nosferatu", 1922): nosferatu.render,
}


def find(title: str | None, year: int | None) -> Callable[[], list[Frame]] | None:
    if not title or not year:
        return None
    return REGISTRY.get((title.strip().lower(), int(year)))
