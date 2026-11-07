#!/usr/bin/env python3
"""
scripts/film_gif_render.py: render each approved film's 5-second pixel GIF.

For every catalog row with status "approved" (api/film_catalog.py) it makes
two GIFs, 64×32 art pixels, 40 frames × 125 ms, looping:
  data/film/gifs/<film>_web.gif      light-theme --px-* palette, for the site
  data/film/gifs/<film>_matrix.gif   dark-theme palette, for the LED panel
then marks the row "rendered" with both paths (relative to the data dir).

Render modes (see film/):
  sprite     a hand-built scene from film/sprites/; a public-domain film with
             no scene written yet is skipped and stays approved
  plex_clip  ffmpeg pixelates clip_start → +5 s of your Plex copy
  motif      an original mood loop with the title in the 3×5 font

data/film/gifs/ is gitignored: plex_clip GIFs are a personal-use derivative
and are only ever served to the owner.

Usage:
  python scripts/film_gif_render.py                      # every approved film without a GIF
  python scripts/film_gif_render.py --film tmdb:30497    # one film (approved, or rendered with --force)
  python scripts/film_gif_render.py --dry-run            # list what would render
  python scripts/film_gif_render.py --preview /tmp/px    # also write 8× previews there
  python scripts/film_gif_render.py --film tmdb:30497 --mode motif --preview /tmp/px --no-write
                                                         # try a look without touching the catalog
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from api import film_catalog as fc  # noqa: E402
from api.store import data_dir  # noqa: E402
from film import canvas, clip, motifs, sprites  # noqa: E402

GIF_DIR = Path("film") / "gifs"   # relative to the data dir


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
    raise ValueError(f"unknown render mode {mode!r}")


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
    canvas.save_gif(web, data_dir() / rel_web)
    canvas.save_gif(matrix, data_dir() / rel_matrix)
    return fc.mark_rendered(row["film_key"], str(rel_web), str(rel_matrix))


def queue(film_key: str | None, force: bool) -> list[dict]:
    rows = fc.catalog()
    if film_key:
        row = fc.get(film_key)
        ok = ("approved", "rendered") if force else ("approved",)
        if row["status"] not in ok:
            raise fc.CatalogError(f"{film_key} is {row['status']}" + ("" if force else "; use --force to re-render"))
        return [row]
    return sorted((r for r in rows.values() if r.get("status") == "approved"),
                  key=lambda r: r.get("approved_at") or "")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Render approved films' pixel GIFs.")
    p.add_argument("--film", help="render just this film_key")
    p.add_argument("--force", action="store_true", help="with --film: re-render a rendered film")
    p.add_argument("--mode", choices=fc.RENDER_MODES, help="override the render mode (needs --no-write)")
    p.add_argument("--preview", type=Path, help="also write 8× previews to this directory")
    p.add_argument("--no-write", action="store_true", help="previews only; no GIFs in data/, no catalog change")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    if args.mode and not args.no_write:
        p.error("--mode only goes with --no-write: change the catalog's render mode to keep it")
    if args.no_write and not args.preview:
        p.error("--no-write needs --preview, or nothing is produced")

    try:
        rows = queue(args.film, args.force or args.no_write)
    except fc.CatalogError as e:
        print(f"❌ {e}")
        return 1
    print(f"Film GIFs: {len(rows)} to render")
    if args.dry_run:
        for r in rows:
            print(f"  [dry-run] {r['film_key']:<24} {r.get('title')} ({r.get('year')})  [{r['render_mode']}]")
        return 0

    counts = {"rendered": 0, "skipped": 0, "failed": 0}
    for row in rows:
        try:
            render_and_record(row, mode=args.mode, write=not args.no_write, preview_dir=args.preview)
            counts["rendered"] += 1
            print(f"  ✓ {row.get('title')} [{args.mode or row['render_mode']}]")
        except Skip as e:
            counts["skipped"] += 1
            print(f"  · {row.get('title')}: {e}")
        except (clip.ClipError, fc.CatalogError, OSError) as e:
            counts["failed"] += 1
            print(f"  ✗ {row.get('title')}: {e}")
    print(f"  {counts}")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
