"""
Stage 1: run every tool and assemble the day's snapshot.

The snapshot is the agent's whole view of the world. Stage 2's writer sees only
this, and stage 3's grounding check compares the brief against `facts()`, the
flat {"running.miles_7d": 12.4, ...} form of it.

One broken tool never sinks the brief: its section carries an `error` and the
rest still runs.

    python -m agents.morning_brief.snapshot                # today, full JSON
    python -m agents.morning_brief.snapshot --facts        # flat fact ids only
    python -m agents.morning_brief.snapshot --date 2026-11-10 --save

--save writes data/ai/morning_brief/snapshots/<date>.json (gitignored). Saved
snapshots become the eval set in stage 5, so save the odd days too: a broken
streak, a week off running, a day with nothing on the calendar.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import duckdb

from api.store import data_dir, local_tz, now_local, today_local
from agents.morning_brief.tools import DB_PATH, TOOLS, Ctx, ToolResult


def build_snapshot(today: date | None = None, db_path: Path | str | None = None) -> dict[str, Any]:
    today = today or today_local()
    try:
        con = duckdb.connect(str(db_path or DB_PATH), read_only=True)
    except duckdb.IOException as e:
        raise SystemExit(
            f"Can't open the warehouse read-only ({e}). If the daily sync or dbt is "
            "writing right now, wait for it to finish."
        ) from e

    sections: dict[str, dict] = {}
    try:
        ctx = Ctx(con=con, today=today, tz=local_tz())
        for tool in TOOLS:
            try:
                result = tool(ctx)
            except Exception as e:   # one bad tool shouldn't sink the brief
                result = ToolResult(tool.__name__, error=f"{type(e).__name__}: {e}")
            sections[result.name] = result.to_dict()
    finally:
        con.close()

    return {
        "date": today.isoformat(),
        "weekday": today.strftime("%A"),
        "generated_at": now_local().isoformat(timespec="seconds"),
        "sections": sections,
    }


def facts(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Flatten a snapshot to {"<tool>.<fact>": value}: the grounding contract."""
    return {
        f"{name}.{key}": value
        for name, section in snapshot["sections"].items()
        for key, value in section["facts"].items()
    }


def snapshot_path(day: date | str) -> Path:
    return data_dir() / "ai" / "morning_brief" / "snapshots" / f"{day}.json"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", type=date.fromisoformat, help="build as of this day (default: today)")
    p.add_argument("--facts", action="store_true", help="print flat fact ids instead of the full snapshot")
    p.add_argument("--save", action="store_true", help="also save to data/ai/morning_brief/snapshots/")
    args = p.parse_args(argv)

    snap = build_snapshot(args.date)
    out = facts(snap) if args.facts else snap
    print(json.dumps(out, indent=2, default=str))

    problems = {n: s["error"] or "stale" for n, s in snap["sections"].items() if s["error"] or s["stale"]}
    if problems:
        print("\nheads up: " + ", ".join(f"{n} ({why})" for n, why in problems.items()), file=sys.stderr)
    if args.save:
        path = snapshot_path(snap["date"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snap, indent=2, default=str))
        print(f"saved {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
