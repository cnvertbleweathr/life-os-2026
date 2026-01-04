#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional


def read_single_row_csv(path: Path) -> dict:
    """
    Reads the first data row from a CSV into a dict.
    Returns {} if file missing, empty, or unreadable.
    """
    try:
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                return row or {}
        return {}
    except Exception:
        return {}


def first_existing(paths: List[Path]) -> Optional[Path]:
    for p in paths:
        if p.exists():
            return p
    return None


def append_history_row(repo_root: Path, today: str, year: int) -> Path:
    """
    Reads existing metric outputs and appends one consolidated row to:
      data/daily/history_daily.csv

    Best-effort: missing inputs never raise.
    Header is managed safely: if new columns appear, the file is rewritten
    with an expanded header (preserving existing rows).
    """
    history_path = repo_root / "data" / "daily" / "history_daily.csv"
    history_path.parent.mkdir(parents=True, exist_ok=True)

    # --- Fitness (SugarWOD) ---
    fitness_path = first_existing([
        repo_root / f"data/sugarwod/metrics/fitness_summary_{year}.csv",
        repo_root / "data/sugarwod/metrics/fitness_summary_2026.csv",
    ])
    fitness_summary = read_single_row_csv(fitness_path) if fitness_path else {}

    # --- Reading (Hardcover) ---
    reading_path = first_existing([
        repo_root / f"data/hardcover/metrics/reading_summary_{year}.csv",
    ])
    reading_summary = read_single_row_csv(reading_path) if reading_path else {}

    # --- Date Night (Calendar) ---
    date_night_path = first_existing([
        repo_root / f"data/calendar/metrics/date_night_summary_{year}.csv",
    ])
    date_night_summary = read_single_row_csv(date_night_path) if date_night_path else {}

    # --- Running (Strava-derived) ---
    running_path = first_existing([
        repo_root / f"data/strava/metrics/running_summary_{year}.csv",
        repo_root / f"data/running/metrics/running_summary_{year}.csv",
        repo_root / f"data/strava/metrics/strava_summary_{year}.csv",
        repo_root / f"data/running/metrics/running_metrics_{year}.csv",
    ])
    running_summary = read_single_row_csv(running_path) if running_path else {}

    # --- Shows (AEG / Denver feed) ---
    shows_path = first_existing([
        repo_root / f"data/shows/metrics/shows_summary_{year}.csv",
    ])
    shows_summary = read_single_row_csv(shows_path) if shows_path else {}

    row = {
        "date": today,
        "year": str(year),

        # Fitness / SugarWOD
        "classes_attended_ytd": (
            fitness_summary.get("classes_attended_2026")
            or fitness_summary.get("classes_attended_ytd")
            or ""
        ),
        "classes_goal": fitness_summary.get("classes_goal", ""),
        "classes_progress_pct": fitness_summary.get("classes_progress_pct", ""),
        "required_classes_per_week": fitness_summary.get("required_classes_per_week", ""),
        "rx_rate": fitness_summary.get("rx_rate", ""),
        "pr_count": fitness_summary.get("pr_count", ""),

        # Hardcover
        "nonfiction_read_ytd": (
            reading_summary.get("nonfiction_read_ytd")
            or reading_summary.get("nonfiction_books_read")
            or ""
        ),
        "nonfiction_goal": (
            reading_summary.get("nonfiction_goal")
            or reading_summary.get("nonfiction_books_goal")
            or ""
        ),
        "fiction_read_ytd": (
            reading_summary.get("fiction_read_ytd")
            or reading_summary.get("fiction_books_read")
            or ""
        ),
        "fiction_goal": (
            reading_summary.get("fiction_goal")
            or reading_summary.get("fiction_books_goal")
            or ""
        ),

        # Calendar Date Night
        "weeks_with_date_night": date_night_summary.get("weeks_with_date_night", ""),
        "weeks_observed": date_night_summary.get("weeks_observed", ""),
        "date_night_goal_per_week": date_night_summary.get("date_night_goal_per_week", ""),
        "date_night_completion_rate_pct": date_night_summary.get("completion_rate_pct", ""),

        # Running (best-effort)
        "running_miles_ytd": (
            running_summary.get("running_miles_ytd")
            or running_summary.get("miles_ytd")
            or ""
        ),
        "running_goal_miles": (
            running_summary.get("running_goal_miles")
            or running_summary.get("miles_goal")
            or ""
        ),
        "running_progress_pct": running_summary.get("running_progress_pct", ""),

        # Shows (Denver upcoming)
        "denver_upcoming_show_count": shows_summary.get("denver_upcoming_show_count", ""),
        "next_show_date": shows_summary.get("next_show_date", ""),
        "next_show_title": shows_summary.get("next_show_title", ""),
        "next_show_venue": shows_summary.get("next_show_venue", ""),
        "next_show_url": shows_summary.get("next_show_url", ""),
        "unique_venues_count": shows_summary.get("unique_venues_count", ""),
    }

    # ---- Safe header management ----
    existing_rows = []
    existing_header: List[str] = []

    if history_path.exists():
        try:
            with open(history_path, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                existing_header = reader.fieldnames or []
                for r in reader:
                    existing_rows.append(r)
        except Exception:
            # If unreadable, fall back to overwrite with just this row.
            existing_rows = []
            existing_header = []

    # union headers
    new_keys = list(row.keys())
    header = list(existing_header) if existing_header else []
    for k in new_keys:
        if k not in header:
            header.append(k)

    # if header changed, rewrite file preserving old rows
    header_changed = bool(existing_header) and header != existing_header

    if not history_path.exists() or not existing_header or header_changed:
        with open(history_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()
            for r in existing_rows:
                writer.writerow({h: r.get(h, "") for h in header})
            writer.writerow({h: row.get(h, "") for h in header})
    else:
        # append only
        with open(history_path, "a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writerow({h: row.get(h, "") for h in header})

    return history_path



@dataclass
class Step:
    name: str
    cmd: List[str]
    required: bool = False  # if True, failing stops the run
    run_if_exists: Optional[Path] = None  # if set, only run if this file exists


def run_step(step: Step, cwd: Path, log_dir: Path) -> dict:
    if step.run_if_exists is not None and not step.run_if_exists.exists():
        return {"name": step.name, "status": "skipped", "reason": f"missing {step.run_if_exists}"}

    start = datetime.now().isoformat(timespec="seconds")
    log_path = log_dir / f"{step.name.replace(' ', '_').lower()}.log"

    try:
        proc = subprocess.run(
            step.cmd,
            cwd=str(cwd),
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

        result = {
            "name": step.name,
            "status": "ok" if proc.returncode == 0 else "failed",
            "returncode": proc.returncode,
            "started_at": start,
            "ended_at": end,
            "log_file": str(log_path),
        }

        if proc.returncode != 0 and step.required:
            result["required"] = True

        return result

    except Exception as e:
        end = datetime.now().isoformat(timespec="seconds")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"$ {' '.join(step.cmd)}\n\n")
            f.write(f"Exception: {repr(e)}\n")

        return {
            "name": step.name,
            "status": "failed",
            "returncode": None,
            "started_at": start,
            "ended_at": end,
            "error": repr(e),
            "log_file": str(log_path),
            "required": step.required,
        }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int, default=datetime.now().year)
    p.add_argument(
        "--also-run",
        action="append",
        default=[],
        help="Optional extra command to run (repeatable). Example: --also-run 'python3 scripts/foo.py'",
    )
    args = p.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    today = datetime.now().strftime("%Y-%m-%d")

    out_dir = repo_root / "data" / "daily" / today
    out_dir.mkdir(parents=True, exist_ok=True)

    steps: List[Step] = [
        # SugarWOD
        Step(
            name="sugarwod_import",
            cmd=["python3", "scripts/import_sugarwod_csv.py"],
            run_if_exists=repo_root / "scripts/import_sugarwod_csv.py",
        ),
        Step(
            name="fitness_metrics",
            cmd=["python3", "scripts/fitness_metrics.py"],
            run_if_exists=repo_root / "scripts/fitness_metrics.py",
        ),

        # Strava (fetch activities; auth is not a daily step)
        Step(
            name="strava_fetch",
            cmd=["python3", "scripts/fetch_strava_activities.py", "--year", str(args.year)],
            run_if_exists=repo_root / "scripts/fetch_strava_activities.py",
        ),
        Step(
            name="running_metrics",
            cmd=["python3", "scripts/running_metrics.py", "--year", str(args.year)],
            run_if_exists=repo_root / "scripts/running_metrics.py",
        ),

        # Hardcover
        Step(
            name="hardcover_fetch",
            cmd=["python3", "scripts/hardcover_fetch.py"],
            run_if_exists=repo_root / "scripts/hardcover_fetch.py",
        ),
        Step(
            name="hardcover_metrics",
            cmd=["python3", "scripts/hardcover_metrics.py", "--year", str(args.year)],
            run_if_exists=repo_root / "scripts/hardcover_metrics.py",
        ),

        # Google Calendar
        Step(
            name="calendar_export",
            cmd=["python3", "scripts/calendar_export.py", "--year", str(args.year)],
            run_if_exists=repo_root / "scripts/calendar_export.py",
        ),
        Step(
            name="calendar_metrics",
            cmd=["python3", "scripts/calendar_metrics.py", "--year", str(args.year)],
            run_if_exists=repo_root / "scripts/calendar_metrics.py",
        ),

        #AEG Shows
        Step(
            name="aeg_events_fetch",
            cmd=["python3", "scripts/aeg_events_fetch.py"],
            run_if_exists=repo_root / "scripts" / "aeg_events_fetch.py",
        ),
        Step(
            name="shows_metrics",
            cmd=["python3", "scripts/shows_metrics.py", "--year", str(args.year)],
            run_if_exists=repo_root / "scripts" / "shows_metrics.py",
        ),

    ]

    for extra in args.also_run:
        steps.append(Step(name=f"extra_{len(steps)+1}", cmd=extra.split(), required=False))

    run_results = []
    failed_required = False

    for step in steps:
        res = run_step(step, cwd=repo_root, log_dir=out_dir)
        run_results.append(res)
        if res.get("status") == "failed" and res.get("required"):
            failed_required = True
            break

    summary = {"date": today, "year": args.year, "steps": run_results}
    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    lines = [f"# Daily Sync — {today}", "", f"- Year: {args.year}", ""]
    for r in run_results:
        status = r.get("status")
        name = r.get("name")
        log_file = r.get("log_file")
        if status == "ok":
            lines.append(f"- ✅ {name}  (log: {log_file})")
        elif status == "skipped":
            lines.append(f"- ⏭️ {name} — skipped ({r.get('reason')})")
        else:
            lines.append(f"- ❌ {name}  (log: {log_file})")
            if r.get("returncode") is not None:
                lines.append(f"  - returncode: {r.get('returncode')}")
            if r.get("error"):
                lines.append(f"  - error: {r.get('error')}")
    lines.append("")

    with open(out_dir / "summary.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # Append consolidated daily history row (best-effort, never fatal)
    try:
        history_path = append_history_row(repo_root, today=today, year=args.year)
        print(f"Appended: {history_path}", flush=True)
    except Exception as e:
        print(f"Warning: failed to append history_daily.csv: {e}", file=sys.stderr, flush=True)

    print(f"Wrote: {out_dir / 'summary.json'}")
    print(f"Wrote: {out_dir / 'summary.md'}")

    return 1 if failed_required else 0


if __name__ == "__main__":
    raise SystemExit(main())
