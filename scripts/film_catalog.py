#!/usr/bin/env python3
"""
scripts/film_catalog.py: review the film scene catalog from the command line.

The same approve / edit / reject as /api/film/queue (both go through
api/film_catalog.py), for use before the /film page exists. Writes append to
data/film/scene_catalog.jsonl (or ONS_DATA_DIR / ONS_DEV's .dev-data);
film.scene_catalog in DuckDB catches up on the next sync.

Usage:
  python scripts/film_catalog.py list                    # suggested rows
  python scripts/film_catalog.py list --status all
  python scripts/film_catalog.py show tmdb:30497
  python scripts/film_catalog.py approve tmdb:30497
  python scripts/film_catalog.py approve tmdb:30497 --label "Leatherface at the door" --clip 2950 2955
  python scripts/film_catalog.py edit tmdb:30497 --mode motif --note "Porch light flickering"
  python scripts/film_catalog.py reject tmdb:30497
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api import film_catalog as fc  # noqa: E402


def _edits(args) -> dict:
    out = {}
    if args.label is not None:
        out["scene_label"] = args.label
    if args.note is not None:
        out["scene_note"] = args.note
    if args.mode is not None:
        out["render_mode"] = args.mode
    if args.clip is not None:
        out["clip_start"], out["clip_end"] = args.clip
    return out


def _line(row: dict) -> str:
    clip = f" clip {row['clip_start']:g}–{row['clip_end']:g}s" if row.get("clip_start") is not None else ""
    return (f"{row['status']:<9} {row['film_key']:<24} {row.get('title')} ({row.get('year')})  "
            f"[{row.get('render_mode')}{clip}]  {row.get('scene_label') or '—'}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Review the film scene catalog.")
    sub = p.add_subparsers(dest="cmd", required=True)

    ls = sub.add_parser("list")
    ls.add_argument("--status", default="suggested", choices=[*fc.STATUSES, "all"])
    sub.add_parser("show").add_argument("film_key")
    sub.add_parser("reject").add_argument("film_key")
    for name in ("approve", "edit"):
        sp = sub.add_parser(name)
        sp.add_argument("film_key")
        sp.add_argument("--label")
        sp.add_argument("--note")
        sp.add_argument("--mode", choices=fc.RENDER_MODES)
        sp.add_argument("--clip", nargs=2, type=float, metavar=("START", "END"), help="seconds into the file")
    args = p.parse_args(argv)

    try:
        if args.cmd == "list":
            rows = sorted(fc.catalog().values(), key=lambda r: r.get("suggested_at") or "", reverse=True)
            rows = [r for r in rows if args.status == "all" or r.get("status") == args.status]
            for r in rows:
                print(_line(r))
            print(f"{len(rows)} row(s)")
        elif args.cmd == "show":
            print(json.dumps(fc.get(args.film_key), indent=2))
        elif args.cmd == "approve":
            print(_line(fc.approve(args.film_key, _edits(args))))
        elif args.cmd == "edit":
            print(_line(fc.edit(args.film_key, _edits(args))))
        elif args.cmd == "reject":
            print(_line(fc.reject(args.film_key)))
    except fc.CatalogError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
