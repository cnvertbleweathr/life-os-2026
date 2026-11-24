"""
Secretary step 3: starter templates and heads-up rhythms (secretary/config.py).

The committed examples hold placeholders only (public repo); the real files are
data/secretary/ (gitignored). Everything here runs on temp copies.

  uv run --with pytest pytest tests/test_secretary_templates.py -q
"""

from __future__ import annotations

import re
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from secretary import config as SC  # noqa: E402

EXAMPLES = ROOT / "secretary" / "config"


def examples_as_real(tmp_path: Path) -> Path:
    folder = tmp_path / "secretary"
    (folder / "templates").mkdir(parents=True)
    shutil.copy(EXAMPLES / "secretary.example.yaml", folder / "secretary.yaml")
    for f in (EXAMPLES / "templates").glob("*.example.yaml"):
        shutil.copy(f, folder / "templates" / f.name.replace(".example", ""))
    return folder


def test_examples_load_cleanly_and_list_what_to_fill_in(tmp_path):
    cfg = SC.load(examples_as_real(tmp_path))
    assert cfg.problems == []
    keys = {t.key for t in cfg.templates}
    assert {"mothers_day", "fathers_day", "christmas", "thanksgiving", "halloween", "valentines_day",
            "easter", "groundhog_day", "flag_day"} <= keys
    todo = "\n".join(cfg.placeholders)
    for name in ("wife_birthday", "child_birthday", "mum_birthday", "anniversary"):
        assert name not in keys
    for label in ("<WIFE'S NAME>'s birthday", "<CHILD'S NAME>'s birthday", "Mum's birthday",
                  "Wedding anniversary", "<WIFE'S NAME>", "<MUM'S NAME>", "<CHILD'S NAME>"):
        assert label in todo
    assert {t.tier for t in cfg.templates if t.source == "trivia.yaml"} == {"trivia"}


def private_values() -> set[str]:
    """Names and birthday dates from the real, gitignored data/secretary/ files, read at
    test time so they never have to be written into this (public) repo."""
    real = ROOT / "data" / "secretary"
    if not real.exists():
        return set()
    cfg = SC.load(real)
    values = {m for p in cfg.critical_people for m in p["match"]}
    values |= {t.person for t in cfg.templates if t.person}
    values |= {t.when for t in cfg.templates if t.person and isinstance(t.when, str)}
    return {v for v in values if v and len(v) > 2}


def test_committed_files_hold_no_private_details():
    committed = list(EXAMPLES.rglob("*.yaml")) + list((ROOT / "secretary").glob("*.py")) + \
        list((ROOT / "tests").glob("test_secretary*.py"))
    text = "\n".join(p.read_text() for p in committed)
    for private in private_values():
        assert private not in text, "a name or date from data/secretary/ is in a committed file"
    # in the examples, birthdays and anniversaries are placeholders, not dates
    text = "\n".join(p.read_text() for p in EXAMPLES.rglob("*.yaml"))
    blocks = re.findall(r"- key: (?:wife_birthday|child_birthday|mum_birthday|anniversary)(?:(?!\n- key).)*",
                        text, re.S)
    assert len(blocks) == 4
    for block in blocks:
        assert "when: <MM-DD>" in block


def test_rhythms_match_the_spec(tmp_path):
    cfg = SC.load(examples_as_real(tmp_path))
    days = lambda ms: [m["days_before"] for m in ms]
    crit_bday = SC.rhythm_for(cfg, "critical", is_birthday=True)
    assert days(crit_bday) == [21, 10, 3, 0]
    assert [m["surfaces"] for m in crit_bday] == [["checkin"], ["paper"], ["paper", "checkin"], ["paper_lead"]]
    assert "Gift ideas?" in crit_bday[0]["text"] and "ship" in crit_bday[1]["text"]
    assert days(SC.rhythm_for(cfg, "important", is_birthday=True)) == [7, 0]       # other birthdays
    assert days(SC.rhythm_for(cfg, "important", is_birthday=False)) == [7, 0]
    assert SC.rhythm_for(cfg, "nice_to_know", is_birthday=False) == []            # Coming Up box only
    assert days(SC.rhythm_for(cfg, "trivia", is_birthday=False)) == [0]
    assert cfg.settings["coming_up_days"] == 14


def test_templates_bring_their_own_milestones(tmp_path):
    cfg = SC.load(examples_as_real(tmp_path))
    thanksgiving = SC.rhythm_for(cfg, "important", is_birthday=False, template_key="thanksgiving")
    assert [m["days_before"] for m in thanksgiving][0] == 21                       # prep from 3 weeks out
    halloween = SC.rhythm_for(cfg, "important", is_birthday=False, template_key="halloween")
    assert halloween[0]["days_before"] == 21 and "Costume" in halloween[0]["text"]
    pi = SC.rhythm_for(cfg, "trivia", is_birthday=False, template_key="pi_day")
    assert [m["days_before"] for m in pi] == [0] and pi[0]["surfaces"] == ["paper"]
    easter = SC.rhythm_for(cfg, "important", is_birthday=False, template_key="easter")
    assert [m["days_before"] for m in easter] == [7, 0]                            # no milestones → tier rhythm


def test_bad_milestones_are_reported_not_loaded(tmp_path):
    folder = tmp_path / "s"
    (folder / "templates").mkdir(parents=True)
    (folder / "templates" / "x.yaml").write_text("""
- key: a
  name: A
  tier: important
  when: "01-05"
  milestones: [{days_before: -1, surfaces: [paper], text: hi}]
- key: b
  name: B
  tier: important
  when: "01-06"
  milestones: [{days_before: 3, surfaces: [phone], text: hi}]
- key: c
  name: C
  tier: important
  when: "01-07"
- key: c
  name: C again
  tier: trivia
  when: "01-08"
""")
    cfg = SC.load(folder)
    assert [t.key for t in cfg.templates] == ["c"]
    joined = "\n".join(cfg.problems)
    assert "days_before must be" in joined and "surfaces must be" in joined and "used twice" in joined


def test_settings_rhythm_overrides_one_tier_and_bad_ones_fall_back(tmp_path):
    folder = tmp_path / "s"
    folder.mkdir()
    (folder / "secretary.yaml").write_text("""
rhythms:
  important:
    - {days_before: 5, surfaces: [checkin], text: "{name} in {days} days"}
  trivia: "nope"
""")
    cfg = SC.load(folder)
    assert [m["days_before"] for m in SC.rhythm_for(cfg, "important", is_birthday=False)] == [5]
    assert [m["days_before"] for m in SC.rhythm_for(cfg, "trivia", is_birthday=False)] == [0]   # default kept
    assert [m["days_before"] for m in SC.rhythm_for(cfg, "critical", is_birthday=True)] == [21, 10, 3, 0]
    assert any("rhythms.trivia" in p for p in cfg.problems)


def test_text_fills_name_date_and_days():
    out = SC.render_text("{name} in {days} days ({date})", name="Robin's birthday",
                         on=date(2026, 12, 12), today=date(2026, 12, 2))
    assert out == "Robin's birthday in 10 days (Sat Dec 12)"
    when = lambda d: SC.render_text("{name} {when}", name="Robin's birthday", on=date(2026, 12, 12), today=d)
    assert when(date(2026, 11, 24)) == "Robin's birthday in 18 days"
    assert when(date(2026, 12, 11)) == "Robin's birthday tomorrow"
    assert when(date(2026, 12, 12)) == "Robin's birthday today"
    assert SC.render_text("Stray {brace", name="x", on=date(2026, 1, 1), today=date(2026, 1, 1)) == "Stray {brace"
