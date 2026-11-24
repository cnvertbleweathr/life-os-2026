"""
Secretary step 4: the heads-up engine (secretary/headsups.py → secretary.headsups).

A temp DuckDB stands in for the warehouse: main_intermediate.int_events_tiered is
written directly (tests/test_secretary_tiers.py covers how dbt builds it). Made-up
names only; ONS_DATA_DIR points at tmp so the action log never touches data/.

  uv run --with pytest pytest tests/test_secretary_headsups.py -q
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from secretary import config as SC  # noqa: E402
from secretary import headsups as H  # noqa: E402

ALL = {"paper", "paper_lead", "checkin"}

TEMPLATES = """
- key: robin_birthday
  name: Robin's birthday
  tier: critical
  person: Robin
  when: "12-12"
- key: towel_day
  name: Towel Day
  tier: trivia
  when: "05-25"
- key: feast
  name: Feast
  tier: important
  when: "12-03"
  milestones:
    - {days_before: 21, surfaces: [checkin], text: "{name} in 3 weeks"}
    - {days_before: 14, surfaces: [paper], text: "{name} in {days} days"}
    - {days_before: 0, surfaces: [paper], text: "{name} today"}
"""

# (event_key, source, title, tier, date, is_birthday, template_key)
ROBIN = ("tpl:robin_birthday:2026-12-12", "template", "Robin's birthday", "critical", date(2026, 12, 12), True, "robin_birthday")
SAM = ("cal:b:sam", "calendar", "Sam Example", "important", date(2026, 12, 5), True, None)
DENTIST = ("cal:p:dentist", "calendar", "Dentist", "nice_to_know", date(2026, 12, 2), False, None)
TOUR = ("cal:p:tour", "calendar", "Preschool tour", "critical", date(2026, 12, 4), False, None)
FEAST = ("tpl:feast:2026-12-03", "template", "Feast", "important", date(2026, 12, 3), False, "feast")
TOWEL = ("tpl:towel_day:2027-05-25", "template", "Towel Day", "trivia", date(2027, 5, 25), False, "towel_day")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path / "data"))
    folder = tmp_path / "secretary"
    (folder / "templates").mkdir(parents=True)
    (folder / "secretary.yaml").write_text("nag_limit: 2\n")
    (folder / "templates" / "t.yaml").write_text(TEMPLATES)
    cfg = SC.load(folder)
    assert cfg.problems == [] or all("secretary.example" in p for p in cfg.problems)
    db = tmp_path / "ons.duckdb"

    def events(*rows):
        con = duckdb.connect(str(db))
        con.execute("CREATE SCHEMA IF NOT EXISTS main_intermediate")
        con.execute("""CREATE OR REPLACE TABLE main_intermediate.int_events_tiered (
                         event_key VARCHAR, source VARCHAR, display_title VARCHAR, tier VARCHAR,
                         event_date DATE, is_birthday BOOLEAN, template_key VARCHAR,
                         start_at TIMESTAMPTZ, all_day BOOLEAN DEFAULT true)""")
        if rows:
            rows = [r if len(r) == 9 else (*r, None, True) for r in rows]
            con.executemany("INSERT INTO main_intermediate.int_events_tiered VALUES (?,?,?,?,?,?,?,?,?)", rows)
        con.close()

    def run(day, surfaces=ALL):
        return H.refresh(day, cfg=cfg, path=db, surfaces_today=set(surfaces),
                         now=datetime(day.year, day.month, day.day, 4, tzinfo=SC.TZ))

    def rows(where="true"):
        con = duckdb.connect(str(db), read_only=True)
        out = H._select(con, where, [])
        con.close()
        return {h["headsup_id"]: h for h in out}

    def picked(day, surface=None):
        con = duckdb.connect(str(db), read_only=True)
        out = [h["headsup_id"] for h in H.shown_today(con, day, surface)]
        con.close()
        return out

    return type("Env", (), {"events": staticmethod(events), "run": staticmethod(run),
                            "rows": staticmethod(rows), "picked": staticmethod(picked), "cfg": cfg, "db": db})


def days(start: date, n: int):
    return [start + timedelta(days=i) for i in range(n)]


# ── rhythm and idempotency ────────────────────────────────────────────────────

def test_critical_birthday_walks_its_rhythm_and_reruns_change_nothing(env):
    env.events(ROBIN)
    env.run(date(2026, 11, 20))
    assert env.rows() == {}                                            # 22 days out: nothing yet
    first = env.run(date(2026, 11, 21))
    assert first["added"] == 1 and first["shown"] == 1
    again = env.run(date(2026, 11, 21))                                # rerun / --force reprint
    assert again["added"] == again["shown"] == 0 and again["showing_today"] == 1
    h = env.rows()[f"{ROBIN[0]}@21"]
    assert h["shown_count"] == 1 and h["surfaces"] == ["checkin"]
    assert h["text"] == "Robin's birthday is in 21 days (Sat Dec 12). Gift ideas?"

    for d in days(date(2026, 11, 22), 10):                             # critical: daily, no nag limit
        env.run(d)
    h = env.rows()[f"{ROBIN[0]}@21"]
    assert h["shown_count"] == 11
    assert h["text"] == "Robin's birthday is in 11 days (Sat Dec 12). Gift ideas?"     # stays true daily

    out = env.run(date(2026, 12, 2))                                   # 10 days: next milestone
    assert out["superseded"] == 1
    r = env.rows()
    assert r[f"{ROBIN[0]}@21"]["status"] == "superseded"
    assert r[f"{ROBIN[0]}@10"]["status"] == "open" and r[f"{ROBIN[0]}@10"]["surfaces"] == ["paper"]
    for d in days(date(2026, 12, 3), 10):
        env.run(d)
    r = env.rows()
    assert [r[f"{ROBIN[0]}@{n}"]["status"] for n in (21, 10, 3, 0)] == ["superseded"] * 3 + ["open"]
    assert env.picked(date(2026, 12, 12), "paper_lead") == [f"{ROBIN[0]}@0"]
    env.run(date(2026, 12, 13))
    assert env.rows()[f"{ROBIN[0]}@0"]["status"] == "expired"


def test_first_run_does_not_replay_missed_milestones(env):
    env.events(FEAST)                                                  # Dec 3: milestones 21 / 14 / 0
    env.run(date(2026, 11, 25))                                        # 8 days out: 21 and 14 both past
    assert set(env.rows()) == {f"{FEAST[0]}@14"}
    assert env.rows()[f"{FEAST[0]}@14"]["text"] == "Feast in 8 days"


def test_text_stays_current_while_open(env):
    env.events(FEAST)
    env.run(date(2026, 11, 19))
    env.run(date(2026, 11, 20))
    assert env.rows()[f"{FEAST[0]}@14"]["text"] == "Feast in 13 days"


# ── nag limit ─────────────────────────────────────────────────────────────────

def test_nag_limit_stops_non_critical_after_two_days(env):
    env.events(SAM)                                                    # important birthday: 7 days, day of
    for d in days(date(2026, 11, 28), 4):
        env.run(d)
    h = env.rows()[f"{SAM[0]}@7"]
    assert h["shown_count"] == 2 and h["last_shown_on"] == date(2026, 11, 29)
    assert env.picked(date(2026, 12, 1)) == []
    assert f"{SAM[0]}@7" in env.rows("status = 'open'")               # still listed on the website
    env.run(date(2026, 12, 5))                                         # the day itself is a new heads-up
    assert env.picked(date(2026, 12, 5)) == [f"{SAM[0]}@0"]


def test_critical_ignores_the_nag_limit(env):
    env.events(TOUR)                                                   # "!" event: critical rhythm
    for d in days(date(2026, 12, 1), 3):
        env.run(d)
    assert env.rows()[f"{TOUR[0]}@3"]["shown_count"] == 3


def test_a_day_its_surface_does_not_go_out_does_not_count(env):
    env.events(ROBIN)
    env.run(date(2026, 11, 21), surfaces={"paper", "paper_lead"})     # no packet today; @21 is checkin-only
    h = env.rows()[f"{ROBIN[0]}@21"]
    assert h["shown_count"] == 0 and env.picked(date(2026, 11, 21)) == []
    env.run(date(2026, 11, 22))
    assert env.picked(date(2026, 11, 22), "checkin") == [f"{ROBIN[0]}@21"]


def test_nice_to_know_gets_no_headsups_and_trivia_only_the_day(env):
    env.events(DENTIST, TOWEL)
    for d in days(date(2026, 11, 20), 13):
        env.run(d)
    assert env.rows() == {}
    env.run(date(2027, 5, 24))
    assert env.rows() == {}
    env.run(date(2027, 5, 25))
    assert env.picked(date(2027, 5, 25), "paper") == [f"{TOWEL[0]}@0"]
    assert env.rows()[f"{TOWEL[0]}@0"]["text"] == "Today is Towel Day."


# ── done / dismiss / gone ─────────────────────────────────────────────────────

def test_done_and_dismiss_come_from_the_action_log(env):
    env.events(ROBIN, TOUR)
    env.run(date(2026, 12, 2))
    H.record_action(f"{ROBIN[0]}@10", "done", by="website")
    H.record_action(f"{TOUR[0]}@3", "dismiss", by="website")
    out = env.run(date(2026, 12, 3))
    assert out["actions"] == 2
    r = env.rows()
    assert r[f"{ROBIN[0]}@10"]["status"] == "done" and r[f"{TOUR[0]}@3"]["status"] == "dismissed"
    assert f"{ROBIN[0]}@10" not in env.picked(date(2026, 12, 3))
    assert env.run(date(2026, 12, 3))["actions"] == 0                 # applying again is a no-op

    H.record_action(f"{ROBIN[0]}@10", "reopen", by="cli")
    env.run(date(2026, 12, 4))
    assert env.rows()[f"{ROBIN[0]}@10"]["status"] == "open"

    env.run(date(2026, 12, 5))                                         # tour day passes: dismissed stays
    out = env.run(date(2026, 12, 9))                                   # Robin @3 supersedes @10
    assert out["actions"] == 0                                         # old clicks don't undo the sync
    assert env.rows()[f"{ROBIN[0]}@10"]["status"] == "superseded"


def test_done_milestone_does_not_hide_the_next_one(env):
    env.events(ROBIN)
    env.run(date(2026, 12, 2))
    H.record_action(f"{ROBIN[0]}@10", "done", by="website")
    env.run(date(2026, 12, 9))
    r = env.rows()
    assert r[f"{ROBIN[0]}@10"]["status"] == "done" and r[f"{ROBIN[0]}@3"]["status"] == "open"


def test_event_removed_from_calendar_is_marked_gone(env):
    env.events(TOUR)
    env.run(date(2026, 12, 1))
    env.events()                                                       # the tour was deleted
    out = env.run(date(2026, 12, 2))
    assert out["gone"] == 1 and env.rows()[f"{TOUR[0]}@3"]["status"] == "gone"


def test_bad_action_is_refused():
    with pytest.raises(ValueError):
        H.record_action("x", "snooze")


# ── the paper (day sheet → print_edition) ─────────────────────────────────────

FRIDAY = date(2026, 12, 11)
DENTIST_MON = ("cal:p:dentist2", "calendar", "Dentist", "nice_to_know", date(2026, 12, 14), False, None,
               datetime(2026, 12, 14, 15, 30, tzinfo=SC.TZ), False)
TOUR_WED = ("cal:p:tour2", "calendar", "Preschool tour", "critical", date(2026, 12, 16), False, None)
SAM_LATER = ("cal:b:sam2", "calendar", "Sam Example", "important", date(2026, 12, 20), True, None)
BRUNCH_SUN = ("cal:p:brunch", "calendar", "Brunch", "nice_to_know", date(2026, 12, 13), False, None)


def paper(env, day):
    import json
    from secretary import sheet as S
    from agents.morning_brief import print_edition as P
    con = duckdb.connect(str(env.db), read_only=True)
    s = S.build(con, env.cfg, day)
    con.close()
    S.write(s)
    edition = json.loads((ROOT / "tests" / "fixtures" / "morning_brief" / "edition_sample.json").read_text())
    edition["date"] = day.isoformat()
    return s, P.render_html({"status": "published", "edition": edition, "revisions": 0})


def test_friday_paper_has_today_this_weekend_and_coming_up(env):
    env.events(ROBIN, DENTIST_MON, TOUR_WED, SAM_LATER, BRUNCH_SUN)
    env.run(FRIDAY)
    s, page = paper(env, FRIDAY)
    assert [h["text"] for h in s["today"]] == ["Robin's birthday tomorrow: card and plans sorted?",
                                               "Preschool tour in 5 days (Wed Dec 16)."]
    assert [e["title"] for e in s["weekend"]] == ["Robin's birthday"]          # Sat; Sunday brunch isn't important
    assert [(e["title"], e["tier"]) for e in s["coming_up"]] == [             # by tier, then date; minus Today's
        ("Sam Example", "important"), ("Brunch", "nice_to_know"), ("Dentist", "nice_to_know")]
    assert s["coming_up"][2]["time"] == "3:30pm"
    assert [e["title"] for e in s["checkin_coming_up"]] == ["Robin's birthday", "Preschool tour", "Sam Example"]

    strip = page[page.index('<section class="secretary">'):page.index("</section>")]
    assert strip.index(">Today<") < strip.index(">This Weekend<") < strip.index(">Coming Up<")
    assert '<li class="critical">■ Robin&#x27;s birthday tomorrow: card and plans sorted?</li>' in strip
    assert '<li class="critical">■ Sat · Robin&#x27;s birthday</li>' in strip
    assert '<li class="nice_to_know">○ Mon Dec 14 3:30pm · Dentist</li>' in strip
    assert page.index('class="lead"') < page.index('class="secretary"') < page.index('class="columns"')
    assert "sec-lead" not in page.split("<style>")[1].split("</style>")[1]   # no day-of lead yet


def test_day_of_critical_is_the_lead_bar_and_weekdays_have_no_weekend_box(env):
    env.events(ROBIN, TOUR_WED)
    env.run(date(2026, 12, 12))
    s, page = paper(env, date(2026, 12, 12))
    assert [h["text"] for h in s["lead"]] == ["Today: Robin's birthday."]
    assert [h["text"] for h in s["today"]] == ["Preschool tour in 4 days (Wed Dec 16)."]
    body = page.split("</style>")[1]
    assert '<div class="sec-lead">■ Today: Robin&#x27;s birthday.</div>' in body
    assert body.index("sec-lead") < body.index('class="lead"')
    assert s["weekend"] == [] and "This Weekend" not in body                    # Saturday, not Friday


def test_coming_up_is_capped_on_paper(env):
    many = [(f"cal:p:{i}", "calendar", f"Thing {i}", "nice_to_know", date(2026, 12, 1) + timedelta(days=i % 13 + 1),
             False, None) for i in range(11)]
    env.events(*many)
    env.run(date(2026, 12, 1))
    s, page = paper(env, date(2026, 12, 1))
    assert len(s["coming_up"]) == 11
    assert page.count('<li class="nice_to_know">') == 8 and "+3 more on the website" in page


def test_paper_without_a_sheet_is_unchanged(env):
    from agents.morning_brief import print_edition as P
    import json
    edition = json.loads((ROOT / "tests" / "fixtures" / "morning_brief" / "edition_sample.json").read_text())
    page = P.render_html({"status": "published", "edition": edition, "revisions": 0})
    assert 'class="secretary"' not in page and 'class="sec-lead"' not in page


# ── wiring ────────────────────────────────────────────────────────────────────

def test_sync_runs_headsups_after_dbt_and_before_the_paper_and_packet():
    # Parse, never import: importing daily_sync.py unloads the production API.
    import ast
    tree = ast.parse((ROOT / "scripts" / "daily_sync.py").read_text())
    steps = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Step":
            kw = {k.arg: k.value for k in node.keywords}
            steps.append((node.lineno, kw["name"].value, "run_on_days" in kw))
    order = [name for _, name, _ in sorted(steps)]
    pos = [order.index(n) for n in ("dbt", "secretary_headsups", "morning_brief", "checkin_packet")]
    assert pos == sorted(pos)
    assert not dict((n, d) for _, n, d in steps)["secretary_headsups"]       # daily
