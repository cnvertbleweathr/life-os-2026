#!/usr/bin/env python3
"""
download_cfb_logos.py — Download CFB team logos from CFBD repo to web/public/logos/.

Run once after cloning. Logos are served locally at /logos/{id}.png
instead of from GitHub CDN (faster, no rate limits, works offline).

After running this script, update web/components/ui/TeamLogo.tsx:
  Change: src={`https://raw.githubusercontent.com/CFBD/cfb-web/master/public/logos/${id}.png`}
  To:     src={`/logos/${id}.png`}

Usage:
  python scripts/download_cfb_logos.py
  python scripts/download_cfb_logos.py --dry-run
  python scripts/download_cfb_logos.py --force   # re-download existing
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

ROOT       = Path(__file__).resolve().parents[1]
IDS_PATH   = ROOT / "web" / "lib" / "cfb_team_ids.json"
LOGOS_DIR  = ROOT / "web" / "public" / "logos"
CDN_BASE   = "https://raw.githubusercontent.com/CFBD/cfb-web/master/public/logos"


def main() -> int:
    p = argparse.ArgumentParser(description="Download CFB team logos locally.")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force",   action="store_true", help="Re-download existing logos")
    args = p.parse_args()

    if not IDS_PATH.exists():
        print(f"❌ Team ID map not found: {IDS_PATH}")
        print("   Extract ons-web.tar.gz first.")
        return 1

    team_ids: dict[str, int] = json.loads(IDS_PATH.read_text())
    ids = sorted(set(team_ids.values()))

    print(f"ONS CFB Logo Downloader")
    print(f"  Source:  {CDN_BASE}/{{id}}.png")
    print(f"  Target:  {LOGOS_DIR}/")
    print(f"  Teams:   {len(ids)} unique IDs from {len(team_ids)} team entries")
    print()

    if args.dry_run:
        print(f"[dry-run] Would create: {LOGOS_DIR}")
        print(f"[dry-run] Would download {len(ids)} logos")
        return 0

    LOGOS_DIR.mkdir(parents=True, exist_ok=True)

    ok = skipped = failed = 0

    for i, tid in enumerate(ids, 1):
        dest = LOGOS_DIR / f"{tid}.png"

        if dest.exists() and not args.force:
            skipped += 1
            continue

        url = f"{CDN_BASE}/{tid}.png"
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "ons-2026/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                data = r.read()
            dest.write_bytes(data)
            ok += 1
            print(f"  ✓ {tid:5}  ({len(data):,} bytes)  [{i}/{len(ids)}]")
            # Polite rate limiting — 50ms between requests
            time.sleep(0.05)
        except Exception as e:
            failed += 1
            print(f"  ✗ {tid:5}  {e}")

    print()
    print(f"Done: {ok} downloaded · {skipped} skipped (already exist) · {failed} failed")

    if ok > 0 or skipped > 0:
        print()
        print("Next step — update TeamLogo.tsx:")
        print("  Change the src line from:")
        print(f"    `${{CDN_BASE}}/${{id}}.png`")
        print("  To:")
        print(f"    `/logos/${{id}}.png`")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
