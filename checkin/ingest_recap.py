"""
Secretary step 8: read check-in RECAPs (docs/context/checkin-protocol.md) and act on them.

A RECAP is pasted on the website (Check-in → Paste RECAP), which appends it to
data/checkin/recaps.jsonl. The sync's ingest_recap step runs this before secretary_config, so
what it records is published the same morning. Each recap is applied once; results go to
data/checkin/recap_ingest.jsonl (the website shows them).

  Done: <project> — <milestone>
      Marks the milestone done in data/secretary/milestone_log.jsonl (by "recap", on the recap's
      date), exactly like `python -m secretary.projects --done`. Names are matched exactly
      (case and punctuation aside), then by close spelling, which is reported.
  New project: <name> | deadline <YYYY-MM-DD> | tier <tier> | <notes>
      Adds a DRAFT to data/secretary/projects.proposed.yaml with suggested milestones. Never
      active: you review it and move it into projects.yaml. Skipped when a project of that name
      already exists or is already proposed.
  New critical person: <name>
      Proposes the person in data/secretary/secretary.proposed.yaml, for you to copy into
      secretary.yaml's critical_people. Skipped when already critical or already proposed.

The other keys (Wins, Top 3 next week, Decisions, Parking lot, Commitments) are parsed and kept
with the result, for later use. This writes files only, never DuckDB, so it's safe any time.

  python -m checkin.ingest_recap                 # the sync step: apply new recaps
  python -m checkin.ingest_recap --preview FILE  # show what a RECAP would do; writes nothing
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.store import JsonlLog, timestamp, today_local  # noqa: E402
from secretary import config as SC  # noqa: E402
from secretary import projects as PR  # noqa: E402

LIST_KEYS = {"wins": "wins", "top 3 next week": "top3", "decisions": "decisions",
             "parking lot": "parking_lot", "commitments": "commitments"}
DASH = re.compile(r"\s+(?:—|–|--|-)\s+")
LINE = re.compile(r"^\s*(?:[-*•]\s*)?\**\s*([A-Za-z0-9 ]+?)\s*\**\s*:\s*\**\s*(.*?)\s*$")
HEADER = re.compile(r"^\s*\**\s*RECAP\b\s*\**\s*(\d{4}-\d{2}-\d{2})?", re.I)
PROPOSED_PROJECTS = "projects.proposed.yaml"
PROPOSED_SETTINGS = "secretary.proposed.yaml"


def recaps_log() -> JsonlLog:
    return JsonlLog("checkin", "recaps.jsonl")


def results_log() -> JsonlLog:
    return JsonlLog("checkin", "recap_ingest.jsonl")


def norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").lower()
    s = re.sub(r"\(deadline\)", "", s)
    return re.sub(r"\s+", " ", s).strip(" .;:,*_`'\"")


# ── parse ────────────────────────────────────────────────────────────────────

@dataclass
class Recap:
    date: date | None
    sections: dict[str, list[str]] = field(default_factory=dict)
    done: list[tuple[str, str]] = field(default_factory=list)              # (project, milestone) as written
    new_projects: list[dict[str, Any]] = field(default_factory=list)
    new_people: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def parse(text: str) -> Recap:
    lines = [l.strip().strip("`") for l in (text or "").splitlines()]
    lines = [l for l in lines if l and not l.startswith("```")]
    if not lines or not HEADER.match(lines[0]):
        raise ValueError("a RECAP starts with a line like 'RECAP 2026-12-04'")
    m = HEADER.match(lines[0])
    r = Recap(date=date.fromisoformat(m.group(1)) if m.group(1) else None)
    if r.date is None:
        r.problems.append("no date on the RECAP line; used the day it was pasted")
    for line in lines[1:]:
        lm = LINE.match(line)
        if not lm:
            r.problems.append(f"not a RECAP line: {line[:80]}")
            continue
        key, value = norm(lm.group(1)), lm.group(2).strip()
        if not value:
            continue
        if key in LIST_KEYS:
            if key == "top 3 next week":
                items = [x.strip(" ;") for x in re.split(r"\s*\d\)\s*", value) if x.strip(" ;")]
            else:
                items = [x.strip() for x in value.split(";") if x.strip()]
            r.sections.setdefault(LIST_KEYS[key], []).extend(items)
        elif key == "done":
            parts = DASH.split(value, maxsplit=1)
            if len(parts) != 2:
                r.problems.append(f"Done line needs '<project> — <milestone>': {value[:80]}")
            else:
                r.done.append((parts[0].strip(), parts[1].strip()))
        elif key == "new project":
            r.new_projects.append(_project_line(value, r))
        elif key == "new critical person":
            r.new_people.append(value.strip(" ."))
        else:
            r.problems.append(f"unknown key '{lm.group(1)}': kept out of ONS")
    r.new_projects = [p for p in r.new_projects if p]
    return r


def _project_line(value: str, r: Recap) -> dict[str, Any] | None:
    parts = [p.strip() for p in value.split("|")]
    if not parts[0]:
        r.problems.append(f"New project line has no name: {value[:80]}")
        return None
    out: dict[str, Any] = {"name": parts[0], "deadline": None, "tier": "important", "notes": []}
    for p in parts[1:]:
        low = p.lower()
        if low.startswith("deadline"):
            raw = p[len("deadline"):].strip(" :")
            try:
                out["deadline"] = date.fromisoformat(raw[:10])
            except ValueError:
                r.problems.append(f"New project '{parts[0]}': deadline must be YYYY-MM-DD, got '{raw}'")
        elif low.startswith("tier"):
            tier = p[len("tier"):].strip(" :").lower().replace(" ", "_")
            if tier in SC.TIERS:
                out["tier"] = tier
            else:
                r.problems.append(f"New project '{parts[0]}': tier '{tier}' isn't one of {', '.join(SC.TIERS)}; used important")
        elif p:
            out["notes"].append(p)
    out["notes"] = " | ".join(out["notes"])
    return out


# ── plan: match against what ONS knows ───────────────────────────────────────

def _match(name: str, options: dict[str, Any]) -> tuple[Any, bool]:
    """(value, by_spelling). Exact normalized match, else a close spelling (reported by the caller), else None."""
    n = norm(name)
    if n in options:
        return options[n], False
    close = difflib.get_close_matches(n, list(options), n=1, cutoff=0.82)
    if close:
        return options[close[0]], True
    return None, False


def plan(r: Recap, today: date) -> dict[str, Any]:
    on = r.date or today
    ps = PR.load()
    cfg = SC.load()
    out: dict[str, Any] = {"done": [], "projects": [], "people": [], "skipped": [], "problems": list(r.problems)}

    by_name: dict[str, PR.Project] = {}
    for p in ps.projects:
        by_name[norm(p.name)] = p
        by_name[norm(p.key)] = p
    for project, milestone in r.done:
        p, fuzzy_p = _match(project, by_name)
        if p is None:
            out["problems"].append(f"Done: no project named '{project}' (known: {', '.join(x.name for x in ps.projects) or 'none'})")
            continue
        ms_by = {}
        for m in p.milestones:
            ms_by[norm(m.title)] = m
            ms_by[norm(m.key)] = m
        m, fuzzy_m = _match(milestone, ms_by)
        if m is None:
            out["problems"].append(f"Done: '{p.name}' has no milestone '{milestone}' "
                                   f"(its milestones: {'; '.join(x.title for x in p.milestones)})")
            continue
        notes = ([f"read '{project}' as '{p.name}'"] if fuzzy_p else []) + \
                ([f"read '{milestone}' as '{m.title}'"] if fuzzy_m else [])
        out["done"].append({"project": p.key, "milestone": m.key, "label": f"{p.name} — {m.title}", "on": on.isoformat(),
                            "already": m.done_on is not None, "note": "; ".join(notes) or None})

    proposed = _read_list(SC.secretary_dir() / PROPOSED_PROJECTS)
    taken = set(by_name) | {norm(x.get("name", "")) for x in proposed} | {norm(x.get("key", "")) for x in proposed}
    for np in r.new_projects:
        if norm(np["name"]) in by_name:
            out["skipped"].append(f"New project '{np['name']}': already a project")
            continue
        if norm(np["name"]) in taken:
            out["skipped"].append(f"New project '{np['name']}': already proposed")
            continue
        taken.add(norm(np["name"]))
        out["projects"].append(proposed_project(np, on))

    known = {norm(m) for p in cfg.critical_people for m in p["match"]} | {norm(p["name"]) for p in cfg.critical_people}
    settings_proposed = _read_map(SC.secretary_dir() / PROPOSED_SETTINGS).get("critical_people") or []
    known_proposed = {norm(x.get("name", "")) for x in settings_proposed if isinstance(x, dict)}
    for person in r.new_people:
        if norm(person) in known:
            out["skipped"].append(f"New critical person '{person}': already critical")
        elif norm(person) in known_proposed:
            out["skipped"].append(f"New critical person '{person}': already proposed")
        else:
            known_proposed.add(norm(person))
            out["people"].append({"name": person, "match": [person], "proposed_on": on.isoformat()})
    return out


def proposed_project(np: dict[str, Any], on: date) -> dict[str, Any]:
    """A draft with suggested milestones: list the steps soon, a halfway check for longer runs, the deadline."""
    key = PR.slug(np["name"])
    ms: list[dict[str, Any]] = [{"key": "plan", "title": "List the steps and who does them",
                                 "due": (on + timedelta(days=3)).isoformat()}]
    dl = np.get("deadline")
    if dl:
        if (dl - on).days >= 14:
            ms.append({"key": "halfway", "title": "Halfway check: on track?",
                       "due": (on + (dl - on) / 2).isoformat()})
        ms.append({"key": "deadline", "title": "Deadline", "due": dl.isoformat(), "deadline": True})
    entry = {"key": key, "name": np["name"], "tier": np["tier"], "status": "draft"}
    if np.get("notes"):
        entry["notes"] = np["notes"]
    entry["proposed"] = f"from the RECAP of {on.isoformat()}"
    entry["milestones"] = ms
    return entry


# ── apply ────────────────────────────────────────────────────────────────────

PROJECTS_HEADER = """# Projects proposed by check-in RECAPs (checkin/ingest_recap.py). Never active on their own.
# To start one: review the milestones, move the entry into projects.yaml, set status: active.
# To drop one: delete it here. (data/** is gitignored; this file stays private.)
"""
SETTINGS_HEADER = """# Critical people proposed by check-in RECAPs (checkin/ingest_recap.py).
# To confirm one: copy it into secretary.yaml's critical_people (fix `match` to how the name
# appears in your calendar's birthdays), then delete it here.
"""


def _read_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text()) or []
    return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []


def _read_map(path: Path) -> dict:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    return data if isinstance(data, dict) else {}


def _write(path: Path, header: str, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(header + "\n" + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100))
    tmp.replace(path)


def apply(p: dict[str, Any]) -> None:
    for d in p["done"]:
        if not d["already"]:
            PR.record_completion(d["project"], d["milestone"], by="recap", on=date.fromisoformat(d["on"]))
    folder = SC.secretary_dir()
    if p["projects"]:
        path = folder / PROPOSED_PROJECTS
        _write(path, PROJECTS_HEADER, _read_list(path) + p["projects"])
    if p["people"]:
        path = folder / PROPOSED_SETTINGS
        current = _read_map(path)
        current["critical_people"] = (current.get("critical_people") or []) + p["people"]
        _write(path, SETTINGS_HEADER, current)


def submit(text: str, source: str = "web") -> dict[str, Any]:
    """Queue a pasted RECAP (the website's POST). Parses first so a malformed paste is refused."""
    r = parse(text)
    row = recaps_log().append({"recap_id": uuid.uuid4().hex, "recap_date": (r.date or today_local()).isoformat(),
                               "submitted_at": timestamp(), "source": source, "text": text.strip()})
    return {**row, "preview": plan(r, today_local())}


def ingest(today: date | None = None) -> list[dict[str, Any]]:
    """Apply every queued RECAP not applied yet, oldest first. Returns the result rows written."""
    today = today or today_local()
    seen = set(results_log().latest_by("recap_id"))
    written = []
    for row in recaps_log().rows():
        rid = row.get("recap_id")
        if not rid or rid in seen:
            continue
        seen.add(rid)
        try:
            r = parse(row.get("text", ""))
            p = plan(r, today)
            apply(p)
            result = {"recap_id": rid, "recap_date": row.get("recap_date"), "ingested_at": timestamp(), "ok": True,
                      "done": [d["label"] + (" (already done)" if d["already"] else "") + (f" [{d['note']}]" if d["note"] else "")
                               for d in p["done"]],
                      "proposed_projects": [x["name"] for x in p["projects"]],
                      "proposed_people": [x["name"] for x in p["people"]],
                      "skipped": p["skipped"], "problems": p["problems"], "sections": r.sections}
        except Exception as e:                           # one bad recap never blocks the others
            result = {"recap_id": rid, "recap_date": row.get("recap_date"), "ingested_at": timestamp(), "ok": False,
                      "problems": [f"couldn't apply: {e}"]}
        written.append(results_log().append(result))
    return written


def describe(p: dict[str, Any]) -> list[str]:
    lines = []
    for d in p["done"]:
        extra = (" (already done)" if d["already"] else "") + (f" [{d['note']}]" if d["note"] else "")
        lines.append(f"done: {d['label']}{extra}")
    lines += [f"propose project: {x['name']} ({x['tier']}, {len(x['milestones'])} milestones)" for x in p["projects"]]
    lines += [f"propose critical person: {x['name']}" for x in p["people"]]
    lines += [f"skip: {s}" for s in p["skipped"]]
    lines += [f"problem: {s}" for s in p["problems"]]
    return lines or ["nothing for ONS to do"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preview", metavar="FILE", help="show what a RECAP in FILE would do; writes nothing")
    args = ap.parse_args(argv)
    if args.preview:
        try:
            r = parse(Path(args.preview).read_text())
        except ValueError as e:
            print(f"✗ {e}", file=sys.stderr)
            return 1
        print("\n".join(describe(plan(r, today_local()))))
        return 0
    results = ingest()
    if not results:
        print("no new RECAPs")
    for res in results:
        print(f"RECAP {res.get('recap_date')}: " + ("ok" if res["ok"] else "FAILED") + " · " +
              "; ".join(f"{k} {len(res.get(k) or [])}" for k in ("done", "proposed_projects", "proposed_people",
                                                                 "skipped", "problems")))
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
