#!/usr/bin/env python3
"""
download_nhl_mls_logos.py — Fetch NHL and MLS team logos to web/public/logos/{league}/.

Two different source shapes:
  - MLS (MatthewHallCom/blade-mls-icons): flat .svg files in resources/svg/,
    fetched directly via raw.githubusercontent.com like the pro_logos script.
  - NHL (bradmcgonigle/react-nhl-logos): logos ship as .tsx React components
    wrapping inline SVG (no standalone .svg files in the repo), so this script
    clones the repo tarball and extracts the inner <svg>...</svg> markup from
    each component into a clean standalone .svg file.

Team name -> filename maps live in web/lib/{league}_team_logos.json, same
pattern as mlb/nba/nfl/cfb.

NOTE — known data gaps (flag these, don't paper over them):
  - NHL: Arizona Coyotes relocated to Utah (Mammoth) in 2024. The repo kept
    the old Coyotes art under "ari.svg" for historical/back-data use. The
    map exposes it as "_legacy_Arizona Coyotes" rather than under a normal
    team name, so current-season lookups won't accidentally surface it.
  - MLS: San Diego FC (2025 expansion team, league's 30th club) has no logo
    in the source repo as of this writing. It is intentionally left OUT of
    mls_team_logos.json — TeamLogo.tsx's text-initial fallback will show
    until a logo is sourced separately. Do not fabricate an entry.

Usage:
  python scripts/download_nhl_mls_logos.py                 # both leagues
  python scripts/download_nhl_mls_logos.py --league mls     # one league
  python scripts/download_nhl_mls_logos.py --dry-run
  python scripts/download_nhl_mls_logos.py --force          # re-fetch existing
"""
from __future__ import annotations

import argparse
import json
import re
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGOS_ROOT = ROOT / "web" / "public" / "logos"

MLS_RAW_BASE = "https://raw.githubusercontent.com/MatthewHallCom/blade-mls-icons/main/resources/svg"
NHL_TARBALL_URL = "https://codeload.github.com/bradmcgonigle/react-nhl-logos/tar.gz/refs/heads/master"


# --------------------------------------------------------------------------
# MLS — flat raw-file fetch
# --------------------------------------------------------------------------
def run_mls(dry_run: bool, force: bool) -> tuple[int, int, int]:
    map_path = ROOT / "web" / "lib" / "mls_team_logos.json"
    logos_dir = LOGOS_ROOT / "mls"

    if not map_path.exists():
        print(f"❌ Team map not found: {map_path}")
        return 0, 0, 1

    team_map: dict[str, str] = json.loads(map_path.read_text())
    filenames = sorted(set(team_map.values())) + ["mls.svg"]  # + league logo

    print("--- MLS ---")
    print(f"  Source:  {MLS_RAW_BASE}/{{filename}}")
    print(f"  Target:  {logos_dir}/")
    print(f"  Files:   {len(filenames)} ({len(team_map)} teams + league logo)")
    print("  NOTE: San Diego FC has no logo in the source repo — not in the map.")

    if dry_run:
        print(f"  [dry-run] Would download {len(filenames)} files\n")
        return 0, 0, 0

    logos_dir.mkdir(parents=True, exist_ok=True)
    ok = skipped = failed = 0
    for i, fname in enumerate(filenames, 1):
        dest = logos_dir / fname
        if dest.exists() and not force:
            skipped += 1
            continue
        url = f"{MLS_RAW_BASE}/{fname}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ons-2026/1.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = r.read()
            dest.write_bytes(data)
            ok += 1
            print(f"  ✓ {fname:30} ({len(data):,} bytes)  [{i}/{len(filenames)}]")
            time.sleep(0.05)
        except Exception as e:
            failed += 1
            print(f"  ✗ {fname:30} {e}")

    print(f"  Done: {ok} downloaded · {skipped} skipped · {failed} failed\n")
    return ok, skipped, failed


# --------------------------------------------------------------------------
# NHL — clone tarball, extract inline SVG out of each .tsx component
# --------------------------------------------------------------------------
def extract_svg_from_tsx(code: str) -> tuple[str, str] | None:
    """Returns (viewbox, full standalone svg string) or None if no match."""
    m = re.search(r"<svg\b(.*?)>(.*)</svg>", code, re.DOTALL)
    if not m:
        return None
    attrs_raw, body = m.group(1), m.group(2)

    viewbox_m = re.search(r'viewBox="([^"]+)"', attrs_raw)
    viewbox = viewbox_m.group(1) if viewbox_m else "0 0 100 100"

    extra_attrs = []
    for am in re.finditer(r'([\w-]+)="([^"]*)"', attrs_raw):
        key, val = am.group(1), am.group(2)
        if key in ("viewBox", "xmlns"):
            continue
        extra_attrs.append(f'{key}="{val}"')
    extra_attrs_str = (" " + " ".join(extra_attrs)) if extra_attrs else ""

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}"{extra_attrs_str}>'
        f"{body}"
        f"</svg>"
    )
    return viewbox, svg


def run_nhl(dry_run: bool, force: bool) -> tuple[int, int, int]:
    map_path = ROOT / "web" / "lib" / "nhl_team_logos.json"
    logos_dir = LOGOS_ROOT / "nhl"

    if not map_path.exists():
        print(f"❌ Team map not found: {map_path}")
        return 0, 0, 1

    print("--- NHL ---")
    print(f"  Source:  {NHL_TARBALL_URL} (cloned, then .tsx -> .svg extracted)")
    print(f"  Target:  {logos_dir}/")
    print("  NOTE: 'ari.svg' is the pre-2024 Arizona Coyotes logo, kept under")
    print("        the map key '_legacy_Arizona Coyotes' for historical data only.")

    if dry_run:
        print("  [dry-run] Would clone repo and extract all .tsx logos\n")
        return 0, 0, 0

    logos_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tarball = tmp_path / "nhl.tar.gz"
        req = urllib.request.Request(NHL_TARBALL_URL, headers={"User-Agent": "ons-2026/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            tarball.write_bytes(r.read())

        with tarfile.open(tarball) as tf:
            tf.extractall(tmp_path)

        src_dirs = list(tmp_path.glob("react-nhl-logos-*/src/logos"))
        if not src_dirs:
            print("  ✗ Could not find src/logos/ in extracted tarball")
            return 0, 0, 1
        src_dir = src_dirs[0]

        ok = skipped = failed = 0
        tsx_files = sorted(src_dir.glob("*.tsx"))
        for i, tsx_path in enumerate(tsx_files, 1):
            out_name = tsx_path.stem + ".svg"
            dest = logos_dir / out_name
            if dest.exists() and not force:
                skipped += 1
                continue
            result = extract_svg_from_tsx(tsx_path.read_text())
            if result is None:
                failed += 1
                print(f"  ✗ {tsx_path.name:12} no <svg> match found")
                continue
            viewbox, svg = result
            dest.write_text(svg)
            ok += 1
            print(f"  ✓ {out_name:12} ({len(svg):,} bytes, viewBox={viewbox})  [{i}/{len(tsx_files)}]")

    print(f"  Done: {ok} extracted · {skipped} skipped · {failed} failed\n")
    return ok, skipped, failed


def main() -> int:
    p = argparse.ArgumentParser(description="Download/extract NHL and MLS team logos locally.")
    p.add_argument("--league", choices=["nhl", "mls"], help="Only process one league")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="Re-fetch/re-extract existing logos")
    args = p.parse_args()

    leagues = [args.league] if args.league else ["nhl", "mls"]

    print("ONS NHL + MLS Logo Downloader")
    print()

    total_ok = total_skipped = total_failed = 0
    for league in leagues:
        fn = run_nhl if league == "nhl" else run_mls
        ok, skipped, failed = fn(args.dry_run, args.force)
        total_ok += ok
        total_skipped += skipped
        total_failed += failed

    if not args.dry_run:
        print(f"=== TOTAL: {total_ok} processed · {total_skipped} skipped · {total_failed} failed ===")

    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
