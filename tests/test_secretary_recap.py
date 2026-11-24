"""
Secretary step 8: check-in RECAPs (checkin/ingest_recap.py and /api/checkin/recap).

Made-up names only; temp ONS_DATA_DIR. The RECAP format is docs/context/checkin-protocol.md.

  uv run --with pytest pytest tests/test_secretary_recap.py -q
"""

from __future__ import annotations

import ast
import json
from datetime import date
from pathlib import Path

import pytest
import yaml
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from checkin import ingest_recap as IR
from secretary import projects as PR

ROOT = Path(__file__).resolve().parents[1]
CF = {"CF-Connecting-IP": "203.0.113.9"}

RECAP = """RECAP 2026-12-04
Wins: Booked the pool tour; three runs this week
Top 3 next week: 1) Pick a swim time slot 2) Finish the quarterly report 3) Call the plumber
Decisions: Swim lessons on weekday evenings, not Saturdays
Parking lot: Garage cleanout; new bike rack
Commitments: Me — email the swim school by Tuesday; Me + partner — budget talk on Sunday
Done: Robin's swim school — Sign-up opens
New project: Passport renewal | deadline 2027-03-01 | tier important | both passports, photos first
New critical person: Alex Sample
"""

PROJECTS = """
- key: swim
  name: Robin's swim school
  tier: critical
  milestones:
    - {key: signup_opens, title: Sign-up opens, due: 2026-12-01}
    - {key: slot, title: Pick a time slot, due: 2026-12-09}
"""


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("ONS_DEV", raising=False)
    f = tmp_path / "data" / "secretary"
    f.mkdir(parents=True)
    (f / "secretary.yaml").write_text("critical_people:\n  - name: Jordan Doe\n    match: [Jordan Doe, Jordy]\n")
    (f / "projects.yaml").write_text(PROJECTS)
    return f


# ── parse ────────────────────────────────────────────────────────────────────

def test_parses_every_key_of_the_owner_format():
    r = IR.parse(RECAP)
    assert r.date == date(2026, 12, 4) and r.problems == []
    assert r.sections["wins"] == ["Booked the pool tour", "three runs this week"]
    assert r.sections["top3"] == ["Pick a swim time slot", "Finish the quarterly report", "Call the plumber"]
    assert r.sections["commitments"] == ["Me — email the swim school by Tuesday", "Me + partner — budget talk on Sunday"]
    assert r.done == [("Robin's swim school", "Sign-up opens")]
    assert r.new_projects == [{"name": "Passport renewal", "deadline": date(2027, 3, 1), "tier": "important",
                               "notes": "both passports, photos first"}]
    assert r.new_people == ["Alex Sample"]


def test_tolerates_bullets_bold_keys_dash_variants_and_code_fences():
    r = IR.parse("```\n**RECAP 2026-12-04**\n- **Done:** Robin's swim school - Sign-up opens\n"
                 "* Done: Robin's swim school -- Pick a time slot\nNew project: Fence | tier Critical\n```")
    assert r.done == [("Robin's swim school", "Sign-up opens"), ("Robin's swim school", "Pick a time slot")]
    assert r.new_projects[0] == {"name": "Fence", "deadline": None, "tier": "critical", "notes": ""}


def test_bad_lines_are_reported_not_fatal():
    r = IR.parse("RECAP 2026-12-04\nDone: no dash here\nNew project: X | deadline soon | tier urgent\nMood: great\nrandom words")
    joined = "\n".join(r.problems)
    for bit in ("Done line needs", "deadline must be YYYY-MM-DD", "tier 'urgent'", "unknown key 'Mood'", "not a RECAP line"):
        assert bit in joined
    assert r.new_projects[0]["tier"] == "important"


def test_not_a_recap_is_refused():
    with pytest.raises(ValueError, match="starts with a line like"):
        IR.parse("Wins: stuff")


# ── plan ─────────────────────────────────────────────────────────────────────

def test_plan_matches_done_lines_and_proposes_new_things(folder):
    p = IR.plan(IR.parse(RECAP), date(2026, 12, 5))
    assert p["done"] == [{"project": "swim", "milestone": "signup_opens", "label": "Robin's swim school — Sign-up opens",
                          "on": "2026-12-04", "already": False, "note": None}]
    [proj] = p["projects"]
    assert proj["status"] == "draft" and proj["key"] == "passport_renewal" and proj["notes"] == "both passports, photos first"
    assert [(m["key"], m["due"]) for m in proj["milestones"]] == [
        ("plan", "2026-12-07"), ("halfway", "2027-01-16"), ("deadline", "2027-03-01")]
    assert proj["milestones"][-1]["deadline"] is True
    assert p["people"] == [{"name": "Alex Sample", "match": ["Alex Sample"], "proposed_on": "2026-12-04"}]
    assert p["problems"] == [] and p["skipped"] == []


def test_close_spellings_match_and_are_reported_unknowns_are_problems(folder):
    p = IR.plan(IR.parse("RECAP 2026-12-04\nDone: Robins swim school — Signup opens\n"
                         "Done: Garage — Donate pile\nDone: Robin's swim school — Buy goggles"), date(2026, 12, 4))
    assert [d["milestone"] for d in p["done"]] == ["signup_opens"]
    assert p["done"][0]["note"] == "read 'Robins swim school' as 'Robin's swim school'; read 'Signup opens' as 'Sign-up opens'"
    assert any("no project named 'Garage'" in x for x in p["problems"])
    assert any("has no milestone 'Buy goggles'" in x and "Pick a time slot" in x for x in p["problems"])


def test_existing_project_and_critical_person_are_skipped(folder):
    p = IR.plan(IR.parse("RECAP 2026-12-04\nNew project: Robin's swim school | deadline 2027-01-19 | tier critical\n"
                         "New critical person: jordy"), date(2026, 12, 4))
    assert p["projects"] == [] and p["people"] == []
    assert p["skipped"] == ["New project 'Robin's swim school': already a project",
                            "New critical person 'jordy': already critical"]


# ── ingest ───────────────────────────────────────────────────────────────────

def test_ingest_applies_once_and_never_activates(folder):
    IR.submit(RECAP)
    [res] = IR.ingest(date(2026, 12, 5))
    assert res["ok"] and res["done"] == ["Robin's swim school — Sign-up opens"]
    assert res["proposed_projects"] == ["Passport renewal"] and res["proposed_people"] == ["Alex Sample"]

    swim = PR.load(folder).projects[0]
    assert swim.milestones[0].done_on == date(2026, 12, 4) and swim.milestones[0].done_by == "recap"
    assert [p.key for p in PR.load(folder).projects] == ["swim"]               # the proposal isn't a project
    proposed = (folder / "projects.proposed.yaml").read_text()
    assert proposed.startswith("# Projects proposed by check-in RECAPs") and "status: draft" in proposed
    people = yaml.safe_load((folder / "secretary.proposed.yaml").read_text())
    assert people["critical_people"][0]["name"] == "Alex Sample"
    assert "Alex Sample" not in (folder / "secretary.yaml").read_text()        # never written into the real settings

    assert IR.ingest(date(2026, 12, 5)) == []                                  # applied once
    IR.submit(RECAP)                                                           # pasted again by mistake
    [again] = IR.ingest(date(2026, 12, 5))
    assert again["proposed_projects"] == [] and again["done"] == ["Robin's swim school — Sign-up opens (already done)"]
    assert any("already proposed" in s for s in again["skipped"])
    assert len(yaml.safe_load(proposed.split("\n", 3)[-1]) or []) == 1


def test_proposals_stay_visible_in_the_sheet_and_the_packet(folder):
    from checkin import build_packet as bp
    from secretary import sheet as S
    IR.submit(RECAP)
    IR.ingest(date(2026, 12, 5))
    prop = S.proposals()
    assert prop == {"projects": ["Passport renewal"], "people": ["Alex Sample"]}
    lines = bp.project_lines(bp.Inputs(today=date(2026, 12, 5), secretary={"projects": [], "proposals": prop}), 6)
    assert lines[-1] == ("_Proposed by RECAPs, waiting for review in data/secretary/*.proposed.yaml: "
                         "projects: Passport renewal; critical people: Alex Sample._")


def test_one_broken_recap_does_not_block_the_next(folder):
    IR.recaps_log().append({"recap_id": "bad", "recap_date": "2026-12-03", "text": "garbage"})
    IR.submit("RECAP 2026-12-04\nDone: Robin's swim school — Pick a time slot")
    res = IR.ingest(date(2026, 12, 5))
    assert [r["ok"] for r in res] == [False, True]


def test_preview_cli_writes_nothing(folder, tmp_path, capsys):
    f = tmp_path / "recap.txt"
    f.write_text(RECAP)
    assert IR.main(["--preview", str(f)]) == 0
    out = capsys.readouterr().out
    assert "done: Robin's swim school — Sign-up opens" in out and "propose project: Passport renewal" in out
    assert not (folder / "projects.proposed.yaml").exists() and not IR.recaps_log().path.exists()


# ── API ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def client(folder, monkeypatch):
    monkeypatch.setenv("ONS_WRITE_TOKEN", "sekrit")
    from api.auth import require_owner
    from api.routers import checkin
    app = FastAPI()
    app.include_router(checkin.router, prefix="/api/checkin", dependencies=[Depends(require_owner)])
    return TestClient(app)


def test_api_previews_queues_and_reports(client, folder):
    assert client.post("/api/checkin/recap", headers=CF, json={"text": RECAP}).status_code == 401
    bad = client.post("/api/checkin/recap", json={"text": "Wins: things went fine"})
    assert bad.status_code == 422 and "RECAP" in bad.json()["detail"]

    r = client.post("/api/checkin/recap", json={"text": RECAP})
    assert r.status_code == 200
    body = r.json()
    assert body["recap_date"] == "2026-12-04"
    assert [d["label"] for d in body["preview"]["done"]] == ["Robin's swim school — Sign-up opens"]
    assert not (folder / "projects.proposed.yaml").exists()                    # preview only; the sync applies

    [waiting] = client.get("/api/checkin/recaps").json()
    assert waiting["result"] is None
    IR.ingest(date(2026, 12, 5))
    [done] = client.get("/api/checkin/recaps").json()
    assert done["result"]["ok"] and done["result"]["proposed_people"] == ["Alex Sample"]
    assert "sections" not in done["result"]


def test_sync_ingests_recaps_before_secretary_config_publishes():
    tree = ast.parse((ROOT / "scripts" / "daily_sync.py").read_text())      # parse, never import (unloads the API)
    names = [kw.value.value for node in ast.walk(tree) if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Step"
             for kw in node.keywords if kw.arg == "name"]
    lines = {kw.value.value: node.lineno for node in ast.walk(tree)
             if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Step"
             for kw in node.keywords if kw.arg == "name"}
    assert "ingest_recap" in names
    assert lines["ingest_recap"] < lines["secretary_config"] < lines["dbt"]
