"""
Secretary step 9: one simulated Friday through the whole pipeline, with made-up people.

Friday 2026-12-11. A critical birthday on Saturday (Robin, from a template; the contacts calendar's
copy is merged in), a "!" event on Sunday, a non-critical birthday that has used up its nag limit,
a dentist visit, a trivia day today, and a school-choice project whose first milestone is overdue,
second was marked done by a check-in RECAP, and whose deadline is in January.

  calendar rows ─┐
  secretary.yaml, templates ─┼─► secretary_config publish ─► dbt build +int_events_tiered
  projects.yaml + RECAP ─────┘        ─► heads-up refresh, Fri Dec 4 … Fri Dec 11 (daily)
                                      ─► day sheet ─► paper · website API · check-in packet

  uv run --with pytest pytest tests/test_secretary_fixture.py -q
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
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

FRIDAY = date(2026, 12, 11)
SETTINGS = "critical_people:\n  - name: Jordan Doe\n    match: [Jordan Doe]\nnag_limit: 2\ncoming_up_days: 14\n"
TEMPLATES = """
- key: robin_birthday
  name: Robin's birthday
  tier: critical
  person: Robin
  when: "12-12"
- key: towel_day
  name: Towel Day
  tier: trivia
  when: "12-11"
"""
PROJECTS = """
- key: school
  name: Robin's school choice
  tier: critical
  status: active
  milestones:
    - {key: round1_opens, title: Round 1 opens, due: 2026-12-01}
    - {key: registration, title: State registration opens, due: 2026-12-08}
    - {key: school_list, title: Finalize the school list, due: 2027-01-03}
    - {key: round1_closes, title: Round 1 closes, due: "2027-01-19 16:00", deadline: true}
"""
RECAP = "RECAP 2026-12-09\nWins: toured two schools\nDone: Robin's school choice — State registration opens\n"


def tz(d: date, h: int, m: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, h, m, tzinfo=SC.TZ)


CALENDAR = [
    # kind, title, date, start (None = all day)
    ("birthdays", "Robin Example", date(2026, 12, 12), None),         # merged into the critical template
    ("birthdays", "Sam Example", date(2026, 12, 15), None),           # other birthday → important
    ("primary", "!Pick up passports", date(2026, 12, 13), (10, 0)),   # "!" → critical, Sunday
    ("primary", "Dentist", date(2026, 12, 16), (15, 30)),             # nice to know
    ("primary", "Groceries", FRIDAY, None),                           # nice to know, today
]


@pytest.fixture(scope="module")
def friday(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("friday")
    mp = pytest.MonkeyPatch()
    mp.setenv("ONS_DATA_DIR", str(tmp / "data"))
    mp.delenv("ONS_DEV", raising=False)
    mp.setenv("ONS_WRITE_TOKEN", "sekrit")
    folder = tmp / "data" / "secretary"
    (folder / "templates").mkdir(parents=True)
    (folder / "secretary.yaml").write_text(SETTINGS)
    (folder / "templates" / "t.yaml").write_text(TEMPLATES)
    (folder / "projects.yaml").write_text(PROJECTS)
    db = tmp / "ons.duckdb"

    from checkin import ingest_recap as IR
    from secretary import headsups as H
    from secretary import projects as PR
    from secretary import sheet as S

    # the calendar sync (all calendars, 7 back / 60 ahead) succeeded this morning
    rows = [{"calendar_id": kind, "calendar_name": kind, "calendar_kind": kind, "event_id": f"e{i}", "title": title,
             "event_type": "birthday" if kind == "birthdays" else "default", "all_day": start is None,
             "start_date": d, "start_at": tz(d, *start) if start else None, "end_at": None, "location": None,
             "status": "confirmed", "synced_at": tz(FRIDAY, 4)} for i, (kind, title, d, start) in enumerate(CALENDAR)]
    CE.write_warehouse(rows, db)
    CE.write_status(True, "ok", tz(FRIDAY, 4))

    # Wednesday's check-in RECAP, pasted on the website, applied by the sync
    IR.submit(RECAP)
    IR.ingest(date(2026, 12, 10))

    SC.publish(SC.load(folder), FRIDAY, db)
    PR.publish(PR.load(folder), FRIDAY, db)
    (tmp / "profiles").mkdir()
    (tmp / "profiles" / "profiles.yml").write_text(
        f"ons:\n  target: dev\n  outputs:\n    dev:\n      type: duckdb\n      path: {db}\n      schema: main\n      threads: 1\n")
    dbt = shutil.which("dbt") or str(ROOT / ".venv" / "bin" / "dbt")
    proc = subprocess.run(
        [dbt, "build", "--select", "+int_events_tiered", "--profiles-dir", str(tmp / "profiles"),
         "--project-dir", str(ROOT / "dbt"), "--target-path", str(tmp / "target"), "--log-path", str(tmp / "logs")],
        capture_output=True, text=True, cwd=ROOT, env={**os.environ, "DBT_SEND_ANONYMOUS_USAGE_STATS": "false"})
    assert proc.returncode == 0, proc.stdout[-3000:]

    # a week of 4am syncs; the packet goes out daily, the paper every day
    cfg = SC.load(folder)
    for n in range(7, -1, -1):
        day = FRIDAY - timedelta(days=n)
        H.refresh(day, cfg=cfg, path=db, surfaces_today={"paper", "paper_lead", "checkin"}, now=tz(day, 4))
    S.build_and_write(FRIDAY, cfg=cfg, path=db)

    con = duckdb.connect(str(db), read_only=True)
    tiered = {r[0]: r[1:] for r in con.execute(
        "SELECT display_title, tier, tier_rule, event_date FROM main_intermediate.int_events_tiered").fetchall()}
    heads = {r[0]: dict(zip(("status", "shown_count", "last_shown_on", "text", "tier"), r[1:])) for r in con.execute(
        "SELECT headsup_id, status, shown_count, last_shown_on, text, tier FROM secretary.headsups").fetchall()}
    con.close()
    yield {"tmp": tmp, "db": db, "sheet": S.load(FRIDAY), "tiered": tiered, "heads": heads}
    mp.undo()


# ── tier rules ───────────────────────────────────────────────────────────────

def test_every_tier_rule_fires_once(friday):
    t = friday["tiered"]
    assert t["Pick up passports"][:2] == ("critical", "bang")                       # 1. "!" (and the "!" is gone)
    assert t["Robin's birthday"][:2] == ("critical", "critical_person_birthday")    # 2. a critical birthday
    assert "Robin Example" not in t                                                 #    its calendar copy is merged
    assert t["Sam Example"][:2] == ("important", "birthday")                        # 3. any other birthday
    assert t["Towel Day"][:2] == ("trivia", "template")                             # 4. template tier
    assert t["Robin's school choice: Round 1 closes (deadline)"][:2] == ("critical", "project")   # 5. project tier
    assert t["Dentist"][:2] == ("nice_to_know", "default")                          # 6. everything else
    assert "Robin's school choice: State registration opens" not in t               # done by the RECAP


# ── nag limit ────────────────────────────────────────────────────────────────

def test_nag_limit_stops_the_important_birthday_but_not_critical_ones_inside_three_days(friday):
    h = friday["heads"]
    sam = h["cal:birthdays:e1@7"]
    assert (sam["status"], sam["shown_count"], sam["last_shown_on"]) == ("open", 2, date(2026, 12, 9))
    assert "tpl:robin_birthday:2026-12-12@21" not in h                              # the week began 8 days out:
    assert h["tpl:robin_birthday:2026-12-12@10"]["status"] == "superseded"          # no replay; 10 → 3 days out
    robin3 = h["tpl:robin_birthday:2026-12-12@3"]
    assert robin3["last_shown_on"] == FRIDAY and robin3["shown_count"] == 3        # Wed, Thu, Fri: critical, daily
    assert not [k for k in h if k.startswith("prj:school:registration")]           # done (RECAP) before the week's syncs


# ── the paper ────────────────────────────────────────────────────────────────

def test_friday_paper(friday):
    import json
    from agents.morning_brief import print_edition as P
    s = friday["sheet"]
    assert s["lead"] == []
    assert [h["text"] for h in s["today"]] == [
        "Robin's birthday tomorrow: card and plans sorted?",
        "Pick up passports in 2 days: all set?",
        "Today is Towel Day.",
    ]
    assert [(e["label"], e["time"], e["title"]) for e in s["weekend"]] == [
        ("Sat Dec 12", None, "Robin's birthday"), ("Sun Dec 13", "10am", "Pick up passports")]
    assert [(e["title"], e["tier"]) for e in s["coming_up"]] == [("Sam Example", "important"), ("Dentist", "nice_to_know")]

    edition = json.loads((ROOT / "tests" / "fixtures" / "morning_brief" / "edition_sample.json").read_text())
    edition["date"] = FRIDAY.isoformat()
    page = P.render_html({"status": "published", "edition": edition, "revisions": 0}).split("</style>")[1]
    strip = page[page.index('<section class="secretary">'):page.index("</section>")]
    assert strip.index(">Today<") < strip.index(">This Weekend<") < strip.index(">Coming Up<")
    assert '<li class="critical">■ Robin&#x27;s birthday tomorrow: card and plans sorted?</li>' in strip   # emphasis
    assert '<li class="trivia">· Today is Towel Day.</li>' in strip
    assert '<li class="critical">■ Sun 10am · Pick up passports</li>' in strip
    assert '<li class="nice_to_know">○ Wed Dec 16 3:30pm · Dentist</li>' in strip
    assert "Calendar unavailable" not in page


def test_saturday_paper_leads_with_the_birthday(friday):
    from secretary import config as SC2
    from secretary import headsups as H
    from secretary import sheet as S
    sat = FRIDAY + timedelta(days=1)
    db = friday["tmp"] / "saturday" / "ons.duckdb"               # a copy: Friday's state stays for the other tests
    db.parent.mkdir()                                            # (same file name: dbt's views name the catalog "ons")
    shutil.copy(friday["db"], db)
    H.refresh(sat, cfg=SC2.load(), path=db, surfaces_today={"paper", "paper_lead"}, now=tz(sat, 4))
    con = duckdb.connect(str(db), read_only=True)
    s = S.build(con, SC2.load(), sat)
    con.close()
    assert [h["text"] for h in s["lead"]] == ["Today: Robin's birthday."] and s["weekend"] == []


# ── the website ──────────────────────────────────────────────────────────────

def test_secretary_page_api(friday, monkeypatch):
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient
    from api.auth import require_owner
    from api.routers import secretary
    monkeypatch.setattr(secretary, "today_local", lambda: FRIDAY)
    app = FastAPI()
    app.state.db = duckdb.connect(str(friday["db"]), read_only=True)
    app.include_router(secretary.router, prefix="/api/secretary", dependencies=[Depends(require_owner)])
    http = TestClient(app)
    try:
        assert http.get("/api/secretary/overview", headers={"CF-Connecting-IP": "203.0.113.9"}).status_code == 401
        o = http.get("/api/secretary/overview").json()
        rows = {h["headsup_id"]: h for h in o["headsups"]}
        assert [h["tier"] for h in o["headsups"]] == ["critical", "critical", "important", "trivia"]
        assert rows["cal:birthdays:e1@7"]["shown_today"] is False and rows["cal:birthdays:e1@7"]["shown_count"] == 2
        assert rows["tpl:robin_birthday:2026-12-12@3"]["shown_today"] is True
        assert o["calendar"]["ok"] is True
        upcoming = [(u["title"], u["tier"]) for u in o["upcoming"]]
        assert ("Robin's school choice: Finalize the school list", "critical") in upcoming
        assert ("Groceries", "nice_to_know") in upcoming and ("Towel Day", "trivia") not in upcoming
        [proj] = o["projects"]                                                      # the Life projects card
        assert [m["title"] for m in proj["overdue"]] == ["Round 1 opens"] and proj["next"]["title"] == "Finalize the school list"
        assert [m["title"] for m in proj["done"]] == ["State registration opens"]
        r = http.post("/api/secretary/headsups/action", json={"headsup_id": "cal:birthdays:e1@7", "action": "done"})
        assert r.status_code == 200
        sam = next(h for h in http.get("/api/secretary/overview").json()["headsups"] if h["headsup_id"] == "cal:birthdays:e1@7")
        assert sam["status"] == "done" and sam["queued"] is True
    finally:
        app.state.db.close()


# ── the check-in packet ──────────────────────────────────────────────────────

def test_friday_packet(friday, monkeypatch):
    from checkin import build_packet as bp
    from checkin import post_slack as ps
    monkeypatch.setattr(bp, "load_warehouse", lambda inp, db_path=None: None)
    monkeypatch.setattr(bp, "load_git", lambda inp: None)
    monkeypatch.setattr(bp, "PRIORITIES", friday["tmp"] / "missing.md")
    text = bp.build_packet(bp.gather(FRIDAY))
    sec = lambda name: text.split(f"## {name}\n")[1].split("\n## ")[0].splitlines()
    assert len(text) <= bp.MAX_CHARS

    ask = sec("Ask first")
    assert ask[0] == ("- Has *Round 1 opens* for *Robin's school choice* happened? (due Tue Dec 1, 10 days ago) "
                      "If yes, RECAP: `Done: Robin's school choice — Round 1 opens`")
    assert ask[1].startswith("- Look ahead:") and len([l for l in ask if l.startswith("- Has")]) == 1

    assert sec("Coming up") == [
        "Heads-ups for today:",
        "- Robin's birthday tomorrow: card and plans sorted?",
        "- Pick up passports in 2 days: all set?",
        "Next 30 days, critical and important:",
        "- **Sun Jan 3 · Robin's school choice: Finalize the school list** (critical, in 23 days)",
        "- Tue Dec 15 · Sam Example (in 4 days)",
    ]
    assert sec("Life projects") == [
        "**Robin's school choice** (critical) · 1 of 4 milestones done",
        "- Overdue: Round 1 opens (Tue Dec 1, 10 days ago)",
        "- Done: State registration opens (12/09)",
        "- Next: Finalize the school list (Sun Jan 3, in 23 days)",
    ]
    slack = ps.to_mrkdwn(text, FRIDAY)
    assert "• *Sun Jan 3 · Robin's school choice: Finalize the school list* (critical, in 23 days)" in slack
