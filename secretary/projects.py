"""
Secretary step 6: life projects, with dated milestones the secretary follows up on.

The real file is data/secretary/projects.yaml (gitignored); secretary/config/
projects.example.yaml is the committed template, placeholders only.

  - key: preschool                  stable id: never rename (completions refer to it)
    name: Sam's preschool           how it reads everywhere
    tier: critical                  critical | important | nice_to_know | trivia
    status: active                  active | draft | done | dropped (only active ones get heads-ups)
    notes: free text
    milestones:
      - key: apply                  optional; defaults to a slug of the title
        title: Application opens
        due: 2026-12-01             a date, or "2027-01-19 16:00" for a time (America/Denver)
        deadline: true              optional: a hard deadline (reads "deadline" everywhere)
        done: 2026-12-02            optional: mark it done by hand

Completions also come from data/secretary/milestone_log.jsonl (one line per "done" or
"reopen"; written by `--done`, and by the check-in RECAP in step 8). The latest line per
milestone wins over the yaml's `done:`.

The sync's secretary_config step publishes secretary.projects and
secretary.project_milestones (status open | done, overdue computed against today).
dbt's int_events_tiered turns the open milestones of active projects into dated events with
the project's tier, so heads-ups, the paper, the website and the packet all see them.

  python -m secretary.projects --check
  python -m secretary.projects --done preschool apply     # queue a completion (safe anytime)
  python -m secretary.projects --reopen preschool apply
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secretary import config as SC  # noqa: E402

STATUSES = ("active", "draft", "done", "dropped")
FILE = "projects.yaml"


@dataclass
class Milestone:
    key: str
    title: str
    due: date
    due_time: time | None = None
    deadline: bool = False
    done_on: date | None = None
    done_by: str | None = None          # yaml · cli · recap · website

    @property
    def due_at(self) -> datetime | None:
        return datetime.combine(self.due, self.due_time, SC.TZ) if self.due_time else None


@dataclass
class Project:
    key: str
    name: str
    tier: str
    status: str
    notes: str = ""
    milestones: list[Milestone] = field(default_factory=list)


@dataclass
class Projects:
    projects: list[Project]
    placeholders: list[str]
    problems: list[str]
    path: Path | None


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "milestone"


def parse_due(value: Any) -> tuple[date, time | None]:
    if isinstance(value, datetime):
        return value.date(), value.time().replace(second=0, microsecond=0)
    if isinstance(value, date):
        return value, None
    s = str(value).strip()
    try:
        if " " in s or "T" in s:
            dt = datetime.fromisoformat(s.replace("T", " "))
            return dt.date(), dt.time().replace(second=0, microsecond=0)
        return date.fromisoformat(s), None
    except ValueError:
        raise ValueError(f"due must be YYYY-MM-DD or 'YYYY-MM-DD HH:MM', not {value!r}") from None


def completion_log():
    from api.store import JsonlLog
    return JsonlLog("secretary", "milestone_log.jsonl")


def milestone_id(project_key: str, milestone_key: str) -> str:
    return f"{project_key}/{milestone_key}"


def record_completion(project_key: str, milestone_key: str, *, done: bool = True, by: str = "cli",
                      on: date | None = None) -> dict:
    """Append a done / reopen line. Safe while the API runs; the next sync publishes it."""
    return completion_log().append({
        "id": milestone_id(project_key, milestone_key), "project": project_key, "milestone": milestone_key,
        "status": "done" if done else "open", "on": (on or SC.today_local()).isoformat(), "by": by,
        "at": datetime.now(SC.TZ).isoformat(timespec="seconds"),
    })


def load(folder: Path | None = None) -> Projects:
    folder = folder or SC.secretary_dir()
    path = folder / FILE
    placeholders: list[str] = []
    problems: list[str] = []
    if not path.exists():
        return Projects([], [], [], None)
    raw_list = SC._read_yaml(path) or []
    if not isinstance(raw_list, list):
        return Projects([], [], [f"{FILE}: expected a list of projects"], path)
    log = completion_log().latest_by("id")

    projects: list[Project] = []
    for raw in raw_list:
        where = f"{FILE}: {raw.get('name') or raw.get('key') or '?'}" if isinstance(raw, dict) else f"{FILE}: {raw!r}"
        if not isinstance(raw, dict):
            problems.append(f"{where}: expected a mapping")
            continue
        if SC.is_placeholder(raw):
            placeholders.append(f"{where} (has <PLACEHOLDERS>)")
            continue
        try:
            p = Project(key=str(raw["key"]), name=str(raw["name"]), tier=str(raw.get("tier", "important")),
                        status=str(raw.get("status", "active")), notes=str(raw.get("notes") or "").strip())
            if p.tier not in SC.TIERS:
                raise ValueError(f"tier must be one of {', '.join(SC.TIERS)}")
            if p.status not in STATUSES:
                raise ValueError(f"status must be one of {', '.join(STATUSES)}")
            for m in raw.get("milestones") or []:
                due, due_time = parse_due(m["due"])
                ms = Milestone(key=str(m.get("key") or slug(str(m["title"]))), title=str(m["title"]).strip(),
                               due=due, due_time=due_time, deadline=bool(m.get("deadline")))
                if m.get("done"):
                    ms.done_on, ms.done_by = parse_due(m["done"])[0], "yaml"
                entry = log.get(milestone_id(p.key, ms.key))
                if entry and entry.get("status") == "done":
                    ms.done_on, ms.done_by = date.fromisoformat(entry.get("on") or SC.today_local().isoformat()), entry.get("by")
                elif entry and entry.get("status") == "open":
                    ms.done_on = ms.done_by = None
                if any(o.key == ms.key for o in p.milestones):
                    raise ValueError(f"milestone key {ms.key!r} is used twice")
                p.milestones.append(ms)
        except (KeyError, ValueError, TypeError) as e:
            problems.append(f"{where}: {e}")
            continue
        if any(o.key == p.key for o in projects):
            problems.append(f"{where}: key {p.key!r} is used twice; skipped this one")
            continue
        p.milestones.sort(key=lambda m: (m.due, m.due_time or time(0)))
        projects.append(p)
    return Projects(projects, placeholders, problems, path)


def milestone_rows(ps: Projects, today: date) -> list[dict]:
    rows = []
    for p in ps.projects:
        for m in p.milestones:
            rows.append({
                "project_key": p.key, "project_name": p.name, "tier": p.tier, "project_status": p.status,
                "milestone_key": m.key, "title": m.title, "due_date": m.due, "due_at": m.due_at,
                "is_deadline": m.deadline, "status": "done" if m.done_on else "open",
                "done_on": m.done_on, "done_by": m.done_by,
                "is_overdue": m.done_on is None and m.due < today,
            })
    return rows


def publish(ps: Projects, today: date, path: Path | None = None) -> dict[str, int]:
    import duckdb
    import pandas as pd

    projects = pd.DataFrame([{"project_key": p.key, "name": p.name, "tier": p.tier, "status": p.status,
                              "notes": p.notes} for p in ps.projects],
                            columns=["project_key", "name", "tier", "status", "notes"])
    ms = pd.DataFrame(milestone_rows(ps, today),
                      columns=["project_key", "project_name", "tier", "project_status", "milestone_key", "title",
                               "due_date", "due_at", "is_deadline", "status", "done_on", "done_by", "is_overdue"])
    con = duckdb.connect(str(path or SC.db_path()))
    try:
        con.register("projects_in", projects)
        con.register("ms_in", ms)
        con.execute("BEGIN")
        con.execute("CREATE SCHEMA IF NOT EXISTS secretary")
        con.execute("""CREATE OR REPLACE TABLE secretary.projects AS
                       SELECT CAST(project_key AS VARCHAR) AS project_key, CAST(name AS VARCHAR) AS name,
                              CAST(tier AS VARCHAR) AS tier, CAST(status AS VARCHAR) AS status,
                              CAST(notes AS VARCHAR) AS notes FROM projects_in""")
        con.execute("""CREATE OR REPLACE TABLE secretary.project_milestones AS
                       SELECT CAST(project_key AS VARCHAR) AS project_key, CAST(project_name AS VARCHAR) AS project_name,
                              CAST(tier AS VARCHAR) AS tier, CAST(project_status AS VARCHAR) AS project_status,
                              CAST(milestone_key AS VARCHAR) AS milestone_key, CAST(title AS VARCHAR) AS title,
                              CAST(due_date AS DATE) AS due_date, CAST(due_at AS TIMESTAMPTZ) AS due_at,
                              CAST(is_deadline AS BOOLEAN) AS is_deadline, CAST(status AS VARCHAR) AS status,
                              CAST(done_on AS DATE) AS done_on, CAST(done_by AS VARCHAR) AS done_by,
                              CAST(is_overdue AS BOOLEAN) AS is_overdue
                       FROM ms_in""")
        con.execute("COMMIT")
        return {"projects": len(projects), "milestones": len(ms)}
    finally:
        con.close()


def fmt_due(m: Milestone) -> str:
    s = f"{m.due:%a %b} {m.due.day}"
    if m.due_time:
        s += " " + f"{m.due_time:%-I:%M%p}".lower().replace(":00", "")
    return s


def report(ps: Projects, today: date) -> str:
    lines = [f"projects: {ps.path or '(no projects.yaml)'} · {len(ps.projects)} loaded"]
    lines += [f"  ! {p}" for p in ps.problems]
    if ps.placeholders:
        lines.append(f"Still to fill in ({len(ps.placeholders)}):")
        lines += [f"  - {p}" for p in ps.placeholders]
    for p in ps.projects:
        lines.append(f"  {p.name} [{p.key}] · {p.tier} · {p.status}")
        for m in p.milestones:
            state = (f"done {m.done_on} ({m.done_by})" if m.done_on
                     else "OVERDUE" if m.due < today else f"in {(m.due - today).days} days")
            lines.append(f"      {fmt_due(m):<16} {m.title}{' (deadline)' if m.deadline else ''}  [{m.key}] · {state}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="show projects, milestones and what's left to fill in")
    ap.add_argument("--done", nargs=2, metavar=("PROJECT", "MILESTONE"), help="queue a completion")
    ap.add_argument("--reopen", nargs=2, metavar=("PROJECT", "MILESTONE"), help="undo a completion")
    ap.add_argument("--date", type=date.fromisoformat, help="treat this day as today")
    args = ap.parse_args(argv)
    today = args.date or SC.today_local()
    for flag, done in (("done", True), ("reopen", False)):
        pair = getattr(args, flag)
        if pair:
            ps = load()
            p = next((p for p in ps.projects if p.key == pair[0]), None)
            if not p or not any(m.key == pair[1] for m in p.milestones):
                keys = ", ".join(f"{p.key}/{m.key}" for p in ps.projects for m in p.milestones)
                print(f"no milestone {pair[0]}/{pair[1]}; known: {keys or 'none'}", file=sys.stderr)
                return 1
            record_completion(pair[0], pair[1], done=done, by="cli", on=today)
            print(f"{'done' if done else 'reopened'}: {pair[0]}/{pair[1]} (published at the next sync)")
            return 0
    print(report(load(), today))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
