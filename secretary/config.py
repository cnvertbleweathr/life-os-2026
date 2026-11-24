"""
Secretary settings and templates: load the private YAML, expand template dates,
publish both to DuckDB for dbt (int_events_tiered).

Real files are private and gitignored (the repo is public), like progeny's:

    data/secretary/secretary.yaml          ← secretary/config/secretary.example.yaml
    data/secretary/templates/*.yaml        ← secretary/config/templates/*.example.yaml

Anything written as <LIKE THIS> is a placeholder: that person or template is
skipped until you fill it in. `--check` lists what's left.

Writes (daily_sync step secretary_config, before dbt; the API is stopped):
    secretary.critical_people        one row per name a critical person may appear as
    secretary.template_occurrences   one row per template per date, last year → next year

    uv run python -m secretary.config --check       # what's loaded, what's still a placeholder
    uv run python -m secretary.config --publish     # write the tables
"""

from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = Path(__file__).parent / "config"
TZ = ZoneInfo(os.getenv("ONS_TZ", "America/Denver"))
TIERS = ("critical", "important", "nice_to_know", "trivia")
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
PLACEHOLDER = re.compile(r"<[^<>]+>")

SURFACES = ("paper", "paper_lead", "checkin")

DEFAULT_RHYTHMS: dict[str, list[dict]] = {
    "critical_birthday": [
        {"days_before": 21, "surfaces": ["checkin"], "text": "{name} is {when} ({date}). Gift ideas?"},
        {"days_before": 10, "surfaces": ["paper"], "text": "{name} {when} ({date}): order now if it has to ship."},
        {"days_before": 3, "surfaces": ["paper", "checkin"], "text": "{name} {when}: card and plans sorted?"},
        {"days_before": 0, "surfaces": ["paper_lead"], "text": "Today: {name}."},
    ],
    "critical": [
        {"days_before": 21, "surfaces": ["checkin"], "text": "{name} is {when} ({date}). Anything to prepare?"},
        {"days_before": 10, "surfaces": ["paper"], "text": "{name} {when} ({date})."},
        {"days_before": 3, "surfaces": ["paper", "checkin"], "text": "{name} {when}: all set?"},
        {"days_before": 0, "surfaces": ["paper_lead"], "text": "Today: {name}."},
    ],
    "important": [
        {"days_before": 7, "surfaces": ["paper", "checkin"], "text": "{name} is {when} ({date})."},
        {"days_before": 0, "surfaces": ["paper"], "text": "Today: {name}."},
    ],
    "nice_to_know": [],             # the paper's Coming Up box covers these (coming_up_days)
    "trivia": [
        {"days_before": 0, "surfaces": ["paper"], "text": "Today is {name}."},
    ],
}

DEFAULTS: dict[str, Any] = {
    "critical_people": [],
    "nag_limit": 2,                 # a heads-up shows on at most this many days...
    "critical_daily_days": 3,       # ...except critical ones this close to the event: daily through the day
    "coming_up_days": 14,           # nice_to_know reach for the paper's Coming Up box
    "phone_notifications": False,   # disabled; output is the paper, the website and the Slack packet
    "rhythms": DEFAULT_RHYTHMS,
}


def data_dir() -> Path:
    return Path(os.getenv("ONS_DATA_DIR") or ROOT / "data")


def secretary_dir() -> Path:
    return data_dir() / "secretary"


def db_path() -> Path:
    return Path(os.getenv("ONS_DB_PATH") or ROOT / "data" / "warehouse" / "ons.duckdb")


def today_local() -> date:
    return datetime.now(TZ).date()


def is_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return bool(PLACEHOLDER.search(value))
    if isinstance(value, dict):
        return any(is_placeholder(v) for v in value.values())
    if isinstance(value, list):
        return any(is_placeholder(v) for v in value)
    return False


# ── dates ─────────────────────────────────────────────────────────────────────

def easter(year: int) -> date:
    """Western Easter (anonymous Gregorian algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def nth_weekday(year: int, month: int, weekday: str, nth: int) -> date:
    """nth weekday of a month; nth=-1 is the last one."""
    wd = WEEKDAYS.index(weekday.lower())
    if nth > 0:
        first = date(year, month, 1)
        return first + timedelta(days=(wd - first.weekday()) % 7 + 7 * (nth - 1))
    last = (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1))
    return last - timedelta(days=(last.weekday() - wd) % 7 + 7 * (-nth - 1))


def occurs_on(when: Any, year: int) -> date:
    """`when` is "MM-DD", "easter", or {month, weekday, nth}."""
    if isinstance(when, str) and when.strip().lower() == "easter":
        return easter(year)
    if isinstance(when, str):
        month, day = (int(x) for x in when.strip().split("-"))
        if (month, day) == (2, 29):
            try:
                return date(year, 2, 29)
            except ValueError:
                return date(year, 2, 28)
        return date(year, month, day)
    if isinstance(when, dict):
        return nth_weekday(year, int(when["month"]), str(when["weekday"]), int(when["nth"]))
    raise ValueError(f"can't read when: {when!r}")


# ── loading ───────────────────────────────────────────────────────────────────

@dataclass
class Template:
    key: str
    name: str
    tier: str
    when: Any
    match: list[str] = field(default_factory=list)    # calendar titles this template stands for
    person: str | None = None                          # set for birthday templates
    milestones: list[dict] = field(default_factory=list)
    source: str = ""


@dataclass
class Config:
    settings: dict[str, Any]
    templates: list[Template]
    critical_people: list[dict]                        # {"name", "match": [...]}
    placeholders: list[str]                            # human-readable "fill me in" list
    problems: list[str]                                # unreadable entries
    settings_path: Path | None


def check_milestones(milestones: Any) -> list[dict]:
    """Validate a milestone list; raises ValueError with the reason."""
    if not isinstance(milestones, list):
        raise ValueError("milestones must be a list")
    out = []
    for m in milestones:
        if not isinstance(m, dict):
            raise ValueError(f"milestone must be a mapping, got {m!r}")
        days = m.get("days_before")
        if not isinstance(days, int) or isinstance(days, bool) or days < 0:
            raise ValueError(f"days_before must be a whole number ≥ 0, got {days!r}")
        surfaces = m.get("surfaces") or []
        bad = [s for s in surfaces if s not in SURFACES]
        if not surfaces or bad:
            raise ValueError(f"surfaces must be some of {', '.join(SURFACES)}, got {surfaces!r}")
        if not str(m.get("text") or "").strip():
            raise ValueError(f"milestone {days} days before has no text")
        out.append({"days_before": days, "surfaces": list(surfaces), "text": str(m["text"]).strip()})
    return sorted(out, key=lambda m: -m["days_before"])


def rhythm_for(cfg: "Config", tier: str, *, is_birthday: bool, template_key: str | None = None) -> list[dict]:
    """The milestones an event gets: its template's own, else the tier's default rhythm."""
    t = next((t for t in cfg.templates if t.key == template_key), None) if template_key else None
    if t and t.milestones:
        return t.milestones
    key = "critical_birthday" if tier == "critical" and is_birthday else tier
    return cfg.settings["rhythms"].get(key, [])


def render_text(text: str, *, name: str, on: date, today: date) -> str:
    """{name} the event · {date} "Sat Dec 19" · {days} days to go · {when} "in 18 days" / "tomorrow" /
    "today". Heads-ups re-render daily, so {when} and {days} stay true on every showing."""
    days = (on - today).days
    when = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
    try:
        return text.format(name=name, date=f"{on:%a %b} {on.day}", days=days, when=when)
    except (KeyError, IndexError, ValueError):
        return text                                     # a stray brace shouldn't drop the heads-up


def _read_yaml(path: Path) -> Any:
    with path.open() as f:
        return yaml.safe_load(f)


def _person(entry: Any) -> dict | None:
    if isinstance(entry, str):
        return {"name": entry, "match": [entry]}
    if isinstance(entry, dict) and entry.get("name"):
        match = entry.get("match") or [entry["name"]]
        return {"name": entry["name"], "match": [m for m in match if m]}
    return None


def load(folder: Path | None = None) -> Config:
    folder = folder or secretary_dir()
    placeholders: list[str] = []
    problems: list[str] = []

    settings_path = folder / "secretary.yaml"
    settings = dict(DEFAULTS)
    if settings_path.exists():
        settings.update(_read_yaml(settings_path) or {})
    else:
        settings_path = None
        problems.append(f"no {folder / 'secretary.yaml'}; copy secretary/config/secretary.example.yaml there")
    settings["phone_notifications"] = bool(settings.get("phone_notifications"))

    rhythms = {k: list(v) for k, v in DEFAULT_RHYTHMS.items()}
    for key, value in (settings.get("rhythms") or {}).items():
        try:
            rhythms[key] = check_milestones(value or [])
        except ValueError as e:
            problems.append(f"secretary.yaml rhythms.{key}: {e} (using the default)")
    settings["rhythms"] = rhythms

    people = []
    for entry in settings.get("critical_people") or []:
        p = _person(entry)
        if p is None:
            problems.append(f"critical_people: can't read {entry!r}")
        elif is_placeholder(p):
            placeholders.append(f"secretary.yaml critical_people: {p['name']}")
        else:
            people.append(p)

    templates: list[Template] = []
    for path in sorted((folder / "templates").glob("*.yaml")):
        for raw in _read_yaml(path) or []:
            where = f"templates/{path.name}: {raw.get('name') or raw.get('key') or '?'}"
            if is_placeholder(raw.get("when")) or is_placeholder(raw.get("person")):
                fields = [k for k in ("person", "when") if is_placeholder(raw.get(k))]
                placeholders.append(f"{where} ({', '.join(fields)})")
                continue
            try:
                t = Template(key=str(raw["key"]), name=str(raw["name"]), tier=str(raw["tier"]),
                             when=raw["when"], match=list(raw.get("match") or []),
                             person=raw.get("person"),
                             milestones=check_milestones(raw.get("milestones") or []),
                             source=path.name)
                if t.tier not in TIERS:
                    raise ValueError(f"tier must be one of {', '.join(TIERS)}")
                occurs_on(t.when, 2026)
            except (KeyError, ValueError, TypeError) as e:
                problems.append(f"{where}: {e}")
                continue
            if any(t.key == other.key for other in templates):
                problems.append(f"{where}: key {t.key!r} is used twice; skipped this one")
                continue
            if is_placeholder(t.milestones) or is_placeholder(t.name):
                placeholders.append(f"{where} (text)")
            templates.append(t)

    # A critical-tier birthday template makes its person a critical person, so the
    # calendar's copy of that birthday is critical too (rule 2 runs before templates).
    known = {m.lower() for p in people for m in p["match"]}
    for t in templates:
        if t.person and t.tier == "critical" and t.person.lower() not in known:
            people.append({"name": t.person, "match": [t.person]})
            known.add(t.person.lower())

    return Config(settings, templates, people, placeholders, problems, settings_path)


def occurrences(cfg: Config, today: date) -> list[dict]:
    rows = []
    for t in cfg.templates:
        for year in (today.year - 1, today.year, today.year + 1):
            rows.append({"template_key": t.key, "template_name": t.name, "tier": t.tier,
                         "person": t.person, "occurs_on": occurs_on(t.when, year),
                         "match_titles": [m.lower().replace("’", "'") for m in ([t.name] + t.match)]})
    return rows


# ── publish ───────────────────────────────────────────────────────────────────

def publish(cfg: Config, today: date, path: Path | None = None) -> dict[str, int]:
    import duckdb
    import pandas as pd

    people = pd.DataFrame([{"name": p["name"], "match_name": m} for p in cfg.critical_people for m in p["match"]],
                          columns=["name", "match_name"])
    occ = pd.DataFrame(occurrences(cfg, today),
                       columns=["template_key", "template_name", "tier", "person", "occurs_on", "match_titles"])
    con = duckdb.connect(str(path or db_path()))
    try:
        con.register("people_in", people)
        con.register("occ_in", occ)
        con.execute("BEGIN")
        con.execute("CREATE SCHEMA IF NOT EXISTS secretary")
        con.execute("""CREATE OR REPLACE TABLE secretary.critical_people AS
                       SELECT CAST(name AS VARCHAR) AS name, CAST(match_name AS VARCHAR) AS match_name FROM people_in""")
        con.execute("""CREATE OR REPLACE TABLE secretary.template_occurrences AS
                       SELECT CAST(template_key AS VARCHAR) AS template_key,
                              CAST(template_name AS VARCHAR) AS template_name,
                              CAST(tier AS VARCHAR) AS tier, CAST(person AS VARCHAR) AS person,
                              CAST(occurs_on AS DATE) AS occurs_on,
                              CAST(match_titles AS VARCHAR[]) AS match_titles
                       FROM occ_in""")
        con.execute("COMMIT")
        return {"critical_people": len(people), "template_occurrences": len(occ)}
    finally:
        con.close()


def report(cfg: Config, today: date) -> str:
    lines = [f"settings: {cfg.settings_path or '(none: using defaults)'}",
             f"nag_limit: {cfg.settings['nag_limit']} · critical daily from {cfg.settings['critical_daily_days']} days out"
             f" · phone_notifications: "
             f"{'on' if cfg.settings['phone_notifications'] else 'off'}",
             f"critical people: {len(cfg.critical_people)} · templates: {len(cfg.templates)}"]
    for p in cfg.problems:
        lines.append(f"  ! {p}")
    if cfg.placeholders:
        lines.append(f"Still to fill in ({len(cfg.placeholders)}):")
        lines += [f"  - {p}" for p in cfg.placeholders]
    soon = sorted((o for o in occurrences(cfg, today) if today <= o["occurs_on"] <= today + timedelta(days=60)),
                  key=lambda o: o["occurs_on"])
    if soon:
        lines.append("Templates in the next 60 days, with their heads-ups:")
        for o in soon:
            lines.append(f"  {o['occurs_on']:%a %b %-d}  {o['tier']:<12} {o['template_name']}")
            for m in rhythm_for(cfg, o["tier"], is_birthday=bool(o["person"]), template_key=o["template_key"]):
                on = o["occurs_on"] - timedelta(days=m["days_before"])
                text = render_text(m["text"], name=o["template_name"], on=o["occurs_on"], today=on)
                lines.append(f"      {on:%a %b %-d} → {'+'.join(m['surfaces']):<14} {text}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check", action="store_true", help="show what's loaded and what's still a placeholder")
    p.add_argument("--publish", action="store_true", help="write secretary.* tables (API must be stopped)")
    p.add_argument("--date", type=date.fromisoformat, help="treat this day as today")
    args = p.parse_args(argv)
    today = args.date or today_local()
    cfg = load()
    from secretary import projects as PR
    ps = PR.load()
    print(report(cfg, today))
    print(PR.report(ps, today))
    if args.publish:
        counts = publish(cfg, today)
        pcounts = PR.publish(ps, today)
        print(f"published: {counts['critical_people']} critical-person names, "
              f"{counts['template_occurrences']} template dates, "
              f"{pcounts['projects']} projects with {pcounts['milestones']} milestones")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
