#!/usr/bin/env python3
"""
daily_sync.py — Operating Narcisystem daily orchestrator.

Runs all pipelines, syncs goal progress, runs dbt, generates Spotify playlist,
and writes a health summary.

Usage:
  python scripts/daily_sync.py
  python scripts/daily_sync.py --year 2026
  python scripts/daily_sync.py --skip spotify
  python scripts/daily_sync.py --only strava hardcover habits dbt

Exit codes:
  0 — all required steps succeeded
  1 — one or more required steps failed
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

YEAR = datetime.now().year  # single source — no hardcoded 2026 anywhere


# ---------------------------------------------------------------------------
# Step definition
# ---------------------------------------------------------------------------

@dataclass
class Step:
    name:          str
    cmd:           List[str]
    required:      bool           = False
    run_if_exists: Optional[Path] = None   # skip if this path does not exist
    tags:          List[str]      = field(default_factory=list)
    run_on_days:   Optional[List[int]] = None  # 0=Mon … 6=Sun; None=every day


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _write_pipeline_run(name: str, result: dict) -> None:
    """
    Append one record to ops.pipeline_runs in DuckDB.
    Non-fatal — silently skipped if DuckDB unavailable.
    """
    try:
        import duckdb as _ddb
        db_path = ROOT / "data" / "warehouse" / "ons.duckdb"
        if not db_path.exists():
            return
        con = _ddb.connect(str(db_path))
        con.execute("CREATE SCHEMA IF NOT EXISTS ops")
        con.execute("""
            CREATE TABLE IF NOT EXISTS ops.pipeline_runs (
                run_id        VARCHAR,
                source_name   VARCHAR,
                started_at    VARCHAR,
                ended_at      VARCHAR,
                duration_s    DOUBLE,
                status        VARCHAR,
                error_message VARCHAR,
                log_path      VARCHAR,
                created_at    TIMESTAMP DEFAULT current_timestamp
            )
        """)
        con.execute("""
            INSERT INTO ops.pipeline_runs
                (run_id, source_name, started_at, ended_at,
                 duration_s, status, error_message, log_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            f"{name}_{result.get('started_at', '')}",
            name,
            result.get("started_at"),
            result.get("ended_at"),
            result.get("duration_s"),
            result.get("status"),
            (result.get("stderr_tail") or [""])[-1]
                if result.get("status") == "failed" else None,
            result.get("log"),
        ])
        con.close()
    except Exception:
        pass  # never let tracking break the sync


def run_step(step: Step, log_dir: Path) -> dict:
    """
    Execute one step. Returns a result dict with status, duration, and log path.

    Status values:
      ok       — exit code 0
      failed   — non-zero exit code or exception
      skipped  — day-of-week gate or run_if_exists check did not pass
    """
    started_dt = datetime.now()
    start      = started_dt.isoformat(timespec="seconds")

    # ── Day-of-week gate ─────────────────────────────────────────────────────
    if step.run_on_days is not None:
        if started_dt.weekday() not in step.run_on_days:
            return {
                "name":     step.name,
                "status":   "skipped",
                "reason":   f"not scheduled today (runs on days {step.run_on_days})",
                "required": step.required,
            }

    # ── run_if_exists gate ───────────────────────────────────────────────────
    if step.run_if_exists is not None and not step.run_if_exists.exists():
        return {
            "name":     step.name,
            "status":   "skipped",
            "reason":   f"run_if_exists path not found: {step.run_if_exists}",
            "required": step.required,
        }

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
        ended_dt = datetime.now()
        duration = round((ended_dt - started_dt).total_seconds(), 2)

        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"$ {' '.join(step.cmd)}\n")
            f.write(f"# started {start}  exit {proc.returncode}  {duration}s\n\n")
            f.write(proc.stdout or "")
            if proc.stderr:
                f.write("\n--- STDERR ---\n")
                f.write(proc.stderr)

        status = "ok" if proc.returncode == 0 else "failed"
        result = {
            "name":       step.name,
            "status":     status,
            "returncode": proc.returncode,
            "started_at": start,
            "ended_at":   ended_dt.isoformat(timespec="seconds"),
            "duration_s": duration,
            "required":   step.required,
            "log":        str(log_path),
        }
        if status == "failed":
            # Include last 10 lines of stderr in the summary for quick diagnosis
            stderr_tail = (proc.stderr or "").strip().splitlines()[-10:]
            result["stderr_tail"] = stderr_tail
        _write_pipeline_run(step.name, result)
        return result

    except Exception as e:
        ended_dt = datetime.now()
        duration = round((ended_dt - started_dt).total_seconds(), 2)
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"Exception: {repr(e)}\n")
        return {
            "name":       step.name,
            "status":     "failed",
            "returncode": None,
            "started_at": start,
            "ended_at":   ended_dt.isoformat(timespec="seconds"),
            "duration_s": duration,
            "required":   step.required,
            "error":      repr(e),
            "log":        str(log_path),
        }


# ---------------------------------------------------------------------------
# Step registry
# ---------------------------------------------------------------------------

def build_steps(year: int) -> List[Step]:
    dbt_cmd = [
        "dbt", "run",
        "--profiles-dir", "dbt/profiles",
        "--project-dir",  "dbt",
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
            run_on_days=[0, 3],  # Monday + Thursday
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
        # Streams
        # ------------------------------------------------------------------
        Step(
            name="fetch_streams",
            cmd=["python3", "scripts/fetch_streams.py"],
            run_if_exists=ROOT / "scripts/fetch_streams.py",
            tags=["streams"],
        ),

        # ------------------------------------------------------------------
        # WOD (Park Hill CrossFit — Playwright headless)
        # ------------------------------------------------------------------
        Step(
            name="fetch_wod",
            cmd=["python3", "scripts/fetch_wod.py"],
            run_if_exists=ROOT / "scripts/fetch_wod.py",
            tags=["fitness", "wod"],
        ),

        # ------------------------------------------------------------------
        # CFB — line tracking (daily during season)
        # ------------------------------------------------------------------
        Step(
            name="track_lines",
            cmd=["python3", "scripts/track_lines.py"],
            run_if_exists=ROOT / "scripts/track_lines.py",
            tags=["betting", "cfb", "lines"],
        ),

        # ------------------------------------------------------------------
        # CFB — news signals (Wed + Thu)
        # ------------------------------------------------------------------
        Step(
            name="track_news_signals",
            cmd=["python3", "scripts/track_news_signals.py"],
            run_if_exists=ROOT / "scripts/track_news_signals.py",
            tags=["betting", "cfb", "news"],
            run_on_days=[2, 3],  # Wednesday + Thursday
        ),

        # ------------------------------------------------------------------
        # CFB — picks (Tue + Wed)
        # ------------------------------------------------------------------
        Step(
            name="generate_picks",
            cmd=["python3", "scripts/generate_picks.py"],
            run_if_exists=ROOT / "scripts/generate_picks.py",
            tags=["betting", "cfb"],
            run_on_days=[1, 2],  # Tuesday + Wednesday
        ),

        # ------------------------------------------------------------------
        # CFB — picks report (Thursday)
        # ------------------------------------------------------------------
        Step(
            name="generate_picks_report",
            cmd=["python3", "scripts/generate_picks_report.py"],
            run_if_exists=ROOT / "scripts/generate_picks_report.py",
            tags=["betting", "cfb"],
            run_on_days=[3],  # Thursday
        ),

        # ------------------------------------------------------------------
        # CFB — grade archived picks against real results (every day)
        # ------------------------------------------------------------------
        # No run_on_days gate, unlike the two steps above -- games finish
        # on varying weekdays (Thu/Fri/Sat/occasional Tue), so this needs
        # to check daily, not on a fixed schedule. Idempotent and cheap:
        # already-fully-graded weeks are skipped before any CFBD call.
        Step(
            name="grade_picks",
            cmd=["python3", "scripts/grade_picks.py"],
            run_if_exists=ROOT / "scripts/grade_picks.py",
            tags=["betting", "cfb"],
        ),

        # ------------------------------------------------------------------
        # CFB — load picks archive into DuckDB (every day, after grading)
        # ------------------------------------------------------------------
        # Runs after grade_picks so cfbd.live_picks reflects same-day
        # outcome updates, not yesterday's. Merge write_disposition means
        # this is cheap even when nothing changed.
        Step(
            name="live_picks_pipeline",
            cmd=["python3", "pipelines/live_picks_pipeline.py"],
            run_if_exists=ROOT / "pipelines/live_picks_pipeline.py",
            tags=["betting", "cfb", "pipelines"],
        ),

        # ------------------------------------------------------------------
        # Shows — playlist artist cross-reference
        # ------------------------------------------------------------------
        Step(
            name="sync_playlist_artists",
            cmd=["python3", "scripts/sync_playlist_artists.py"],
            run_if_exists=ROOT / "scripts/sync_playlist_artists.py",
            tags=["shows", "spotify"],
        ),

        # ------------------------------------------------------------------
        # Goals + dbt — always run, required
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
        Step(
            name="load_goals",
            cmd=["python3", "scripts/load_goals.py"],
            run_if_exists=ROOT / "scripts/load_goals.py",
            tags=["dbt"],
        ),
        Step(
            name="load_goal_progress",
            cmd=["python3", "scripts/load_goal_progress.py"],
            run_if_exists=ROOT / "scripts/load_goal_progress.py",
            tags=["dbt"],
        ),

        # ------------------------------------------------------------------
        # DuckDB backup — always last, after all writes complete
        # ------------------------------------------------------------------
        Step(
            name="backup_duckdb",
            cmd=["python3", "scripts/backup_duckdb.py", "--retention", "7"],
            run_if_exists=ROOT / "scripts/backup_duckdb.py",
            required=False,  # backup failure does not fail the sync
            tags=["infra"],
        ),
    ]


# ---------------------------------------------------------------------------
# Health summary
# ---------------------------------------------------------------------------

def write_health_summary(
    results:    list[dict],
    today:      str,
    year:       int,
    log_dir:    Path,
    total_s:    float,
    aborted_at: str | None,
) -> Path:
    """
    Write two artefacts:
      data/daily/<date>/summary.json   — machine-readable full results
      data/daily/<date>/health.txt     — human-readable at-a-glance summary
    """
    ok      = [r for r in results if r["status"] == "ok"]
    skipped = [r for r in results if r["status"] == "skipped"]
    failed  = [r for r in results if r["status"] == "failed"]

    # ── JSON ─────────────────────────────────────────────────────────────────
    summary = {
        "date":        today,
        "year":        year,
        "total_s":     round(total_s, 2),
        "aborted_at":  aborted_at,
        "counts": {
            "ok":      len(ok),
            "skipped": len(skipped),
            "failed":  len(failed),
            "total":   len(results),
        },
        "steps": results,
    }
    summary_path = log_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    # ── Health text ───────────────────────────────────────────────────────────
    lines = [
        f"ONS Daily Sync — {today}",
        f"Duration: {total_s:.1f}s",
        f"",
        f"  ✓  {len(ok):2d} ok",
        f"  ⏭  {len(skipped):2d} skipped",
        f"  ✗  {len(failed):2d} failed",
    ]

    if aborted_at:
        lines += ["", f"  ⛔ ABORTED at required step: {aborted_at}"]

    if ok:
        lines += ["", "OK:"]
        for r in ok:
            dur = f"{r.get('duration_s', 0):.1f}s"
            lines.append(f"  ✓  {r['name']:<30} {dur:>7}")

    if skipped:
        lines += ["", "Skipped:"]
        for r in skipped:
            reason = r.get("reason", "")
            lines.append(f"  ⏭  {r['name']:<30} {reason}")

    if failed:
        lines += ["", "Failed:"]
        for r in failed:
            lines.append(f"  ✗  {r['name']}")
            tail = r.get("stderr_tail") or []
            for line in tail[-3:]:
                lines.append(f"       {line}")
            lines.append(f"     → {r.get('log', '')}")

    lines += ["", f"Logs: {log_dir}"]
    health_path = log_dir / "health.txt"
    health_path.write_text("\n".join(lines) + "\n")

    return health_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Operating Narcisystem daily sync.")
    p.add_argument("--year", type=int, default=YEAR)
    p.add_argument("--skip", nargs="+", default=[], metavar="STEP",
                   help="Step names or tags to skip")
    p.add_argument("--only", nargs="+", default=[], metavar="STEP",
                   help="Run only these steps (by name or tag)")
    args = p.parse_args()

    today      = datetime.now().strftime("%Y-%m-%d")
    log_dir    = ROOT / "data" / "daily" / today
    log_dir.mkdir(parents=True, exist_ok=True)

    all_steps  = build_steps(args.year)

    # Filter
    if args.only:
        only_set = set(args.only)
        steps = [s for s in all_steps
                 if s.name in only_set or bool(only_set & set(s.tags))]
    else:
        steps = all_steps

    if args.skip:
        skip_set = set(args.skip)
        steps = [s for s in steps
                 if s.name not in skip_set and not (skip_set & set(s.tags))]

    print(f"Operating Narcisystem — {today}")
    print(f"Running {len(steps)} steps  (year={args.year})\n")

    sync_start   = datetime.now()
    results      = []
    aborted_at   = None

    for step in steps:
        # If a required step already failed, skip all remaining steps
        if aborted_at:
            results.append({
                "name":     step.name,
                "status":   "skipped",
                "reason":   f"skipped — run aborted at required step '{aborted_at}'",
                "required": step.required,
            })
            continue

        print(f"  → {step.name:<28}", end=" ", flush=True)
        res = run_step(step, log_dir=log_dir)
        results.append(res)

        status = res["status"]
        dur    = f"({res.get('duration_s', 0):.1f}s)" if "duration_s" in res else ""

        if status == "ok":
            print(f"✓  {dur}")
        elif status == "skipped":
            print(f"⏭  {res.get('reason', '')}")
        else:
            print(f"✗  {dur}  →  {res.get('log', '')}")
            if res.get("stderr_tail"):
                for line in res["stderr_tail"][-2:]:
                    print(f"              {line}")
            # Required step failed — mark abort, remaining steps will be skipped
            if step.required:
                aborted_at = step.name
                print(f"\n  ⛔ Required step '{step.name}' failed — aborting.\n")

    total_s = (datetime.now() - sync_start).total_seconds()

    # Write health summary
    health_path = write_health_summary(
        results, today, args.year, log_dir, total_s, aborted_at
    )

    # Console summary
    ok      = [r for r in results if r["status"] == "ok"]
    skipped = [r for r in results if r["status"] == "skipped"]
    failed  = [r for r in results if r["status"] == "failed"]

    print(f"\n{'='*52}")
    print(f"  ✓ {len(ok):2d} ok   ⏭ {len(skipped):2d} skipped   ✗ {len(failed):2d} failed"
          f"   {total_s:.1f}s total")
    if failed:
        for r in failed:
            req = " [required]" if r.get("required") else ""
            print(f"    ✗ {r['name']}{req}")
    if aborted_at:
        print(f"    ⛔ Aborted at: {aborted_at}")
    print(f"\n  Health summary: {health_path}")
    print(f"{'='*52}\n")

    # ── Push notification ────────────────────────────────────
    _notify_script = ROOT / "scripts" / "notify.py"
    if _notify_script.exists():
        import subprocess as _sp
        if aborted_at or failed:
            _step = aborted_at or (failed[0]["name"] if failed else "unknown")
            _sp.run(
                ["python3", "scripts/notify.py", "sync-fail",
                 "--step", _step],
                cwd=str(ROOT), capture_output=True
            )
        else:
            _sp.run(
                ["python3", "scripts/notify.py", "sync-ok"],
                cwd=str(ROOT), capture_output=True
            )

    return 1 if (aborted_at or failed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
