"""Render one catalog row's two GIFs and record them.

Shared by the 9:00 sync (scripts/film_gif_render.py renders every approved
row) and the API (api/film_render_jobs.py renders a YouTube clip the moment
the owner saves it). Each film makes two GIFs, 64×32 art pixels, 40 frames ×
125 ms, looping:
  data/film/gifs/<film>_web.gif      light-theme --px-* palette, for the site
  data/film/gifs/<film>_matrix.gif   dark-theme palette, for the LED panel

Files are written beside their final path and renamed into place, so a reader
never sees half a GIF and a failed render leaves the old one intact.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from api import film_catalog as fc
from api.store import data_dir
from film import canvas, clip, motifs, sprites, youtube

ROOT = Path(__file__).resolve().parents[1]
GIF_DIR = Path("film") / "gifs"   # relative to the data dir

# What a render can fail with that is the film's problem, not a bug: recorded
# on the row as render_error, shown on /film.
FAILURES = (clip.ClipError, fc.CatalogError, OSError)


class Skip(Exception):
    """Not renderable yet, and not an error (e.g. no sprite written for this film)."""


def slug(film_key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", film_key.lower()).strip("-")[:80]


def db_path() -> str:
    return os.getenv("ONS_DUCKDB_PATH", str(ROOT / "data" / "warehouse" / "ons.duckdb"))


def plex_stream(plex_file: str) -> tuple[str, str]:
    """(url, ffmpeg headers) streaming `plex_file` from the Plex server."""
    import duckdb
    from pipelines.plex_pipeline import PlexClient

    url, token = os.getenv("PLEX_URL", "").strip(), os.getenv("PLEX_TOKEN", "").strip()
    if not url or not token:
        raise clip.ClipError("the file isn't on this machine and PLEX_URL / PLEX_TOKEN aren't set")
    with duckdb.connect(db_path(), read_only=True) as con:
        found = con.execute("""select rating_key from plex.history where file_path = ?
                               order by viewed_at desc limit 1""", [plex_file]).fetchone()
    if not found:
        raise clip.ClipError("no Plex history row for this file, so its library item is unknown")
    meta = PlexClient(url, token).metadata(found[0])
    parts = [p for m in (meta or {}).get("Media") or [] for p in m.get("Part") or []]
    part = next((p for p in parts if p.get("file") == plex_file), parts[0] if parts else None)
    if not part or not part.get("key"):
        raise clip.ClipError("Plex no longer has this file (removed from the library?)")
    return url.rstrip("/") + part["key"], f"X-Plex-Token: {token}\r\n"


def render_row(row: dict, mode: str | None = None):
    """(web images, matrix images) for a catalog row."""
    mode = mode or row["render_mode"]
    if mode == "sprite":
        scene = sprites.find(row.get("title"), row.get("year"))
        if scene is None:
            raise Skip(f"no hand-built sprite for {row.get('title')} ({row.get('year')}) yet; "
                       f"add one under film/sprites/, or switch it to motif")
        frames = scene()
        return canvas.render_frames(frames, "light"), canvas.render_frames(frames, "dark")
    if mode == "motif":
        frames = motifs.render(row.get("title") or "", row["film_key"])
        return canvas.render_frames(frames, "light"), canvas.render_frames(frames, "dark")
    if mode == "plex_clip":
        if row.get("clip_start") is None:
            raise clip.ClipError("no clip_start set")
        source = clip.local_path(row["plex_file"]) if row.get("plex_file") else None
        headers = None
        if source is None:
            source, headers = plex_stream(row["plex_file"])
        raw = clip.extract_frames(source, float(row["clip_start"]), headers)
        return clip.quantize(raw, "light"), clip.quantize(raw, "dark")
    if mode == "youtube":
        if not row.get("youtube_url"):
            raise clip.ClipError("no YouTube link set")
        start = float(row.get("clip_start") or 0)
        source, headers = youtube.stream(row["youtube_url"], start)
        raw = youtube.with_retries(lambda: clip.extract_frames(source, start, headers))
        return clip.quantize(raw, "light"), clip.quantize(raw, "dark")
    raise ValueError(f"unknown render mode {mode!r}")


def _save(images, path: Path) -> None:
    tmp = path.with_name(f".{path.stem}.tmp{path.suffix}")
    canvas.save_gif(images, tmp)
    os.replace(tmp, path)


def render_and_record(row: dict, *, mode: str | None = None, write: bool = True,
                      preview_dir: Path | None = None) -> dict | None:
    web, matrix = render_row(row, mode)
    name = slug(row["film_key"])
    if preview_dir:
        canvas.save_gif(web, preview_dir / f"{name}_web@8x.gif", scale=8)
        canvas.save_gif(matrix, preview_dir / f"{name}_matrix@8x.gif", scale=8)
    if not write:
        return None
    rel_web, rel_matrix = GIF_DIR / f"{name}_web.gif", GIF_DIR / f"{name}_matrix.gif"
    (data_dir() / GIF_DIR).mkdir(parents=True, exist_ok=True)
    _save(web, data_dir() / rel_web)
    _save(matrix, data_dir() / rel_matrix)
    return fc.mark_rendered(row["film_key"], str(rel_web), str(rel_matrix), source=row)
