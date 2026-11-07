"""The 3×5 pixel font of the title scenes (px.js), extended to the full
alphabet for film titles. Glyphs advance 4px (3 + 1 space)."""

from __future__ import annotations

GLYPHS: dict[str, tuple[str, ...]] = {
    "0": ("111", "101", "101", "101", "111"), "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"), "3": ("111", "001", "011", "001", "111"),
    "4": ("101", "101", "111", "001", "001"), "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"), "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"), "9": ("111", "101", "111", "001", "111"),
    "A": ("010", "101", "111", "101", "101"), "B": ("110", "101", "110", "101", "110"),
    "C": ("011", "100", "100", "100", "011"), "D": ("110", "101", "101", "101", "110"),
    "E": ("111", "100", "110", "100", "111"), "F": ("111", "100", "110", "100", "100"),
    "G": ("011", "100", "101", "101", "011"), "H": ("101", "101", "111", "101", "101"),
    "I": ("111", "010", "010", "010", "111"), "J": ("001", "001", "001", "101", "010"),
    "K": ("101", "101", "110", "101", "101"), "L": ("100", "100", "100", "100", "111"),
    "M": ("101", "111", "111", "101", "101"), "N": ("110", "101", "101", "101", "101"),
    "O": ("010", "101", "101", "101", "010"), "P": ("110", "101", "110", "100", "100"),
    "Q": ("010", "101", "101", "110", "011"), "R": ("110", "101", "110", "101", "101"),
    "S": ("011", "100", "010", "001", "110"), "T": ("111", "010", "010", "010", "010"),
    "U": ("101", "101", "101", "101", "111"), "V": ("101", "101", "101", "101", "010"),
    "W": ("101", "101", "111", "111", "101"), "X": ("101", "101", "010", "101", "101"),
    "Y": ("101", "101", "010", "010", "010"), "Z": ("111", "001", "010", "100", "111"),
    "-": ("000", "000", "111", "000", "000"), "!": ("010", "010", "010", "000", "010"),
    ".": ("000", "000", "000", "000", "010"), ",": ("000", "000", "000", "010", "100"),
    "'": ("010", "010", "000", "000", "000"), ":": ("000", "010", "000", "010", "000"),
    "&": ("010", "101", "010", "101", "011"), "?": ("110", "001", "010", "000", "010"),
    "/": ("001", "001", "010", "100", "100"), " ": ("000", "000", "000", "000", "000"),
}
ADVANCE, HEIGHT = 4, 5


def normalise(text: str) -> str:
    """Upper-case, unknown characters dropped (accents folded where simple)."""
    import unicodedata
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "".join(c for c in folded.upper() if c in GLYPHS)


def width(text: str) -> int:
    return max(len(text) * ADVANCE - 1, 0)


def wrap(title: str, max_chars: int, max_lines: int = 2) -> list[str]:
    """Word-wrap a title into at most `max_lines` lines of `max_chars`; a word
    that doesn't fit is cut. A leading 'THE ' is dropped first if that helps."""
    text = normalise(title).strip()
    if len(text) > max_chars and text.startswith("THE "):
        text = text[4:]
    lines: list[str] = []
    for word in text.split():
        word = word[:max_chars]
        if lines and len(lines[-1]) + 1 + len(word) <= max_chars:
            lines[-1] += " " + word
        elif len(lines) < max_lines:
            lines.append(word)
        else:
            break
    return lines


def pixels(text: str) -> list[tuple[int, int]]:
    """(x, y) offsets of the lit pixels for `text` (already normalised)."""
    out = []
    for i, ch in enumerate(text):
        for y, row in enumerate(GLYPHS[ch]):
            out += [(i * ADVANCE + x, y) for x, bit in enumerate(row) if bit == "1"]
    return out
