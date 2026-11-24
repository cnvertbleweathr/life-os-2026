"""
Secretary step 2: settings/templates (secretary/config.py) and the tier rules
in dbt's int_events_tiered, built for real against a temp DuckDB.

  uv run --with pytest pytest tests/test_secretary_tiers.py -q
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from secretary import config as SC  # noqa: E402

spec = importlib.util.spec_from_file_location("calendar_export", ROOT / "scripts" / "calendar_export.py")
CE = importlib.util.module_from_spec(spec)
sys.modules.setdefault("calendar_export", CE)
spec.loader.exec_module(CE)

TODAY = date(2026, 11, 27)
NOW = datetime(2026, 11, 27, 4, 0, tzinfo=CE.TZ)

SETTINGS = """
critical_people:
  - name: Jane Doe
    match: [Jane Doe, Janie]
  - name: <MUM'S NAME>
nag_limit: 2
"""
TEMPLATES = {
    "critical.yaml": """
- key: robin_birthday
  name: Robin's birthday
  tier: critical
  person: Robin
  when: "12-12"
- key: wife_birthday
  name: Wife's birthday
  tier: critical
  person: <WIFE'S NAME>
  when: <MM-DD>
- key: mothers_day
  name: Mother's Day
  tier: critical
  when: {month: 5, weekday: sunday, nth: 2}
""",
    "important.yaml": """
- key: thanksgiving
  name: Thanksgiving
  tier: important
  when: {month: 11, weekday: thursday, nth: 4}
  match: [Thanksgiving Day]
- key: easter
  name: Easter
  tier: important
  when: easter
""",
    "trivia.yaml": """
- key: groundhog_day
  name: Groundhog Day
  tier: trivia
  when: "02-02"
- key: broken
  name: Broken
  tier: urgent
  when: "01-01"
""",
}


def write_config(folder: Path) -> None:
    (folder / "templates").mkdir(parents=True, exist_ok=True)
    (folder / "secretary.yaml").write_text(SETTINGS)
    for name, text in TEMPLATES.items():
        (folder / "templates" / name).write_text(text)


# ── dates ─────────────────────────────────────────────────────────────────────

def test_movable_holidays():
    assert SC.easter(2026) == date(2026, 4, 5) and SC.easter(2027) == date(2027, 3, 28)
    assert SC.occurs_on({"month": 5, "weekday": "sunday", "nth": 2}, 2026) == date(2026, 5, 10)    # Mother's Day
    assert SC.occurs_on({"month": 6, "weekday": "sunday", "nth": 3}, 2026) == date(2026, 6, 21)    # Father's Day
    assert SC.occurs_on({"month": 11, "weekday": "thursday", "nth": 4}, 2026) == date(2026, 11, 26)
    assert SC.occurs_on({"month": 5, "weekday": "monday", "nth": -1}, 2026) == date(2026, 5, 25)   # last Monday
    assert SC.occurs_on("02-29", 2027) == date(2027, 2, 28)


# ── loading ───────────────────────────────────────────────────────────────────

def test_placeholders_are_skipped_and_listed(tmp_path):
    write_config(tmp_path)
    cfg = SC.load(tmp_path)
    keys = {t.key for t in cfg.templates}
    assert "wife_birthday" not in keys and "broken" not in keys
    assert any("Wife's birthday" in p and "person" in p and "when" in p for p in cfg.placeholders)
    assert any("<MUM'S NAME>" in p for p in cfg.placeholders)
    assert any("Broken" in p and "tier must be" in p for p in cfg.problems)


def test_critical_birthday_template_makes_its_person_critical(tmp_path):
    write_config(tmp_path)
    names = {p["name"] for p in SC.load(tmp_path).critical_people}
    assert names == {"Jane Doe", "Robin"}


def test_missing_settings_uses_defaults_with_phone_off(tmp_path):
    cfg = SC.load(tmp_path)
    assert cfg.settings["nag_limit"] == 2 and cfg.settings["phone_notifications"] is False
    assert any("secretary.example.yaml" in p for p in cfg.problems)


def test_example_settings_file_has_only_placeholders_for_private_names():
    text = (ROOT / "secretary" / "config" / "secretary.example.yaml").read_text()
    assert "<WIFE'S NAME>" in text and "<MUM'S NAME>" in text


# ── tier rules, through dbt ───────────────────────────────────────────────────

CALENDAR = [
    # (kind, title, date)
    ("primary", "!Preschool tour", date(2026, 11, 30)),
    ("primary", "Dentist", date(2026, 12, 2)),
    ("birthdays", "Jane Doe", date(2026, 11, 28)),            # critical person (by match name)
    ("birthdays", "Sam Example", date(2026, 12, 5)),          # other birthday
    ("birthdays", "Robin Example", date(2026, 12, 12)),         # covered by Robin's template
    ("holidays", "Thanksgiving Day", date(2026, 11, 26)),     # covered by the Thanksgiving template
    ("holidays", "!Thanksgiving Day", date(2026, 11, 26)),    # "!" is never absorbed
    ("holidays", "Flag Day", date(2026, 6, 14)),              # no template
]


@pytest.fixture(scope="module")
def tiered(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("tiers")
    db = tmp / "ons.duckdb"
    write_config(tmp / "secretary")
    cfg = SC.load(tmp / "secretary")
    SC.publish(cfg, TODAY, db)
    rows = [{"calendar_id": kind, "calendar_name": kind, "calendar_kind": kind, "event_id": f"e{i}",
             "title": title, "event_type": "birthday" if kind == "birthdays" else "default", "all_day": True,
             "start_date": d, "start_at": None, "end_at": None, "location": None, "status": "confirmed",
             "synced_at": NOW} for i, (kind, title, d) in enumerate(CALENDAR)]
    CE.write_warehouse(rows, db)

    (tmp / "profiles").mkdir()
    (tmp / "profiles" / "profiles.yml").write_text(
        f"ons:\n  target: dev\n  outputs:\n    dev:\n      type: duckdb\n      path: {db}\n      schema: main\n      threads: 1\n")
    dbt = shutil.which("dbt") or str(ROOT / ".venv" / "bin" / "dbt")
    proc = subprocess.run(
        [dbt, "build", "--select", "+int_events_tiered", "--profiles-dir", str(tmp / "profiles"),
         "--project-dir", str(ROOT / "dbt"), "--target-path", str(tmp / "target"), "--log-path", str(tmp / "logs")],
        capture_output=True, text=True, cwd=ROOT, env={**os.environ, "DBT_SEND_ANONYMOUS_USAGE_STATS": "false"})
    assert proc.returncode == 0, proc.stdout[-3000:]
    con = duckdb.connect(str(db), read_only=True)
    out = con.execute("SELECT display_title, event_date, tier, tier_rule, source, raw_title "
                      "FROM main_intermediate.int_events_tiered").fetchall()
    con.close()
    return {"rows": out, "dbt": proc.stdout}


def find(tiered, title, d=None):
    hits = [r for r in tiered["rows"] if r[0] == title and (d is None or r[1] == d)]
    assert hits, f"{title} not in int_events_tiered"
    return hits


def test_bang_event_is_critical_and_display_drops_the_bang(tiered):
    [r] = find(tiered, "Preschool tour")
    assert r[2:4] == ("critical", "bang") and r[5] == "!Preschool tour"


def test_birthdays(tiered):
    assert find(tiered, "Jane Doe")[0][2:4] == ("critical", "critical_person_birthday")
    assert find(tiered, "Sam Example")[0][2:4] == ("important", "birthday")


def test_template_birthday_replaces_the_calendar_copy(tiered):
    assert not [r for r in tiered["rows"] if r[0] == "Robin Example"]
    [r] = find(tiered, "Robin's birthday", date(2026, 12, 12))
    assert r[2:5] == ("critical", "critical_person_birthday", "template")


def test_holiday_template_sets_the_tier_and_absorbs_the_holiday_calendar(tiered):
    thanksgiving = [r for r in tiered["rows"] if r[1] == date(2026, 11, 26)]
    assert sorted((r[0], r[2], r[3]) for r in thanksgiving) == [
        ("Thanksgiving", "important", "template"),
        ("Thanksgiving Day", "critical", "bang"),           # the "!" copy survives, as critical
    ]
    assert find(tiered, "Groundhog Day", date(2027, 2, 2))[0][2] == "trivia"
    assert find(tiered, "Mother's Day", date(2026, 5, 10))[0][2] == "critical"
    assert find(tiered, "Easter", date(2027, 3, 28))[0][2] == "important"


def test_everything_else_is_nice_to_know(tiered):
    assert find(tiered, "Dentist")[0][2:4] == ("nice_to_know", "default")
    assert find(tiered, "Flag Day")[0][2:4] == ("nice_to_know", "default")


def test_dbt_schema_tests_ran(tiered):
    assert "accepted_values_int_events_tiered_tier" in tiered["dbt"]
    assert "unique_int_events_tiered_event_key" in tiered["dbt"]
