"""The closed pixel palette: --px-* tokens from web/app/globals.css, both themes.

gif_web uses the light theme; gif_matrix uses the dark theme, since on an LED
panel black is "off" and a dark ground looks right and draws less power.
Reading the CSS keeps the GIFs in step with the site's scenes when a token
changes.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "web" / "app" / "globals.css"
THEMES = ("light", "dark")

RGB = tuple[int, int, int]


def _hex(value: str) -> RGB:
    v = value.lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def _block(css: str, selector_pattern: str) -> str:
    m = re.search(selector_pattern + r"\s*\{", css)
    if not m:
        raise ValueError(f"globals.css has no block matching {selector_pattern!r}")
    depth, i = 1, m.end()
    while depth:
        depth += {"{": 1, "}": -1}.get(css[i], 0)
        i += 1
    return css[m.end():i - 1]


@lru_cache(maxsize=None)
def tokens(theme: str, css_path: str = str(CSS)) -> dict[str, RGB]:
    """{'outline': (29, 34, 48), ...} for 'light' or 'dark' (names without '--px-')."""
    css = Path(css_path).read_text()
    selector = r':root,\s*\[data-theme="light"\]' if theme == "light" else r'\[data-theme="dark"\]'
    body = _block(css, selector)
    return {name: _hex(val) for name, val in re.findall(r"--px-([\w-]+)\s*:\s*(#[0-9a-fA-F]{3,6})", body)}


def colour(role: str, theme: str) -> RGB:
    try:
        return tokens(theme)[role]
    except KeyError:
        raise KeyError(f"no --px-{role} token in the {theme} theme") from None
