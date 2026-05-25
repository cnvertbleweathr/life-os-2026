#!/usr/bin/env python3
"""
daily_sync.py — Life OS daily orchestrator.

Runs all pipelines, syncs goal progress, runs dbt, generates Spotify playlist,
and writes a summary log.

Usage:
  python scripts/daily_sync.py
  python scripts/daily_sync.py --year 2026
  python scripts/daily_sync.py --skip spotify   # skip a step by name
  python scripts/daily_sync.py --only strava hardcover habits dbt
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Step definition
# ---------------------------------------------------------------------------

@dataclass
class Step:
    name: str
    cmd: List[str]
    required: bool = False
    run_if_exists: Optional[Path] = None
    tags: List[str] = field(default_factory=list)


def run_step(step: Step, log_dir: Path) -> dict:
    if step.run_if_exists is not None and not step.run_if_exists.exists():
        return {
            "name": step.name,
            "status": "skipped",
            "reason": f"missing {step.run_if_exists.name}",
        }

    start = datetime.now().isoformat(timespec="seconds")
    log_path = log_dir / f"{step.name}.log"

    try:
        proc = subprocess.run(
            step.cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            env=os.environ.copy(),
        )
        end = datetime.now().isoformat(timespec="seconds")

        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"$ {' '.join(step.cmd)}\n\n")
            f.write(proc.stdout or "")
            if proc.stderr:
                f.write("\n--- STDERR ---\n")
                f.write(proc.stderr)

        return {
            "name": step.name,
            "status": "ok" if proc.returncode == 0 else "failed",
            "returncode": proc.returncode,
            "started_at": start,
            "ended_at": end,
            "log": str(log_path),
        }

    except Exception as e:
        end = datetime.now().isoformat(timespec="seconds")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"Exception: {repr(e)}\n")
        return {
            "name": step.name,
            "status": "failed",
            "returncode": None,
            "started_at": start,
            "ended_at": end,
            "error": repr(e),
            "log": str(log_path),
            "required": step.required,
        }


# ---------------------------------------------------------------------------
# Step registry
# ---------------------------------------------------------------------------

def build_steps(year: int) -> List[Step]:
    dbt_cmd = [
        "dbt", "run",
        "--profiles-dir", "dbt/profiles",
        "--project-dir", "dbt",
    ]

    return [
        # ------------------------------------------------------------------
        # DLT pipelines
        # ------------------------------------------------------------------
        Step(
            name="strava",
            cmd=["python3", "run_pipelines.py", "--only", "strava", "--year", str(year)],
            run_if_exists=ROOT / "pipelines/strava_pipeline.py",
            tags=["pipelines"],
        ),
        Step(
            name="hardcover",
            cmd=["python3", "run_pipelines.py", "--only", "hardcover", "--year", str(year)],
            run_if_exists=ROOT / "pipelines/hardcover_pipeline.py",
            tags=["pipelines"],
        ),
        Step(
            name="habits",
            cmd=["python3", "run_pipelines.py", "--only", "habits", "--year", str(year)],
            run_if_exists=ROOT / "pipelines/habits_pipeline.py",
            tags=["pipelines"],
        ),

        # ------------------------------------------------------------------
        # Calendar
        # ------------------------------------------------------------------
        Step(
            name="calendar_export",
            cmd=["python3", "scripts/calendar_export.py", "--year", str(year)],
            run_if_exists=ROOT / "scripts/calendar_export.py",
            tags=["calendar"],
        ),
        Step(
            name="calendar_metrics",
            cmd=["python3", "scripts/calendar_metrics.py", "--year", str(year)],
            run_if_exists=ROOT / "scripts/calendar_metrics.py",
            tags=["calendar"],
        ),

        # ------------------------------------------------------------------
        # Shows (AEG + Ticketmaster)
        # ------------------------------------------------------------------
        Step(
            name="aeg_events",
            cmd=["python3", "scripts/aeg_events_fetch.py"],
            run_if_exists=ROOT / "scripts/aeg_events_fetch.py",
            tags=["shows"],
        ),
        Step(
            name="ticketmaster",
            cmd=["python3", "scripts/ticketmaster_fetch_denver.py"],
            run_if_exists=ROOT / "scripts/ticketmaster_fetch_denver.py",
            tags=["shows"],
        ),
        Step(
            name="shows_metrics",
            cmd=["python3", "scripts/shows_metrics.py", "--year", str(year)],
            run_if_exists=ROOT / "scripts/shows_metrics.py",
            tags=["shows"],
        ),

        # ------------------------------------------------------------------
        # Spotify
        # ------------------------------------------------------------------
        Step(
            name="spotify_ingest",
            cmd=["python3", "scripts/spotify_ingest_streaming.py"],
            # Only runs if raw streaming history files exist
            run_if_exists=ROOT / "data/spotify/raw/streaming_history",
            tags=["spotify"],
        ),
        Step(
            name="spotify_metrics",
            cmd=["python3", "scripts/spotify_metrics.py", "--year", str(year)],
            run_if_exists=ROOT / "scripts/spotify_metrics.py",
            tags=["spotify"],
        ),
        Step(
            name="spotify_daily10",
            cmd=["python3", "scripts/spotify_daily10_playlist.py"],
            run_if_exists=ROOT / "scripts/spotify_daily10_playlist.py",
            tags=["spotify"],
        ),

        # ------------------------------------------------------------------
        # Streams (streamed.pk)
        # ------------------------------------------------------------------
        Step(
            name="fetch_streams",
            cmd=["python3", "scripts/fetch_streams.py"],
            run_if_exists=ROOT / "scripts/fetch_streams.py",
            tags=["streams"],
        ),

        # ------------------------------------------------------------------
        # Playlist artists + show cross-reference
        # ------------------------------------------------------------------
        Step(
            name="sync_playlist_artists",
            cmd=["python3", "scripts/sync_playlist_artists.py"],
            run_if_exists=ROOT / "scripts/sync_playlist_artists.py",
            tags=["shows", "spotify"],
        ),

        # ------------------------------------------------------------------
        # Goal progress sync + dbt (always last)
        # ------------------------------------------------------------------
        Step(
            name="sync_goal_progress",
            cmd=["python3", "scripts/sync_goal_progress.py"],
            run_if_exists=ROOT / "scripts/sync_goal_progress.py",
            required=True,
            tags=["dbt"],
        ),
        Step(
            name="dbt",
            cmd=dbt_cmd,
            required=True,
            tags=["dbt"],
        ),
    ]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Life OS daily sync.")
    p.add_argument("--year", type=int, default=datetime.now().year)
    p.add_argument("--skip", nargs="+", default=[], metavar="STEP",
                   help="Step names to skip")
    p.add_argument("--only", nargs="+", default=[], metavar="STEP",
                   help="Run only these steps (by name or tag)")
    args = p.parse_args()

    today = datetime.now().strftime("%Y-%m-%d")
    log_dir = ROOT / "data" / "daily" / today
    log_dir.mkdir(parents=True, exist_ok=True)

    all_steps = build_steps(args.year)

    # Filter by --only / --skip
    if args.only:
        only_set = set(args.only)
        steps = [s for s in all_steps if s.name in only_set or bool(only_set & set(s.tags))]
    else:
        steps = all_steps

    if args.skip:
        skip_set = set(args.skip)
        steps = [s for s in steps if s.name not in skip_set]

    print(f"Life OS daily sync — {today}")
    print(f"Running {len(steps)} steps\n")

    results = []
    failed_required = False

    for step in steps:
        print(f"  → {step.name}...", end=" ", flush=True)
        res = run_step(step, log_dir=log_dir)
        results.append(res)

        status = res["status"]
        if status == "ok":
            print("✓")
        elif status == "skipped":
            print(f"skipped ({res.get('reason', '')})")
        else:
            print(f"✗  (see {res.get('log', '')})")
            if res.get("required"):
                failed_required = True
                print(f"\n  Required step '{step.name}' failed — stopping.\n")
                break

    # Summary JSON
    summary = {"date": today, "year": args.year, "steps": results}
    summary_path = log_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # Print summary
    print(f"\n{'='*50}")
    ok    = [r for r in results if r["status"] == "ok"]
    skipped = [r for r in results if r["status"] == "skipped"]
    failed  = [r for r in results if r["status"] == "failed"]

    print(f"  ✓ {len(ok)} ok   ⏭ {len(skipped)} skipped   ✗ {len(failed)} failed")
    if failed:
        for r in failed:
            print(f"    ✗ {r['name']}  →  {r.get('log', '')}")
    print(f"\n  Logs: {log_dir}")
    print(f"{'='*50}\n")

    return 1 if (failed_required or failed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
