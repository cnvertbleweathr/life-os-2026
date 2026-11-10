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
  youtube    ffmpeg pixelates clip_start → +5 s of a YouTube video the owner
             picked on /film (the API renders those straight away; this run
             retries any that failed or were saved while the API was down)

The rendering itself lives in film/render.py, shared with the API.

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
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from api import film_catalog as fc  # noqa: E402
from film.render import (  # noqa: E402,F401  (re-exported for tests and callers)
    FAILURES, GIF_DIR, Skip, db_path, plex_stream, render_and_record, render_row, slug,
)


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
        except FAILURES as e:
            counts["failed"] += 1
            print(f"  ✗ {row.get('title')}: {e}")
            if not args.no_write:
                fc.mark_failed(row["film_key"], str(e))
    print(f"  {counts}")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
