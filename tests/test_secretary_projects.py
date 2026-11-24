"""
Secretary step 6: life projects (secretary/projects.py) → secretary.project_milestones → dbt's
int_events_tiered → heads-ups, the day sheet and the packet's "Life projects". Made-up names only;
temp ONS_DATA_DIR and DuckDB; dbt runs for real against the temp DB.

  uv run --with pytest pytest tests/test_secretary_projects.py -q
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import date, datetime, time
from pathlib import Path

import duckdb
import pytest

from checkin import build_packet as bp
from secretary import config as SC
from secretary import headsups as H
from secretary import projects as PR
from secretary import sheet as S

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 12, 4)

PROJECTS = """
- key: swim
  name: Robin's swim school
  tier: critical
  status: active
  notes: Lessons for the spring term.
  milestones:
    - key: signup_opens
      title: Sign-up opens
      due: 2026-12-01
    - title: Pick a time slot
      due: 2026-12-09
    - key: tour
      title: Pool tour
      due: 2026-11-20
      done: 2026-11-20
    - key: forms_due
      title: Forms due
      due: "2027-01-12 16:00"
      deadline: true
- key: garage
  name: Garage cleanout
  tier: important
  status: draft
  milestones:
    - {title: Donate pile, due: 2026-12-06}
"""


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path / "data"))
    f = tmp_path / "data" / "secretary"
    (f / "templates").mkdir(parents=True)
    (f / "secretary.yaml").write_text("nag_limit: 2\n")
    (f / "projects.yaml").write_text(PROJECTS)
    return f


# ── loading ──────────────────────────────────────────────────────────────────

def test_load_reads_dates_times_deadlines_and_done(folder):
    ps = PR.load(folder)
    assert ps.problems == [] and [p.key for p in ps.projects] == ["swim", "garage"]
    swim = ps.projects[0]
    assert [m.key for m in swim.milestones] == ["tour", "signup_opens", "pick_a_time_slot", "forms_due"]   # by date
    forms = swim.milestones[-1]
    assert forms.due == date(2027, 1, 12) and forms.due_time == time(16, 0) and forms.deadline
    assert forms.due_at == datetime(2027, 1, 12, 16, 0, tzinfo=SC.TZ)
    assert swim.milestones[0].done_on == date(2026, 11, 20) and swim.milestones[0].done_by == "yaml"


def test_bad_entries_are_reported_and_placeholders_listed(tmp_path):
    f = tmp_path / "s"
    f.mkdir()
    (f / "projects.yaml").write_text("""
- {key: a, name: A, tier: urgent, milestones: []}
- {key: b, name: B, status: someday, milestones: []}
- {key: c, name: C, milestones: [{title: X, due: next tuesday}]}
- {key: d, name: D, milestones: [{key: x, title: X, due: 2027-01-01}, {key: x, title: Y, due: 2027-01-02}]}
- {key: e, name: <CHILD'S NAME>'s thing, milestones: [{title: X, due: <YYYY-MM-DD>}]}
- {key: f, name: F, milestones: [{title: X, due: 2027-01-01}]}
- {key: f, name: F again, milestones: []}
""")
    ps = PR.load(f)
    assert [p.key for p in ps.projects] == ["f"]
    joined = "\n".join(ps.problems)
    for bit in ("tier must be", "status must be", "due must be", "milestone key 'x' is used twice", "used twice; skipped"):
        assert bit in joined
    assert ps.placeholders == ["projects.yaml: <CHILD'S NAME>'s thing (has <PLACEHOLDERS>)"]


def test_example_file_is_all_placeholders():
    f = ROOT / "secretary" / "config"
    text = (f / "projects.example.yaml").read_text()
    assert text.count("due: <YYYY-MM-DD") == 4 and "<CHILD'S NAME>" in text


def test_completion_log_wins_over_yaml_and_reopen_undoes(folder):
    PR.record_completion("swim", "signup_opens", by="recap", on=date(2026, 12, 2))
    PR.record_completion("swim", "tour", done=False, by="cli")
    swim = PR.load(folder).projects[0]
    ms = {m.key: m for m in swim.milestones}
    assert ms["signup_opens"].done_on == date(2026, 12, 2) and ms["signup_opens"].done_by == "recap"
    assert ms["tour"].done_on is None                              # the log's reopen beats the yaml's done


def test_cli_done_checks_the_milestone_exists(folder, capsys):
    assert PR.main(["--done", "swim", "nope"]) == 1
    assert "swim/signup_opens" in capsys.readouterr().err
    assert PR.main(["--done", "swim", "signup_opens", "--date", "2026-12-03"]) == 0
    assert PR.load(folder).projects[0].milestones[1].done_on == date(2026, 12, 3)


# ── through dbt, the engine, the sheet and the packet ────────────────────────

@pytest.fixture
def built(folder, tmp_path):
    db = tmp_path / "ons.duckdb"

    def build(day=TODAY):
        SC.publish(SC.load(folder), day, db)
        PR.publish(PR.load(folder), day, db)
        (tmp_path / "profiles").mkdir(exist_ok=True)
        (tmp_path / "profiles" / "profiles.yml").write_text(
            f"ons:\n  target: dev\n  outputs:\n    dev:\n      type: duckdb\n      path: {db}\n      schema: main\n      threads: 1\n")
        dbt = shutil.which("dbt") or str(ROOT / ".venv" / "bin" / "dbt")
        proc = subprocess.run(
            [dbt, "build", "--select", "+int_events_tiered", "--profiles-dir", str(tmp_path / "profiles"),
             "--project-dir", str(ROOT / "dbt"), "--target-path", str(tmp_path / "target"), "--log-path", str(tmp_path / "logs")],
            capture_output=True, text=True, cwd=ROOT, env={**os.environ, "DBT_SEND_ANONYMOUS_USAGE_STATS": "false"})
        assert proc.returncode == 0, proc.stdout[-3000:]
        H.refresh(day, cfg=SC.load(folder), path=db, surfaces_today={"paper", "paper_lead", "checkin"},
                  now=datetime(day.year, day.month, day.day, 4, tzinfo=SC.TZ))
        con = duckdb.connect(str(db), read_only=True)
        sheet = S.build(con, SC.load(folder), day)
        events = con.execute("SELECT display_title, event_date, tier, tier_rule, start_at, all_day "
                             "FROM main_intermediate.int_events_tiered WHERE source = 'project' ORDER BY event_date").fetchall()
        heads = {r[0]: r[1:] for r in con.execute(
            "SELECT headsup_id, status, closed_by, text FROM secretary.headsups").fetchall()}
        con.close()
        return {"sheet": sheet, "events": events, "heads": heads}
    return build


def test_open_milestones_of_active_projects_become_events_with_the_project_tier(built):
    out = built()
    assert [(e[0], e[1], e[2], e[3]) for e in out["events"]] == [
        ("Robin's swim school: Sign-up opens", date(2026, 12, 1), "critical", "project"),
        ("Robin's swim school: Pick a time slot", date(2026, 12, 9), "critical", "project"),
        ("Robin's swim school: Forms due (deadline)", date(2027, 1, 12), "critical", "project"),
    ]                                                   # not the done tour, not the draft garage project
    forms = out["events"][-1]
    assert forms[5] is False and forms[4] == datetime(2027, 1, 12, 16, 0, tzinfo=SC.TZ)


def test_milestones_get_the_critical_rhythm_and_done_closes_their_headsups(built):
    out = built()
    h = out["heads"]["prj:swim:pick_a_time_slot@10"]
    assert h[0] == "open" and h[2] == "Robin's swim school: Pick a time slot in 5 days (Wed Dec 9)."
    PR.record_completion("swim", "pick_a_time_slot", by="recap", on=TODAY)
    out = built(date(2026, 12, 5))
    assert out["heads"]["prj:swim:pick_a_time_slot@10"][:2] == ("done", "project")


def test_sheet_and_packet_list_overdue_due_done_and_next(built):
    PR.record_completion("swim", "tour", by="recap", on=date(2026, 12, 1))    # done within the week
    sheet = built()["sheet"]
    [p] = sheet["projects"]
    assert (p["name"], p["open_count"], p["done_count"]) == ("Robin's swim school", 3, 1)
    assert [m["title"] for m in p["overdue"]] == ["Sign-up opens"]
    assert [m["title"] for m in p["due"]] == ["Pick a time slot"]
    assert p["next"]["label"] == "Tue Jan 12 4pm" and p["next"]["deadline"] is True
    assert sheet["draft_projects"] == 1

    lines = bp.project_lines(bp.Inputs(today=TODAY, secretary=sheet), limit=6)
    assert lines == [
        "**Robin's swim school** (critical) · 1 of 4 milestones done",
        "- Overdue: Sign-up opens (Tue Dec 1, 3 days ago)",
        "- Due: Pick a time slot (Wed Dec 9, in 5 days)",
        "- Done: Pool tour (12/01)",
        "- Next: Forms due, deadline (Tue Jan 12 4pm, in 39 days)",
        "_1 draft project waiting in projects.yaml (set status: active to start follow-ups)._",
    ]
    text = bp.render(bp.Inputs(today=TODAY, secretary=sheet, calendar={"ok": True}), limit=6)
    assert text.index("## Coming up") < text.index("## Life projects") < text.index("## Last 7 days")


def test_no_projects_file_is_fine(tmp_path, monkeypatch):
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path))
    assert PR.load(tmp_path).projects == []
    assert bp.project_lines(bp.Inputs(today=TODAY, secretary={"projects": [], "draft_projects": 0}), 6) == ["No active projects."]
