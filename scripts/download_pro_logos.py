#!/usr/bin/env python3
"""
download_pro_logos.py — Download MLB/NBA/NFL team logos from klunn91/team-logos
to web/public/logos/{league}/.

Source repo:  https://github.com/klunn91/team-logos
Mirrors the pattern used by download_cfb_logos.py — logos are served locally
at /logos/{league}/{filename} instead of pulled live from GitHub (faster, no
rate limits, works offline).

Each league has its own name -> filename map in web/lib/{league}_team_logos.json,
e.g. web/lib/mlb_team_logos.json maps "Guardians" -> "indians.png".

NOTE — source repo is stale (last touched 2019):
  - MLB: "Guardians" file is still named indians.png (pre-2022 rebrand)
  - NFL: "Commanders" file is still named redskins.png (pre-2020 rebrand)
  The JSON maps already point the current team name at the old filename,
  so downstream code can use current names without caring about this.

Usage:
  python scripts/download_pro_logos.py                  # all three leagues
  python scripts/download_pro_logos.py --league mlb      # one league
  python scripts/download_pro_logos.py --dry-run
  python scripts/download_pro_logos.py --force           # re-download existing
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGOS_ROOT = ROOT / "web" / "public" / "logos"
RAW_BASE = "https://raw.githubusercontent.com/klunn91/team-logos/master"

LEAGUES = {
    "mlb": {"repo_dir": "MLB", "map_file": "mlb_team_logos.json"},
    "nba": {"repo_dir": "NBA", "map_file": "nba_team_logos.json"},
    "nfl": {"repo_dir": "NFL", "map_file": "nfl_team_logos.json"},
}


def download_one(url: str, dest: Path, timeout: int = 10) -> int:
    req = urllib.request.Request(url, headers={"User-Agent": "ons-2026/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    dest.write_bytes(data)
    return len(data)


def run_league(league: str, dry_run: bool, force: bool) -> tuple[int, int, int]:
    cfg = LEAGUES[league]
    map_path = ROOT / "web" / "lib" / cfg["map_file"]
    logos_dir = LOGOS_ROOT / league

    if not map_path.exists():
        print(f"❌ Team map not found: {map_path}")
        return 0, 0, 1

    team_map: dict[str, str] = json.loads(map_path.read_text())
    filenames = sorted(set(team_map.values()))
    # League logo (e.g. _NFL_logo.png) — bonus, not in the team map
    filenames.append(f"_{league.upper()}_logo.png")

    print(f"--- {league.upper()} ---")
    print(f"  Source:  {RAW_BASE}/{cfg['repo_dir']}/{{filename}}")
    print(f"  Target:  {logos_dir}/")
    print(f"  Files:   {len(filenames)} ({len(team_map)} teams + league logo)")

    if dry_run:
        print(f"  [dry-run] Would create: {logos_dir}")
        print(f"  [dry-run] Would download {len(filenames)} files")
        print()
        return 0, 0, 0

    logos_dir.mkdir(parents=True, exist_ok=True)

    ok = skipped = failed = 0
    for i, fname in enumerate(filenames, 1):
        dest = logos_dir / fname
        if dest.exists() and not force:
            skipped += 1
            continue

        url = f"{RAW_BASE}/{cfg['repo_dir']}/{fname}"
        try:
            size = download_one(url, dest)
            ok += 1
            print(f"  ✓ {fname:20} ({size:,} bytes)  [{i}/{len(filenames)}]")
            time.sleep(0.05)  # polite rate limiting
        except Exception as e:
            failed += 1
            print(f"  ✗ {fname:20} {e}")

    print(f"  Done: {ok} downloaded · {skipped} skipped · {failed} failed")
    print()
    return ok, skipped, failed


def main() -> int:
    p = argparse.ArgumentParser(description="Download MLB/NBA/NFL team logos locally.")
    p.add_argument("--league", choices=list(LEAGUES.keys()), help="Only download one league")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="Re-download existing logos")
    args = p.parse_args()

    leagues = [args.league] if args.league else list(LEAGUES.keys())

    print("ONS Pro Sports Logo Downloader (klunn91/team-logos)")
    print()

    total_ok = total_skipped = total_failed = 0
    for league in leagues:
        ok, skipped, failed = run_league(league, args.dry_run, args.force)
        total_ok += ok
        total_skipped += skipped
        total_failed += failed

    if not args.dry_run:
        print(f"=== TOTAL: {total_ok} downloaded · {total_skipped} skipped · {total_failed} failed ===")

    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
