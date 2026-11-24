"""
Secretary step 5c: the check-in packet's "Coming up" section (checkin/build_packet.py coming_up_lines),
read from the secretary's day sheet. Made-up names; temp ONS_DATA_DIR and DuckDB.

  uv run --with pytest pytest tests/test_secretary_packet.py -q
"""

from __future__ import annotations

from datetime import date, datetime

import duckdb

from checkin import build_packet as bp
from checkin import post_slack as ps
from secretary import config as SC
from secretary import headsups as H
from secretary import sheet as S

TODAY = date(2026, 11, 29)       # a Sunday; Robin's birthday (critical) is 13 days out

SHEET = {
    "date": "2026-11-29",
    "checkin_today": [{"id": "tpl:robin_birthday:2026-12-12@21", "text": "Robin's birthday is in 13 days (Sat Dec 12). Gift ideas?",
                       "title": "Robin's birthday", "tier": "critical", "date": "2026-12-12", "label": "Sat Dec 12",
                       "rel": "in 13 days", "shown_count": 3}],
    "checkin_coming_up": [
        {"title": "Robin's birthday", "tier": "critical", "date": "2026-12-12", "label": "Sat Dec 12", "time": None, "rel": "in 13 days"},
        {"title": "Preschool tour", "tier": "critical", "date": "2026-12-16", "label": "Wed Dec 16", "time": "9:30am", "rel": "in 17 days"},
        {"title": "Sam Example", "tier": "important", "date": "2026-12-05", "label": "Sat Dec 5", "time": None, "rel": "in 6 days"},
    ],
}


def inputs(**over) -> bp.Inputs:
    base = dict(today=TODAY, secretary=SHEET, calendar={"ok": True})
    base.update(over)
    return bp.Inputs(**base)


def section(text: str) -> str:
    return text.split("## Coming up\n")[1].split("\n## ")[0]


def test_coming_up_asks_todays_questions_then_lists_dates_critical_first():
    lines = bp.coming_up_lines(inputs(), limit=6)
    assert lines == [
        "Heads-ups for today:",
        "- Robin's birthday is in 13 days (Sat Dec 12). Gift ideas?",
        "Next 30 days, critical and important:",
        "- **Wed Dec 16 9:30am · Preschool tour** (critical, in 17 days)",   # Robin's is already asked above
        "- Sat Dec 5 · Sam Example (in 6 days)",
    ]


def test_section_sits_after_priorities_and_reads_in_slack():
    text = bp.render(inputs(), limit=6)
    assert text.index("## My priorities") < text.index("## Coming up") < text.index("## Last 7 days")
    slack = ps.to_mrkdwn(text, TODAY)
    assert "*Coming up*" in slack
    assert "• *Wed Dec 16 9:30am · Preschool tour* (critical, in 17 days)" in slack


def test_missing_sheet_and_calendar_outage_are_said_not_hidden():
    lines = bp.coming_up_lines(inputs(secretary=None, calendar={"ok": False, "message": "Google sign-in expired"}), 6)
    assert lines == [
        "_Calendar unavailable today: Google sign-in expired. Template dates still count; calendar events may be missing._",
        "_No secretary sheet for today: the sync's secretary_headsups step didn't run._",
    ]


def test_quiet_month():
    assert bp.coming_up_lines(inputs(secretary={"date": "2026-11-29"}), 6) == \
        ["Nothing critical or important in the next 30 days."]


def test_cap_trims_important_dates_before_critical():
    many = SHEET | {"checkin_coming_up": [
        {"title": f"Crit {i}", "tier": "critical", "date": f"2026-12-{10 + i}", "label": f"Dec {10 + i}", "time": None, "rel": "soon"}
        for i in range(2)] + [
        {"title": f"Imp {i}", "tier": "important", "date": f"2026-12-0{1 + i}", "label": f"Dec {1 + i}", "time": None, "rel": "soon"}
        for i in range(5)]}
    lines = bp.coming_up_lines(inputs(secretary=many), limit=3)
    dates = lines[lines.index("Next 30 days, critical and important:") + 1:]
    assert [l for l in dates if "Crit" in l] and dates[-1] == "+4 more"
    assert sum("Imp" in l for l in dates) == 1


# ── step 7: Ask first ─────────────────────────────────────────────────────────

PROJECT = {"key": "swim", "name": "Robin's swim school", "tier": "critical", "notes": "", "open_count": 4, "done_count": 0,
           "overdue": [{"key": "signup", "title": "Sign-up opens", "deadline": False, "date": "2026-11-26",
                        "label": "Thu Nov 26", "rel": "3 days ago"}],
           "due": [{"key": "slot", "title": "Pick a time slot", "deadline": False, "date": "2026-11-29",
                    "label": "Sun Nov 29", "rel": "today"},
                   {"key": "forms", "title": "Forms due", "deadline": True, "date": "2026-12-02",
                    "label": "Wed Dec 2 4pm", "rel": "in 3 days"}],
           "done": [], "next": None}


def test_ask_first_has_it_happened_for_due_and_overdue_then_look_ahead():
    lines = bp.ask_lines(inputs(secretary=SHEET | {"projects": [PROJECT]}))
    assert lines[:2] == [
        "- Has *Sign-up opens* for *Robin's swim school* happened? (due Thu Nov 26, 3 days ago) "
        "If yes, RECAP: `Done: Robin's swim school — Sign-up opens`",
        "- Has *Pick a time slot* for *Robin's swim school* happened? (due today) "
        "If yes, RECAP: `Done: Robin's swim school — Pick a time slot`",
    ]                                                                 # Forms due is 3 days out: not asked yet
    assert lines[2].startswith("- Look ahead: what's coming up in the next few weeks")
    assert "`New project:`" in lines[2] and "`New critical person:`" in lines[2]
    assert "Paste RECAP" in lines[3] and len(lines) == 4


def test_overdue_by_one_day_reads_yesterday():
    assert S._rel(date(2026, 11, 28), TODAY) == "yesterday" and S._rel(date(2026, 11, 26), TODAY) == "3 days ago"


def test_look_ahead_is_asked_even_with_no_projects_or_sheet():
    for sheet in (None, SHEET):
        lines = bp.ask_lines(inputs(secretary=sheet))
        assert len(lines) == 2 and lines[0].startswith("- Look ahead:")


def test_ask_first_opens_the_packet_and_survives_the_size_cap():
    text = bp.build_packet(inputs(secretary=SHEET | {"projects": [PROJECT]}, priorities="# P\n" + "- a long priority line\n" * 200))
    assert len(text) <= bp.MAX_CHARS
    assert text.index("## Ask first") < text.index("## My priorities")
    ask = text.split("## Ask first\n")[1].split("\n## ")[0]
    assert ask.count("Has *") == 2 and "Look ahead" in ask


def test_protocol_doc_lists_every_recap_line_and_the_done_line_matches_the_packet():
    doc = (bp.ROOT / "docs" / "context" / "checkin-protocol.md").read_text()
    for key in ("RECAP <YYYY-MM-DD>", "Wins:", "Top 3 next week:", "Decisions:", "Parking lot:", "Commitments:",
                "Done: <project> — <milestone>", "New project: <name> | deadline <YYYY-MM-DD> | tier",
                "New critical person: <name>"):
        assert key in doc, key
    assert bp.LOOK_AHEAD.split(":")[1].strip()[:40].lower() in doc.lower()   # the same look-ahead question


def test_end_to_end_from_the_engine_to_the_packet(tmp_path, monkeypatch):
    """The sync's refresh writes the sheet; gather() picks it up from ONS_DATA_DIR."""
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path / "data"))
    folder = tmp_path / "data" / "secretary"
    (folder / "templates").mkdir(parents=True)
    (folder / "secretary.yaml").write_text("nag_limit: 2\n")
    (folder / "templates" / "t.yaml").write_text(
        '- key: robin_birthday\n  name: Robin\'s birthday\n  tier: critical\n  person: Robin\n  when: "12-12"\n')
    db = tmp_path / "ons.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE SCHEMA main_intermediate")
    con.execute("""CREATE TABLE main_intermediate.int_events_tiered (event_key VARCHAR, source VARCHAR,
                   display_title VARCHAR, tier VARCHAR, event_date DATE, is_birthday BOOLEAN, template_key VARCHAR,
                   start_at TIMESTAMPTZ, all_day BOOLEAN)""")
    con.executemany("INSERT INTO main_intermediate.int_events_tiered VALUES (?,?,?,?,?,?,?,?,?)", [
        ("tpl:robin_birthday:2026-12-12", "template", "Robin's birthday", "critical", date(2026, 12, 12), True,
         "robin_birthday", None, True),
        ("cal:b:sam", "calendar", "Sam Example", "important", date(2026, 12, 5), True, None, None, True),
        ("cal:p:dentist", "calendar", "Dentist", "nice_to_know", date(2026, 12, 1), False, None, None, True),
    ])
    con.close()
    cfg = SC.load()
    H.refresh(TODAY, cfg=cfg, path=db, surfaces_today={"paper", "paper_lead", "checkin"},
              now=datetime(2026, 11, 29, 4, tzinfo=SC.TZ))
    S.build_and_write(TODAY, cfg=cfg, path=db)

    monkeypatch.setattr(bp, "load_warehouse", lambda inp, db_path=None: None)
    monkeypatch.setattr(bp, "load_git", lambda inp: None)
    monkeypatch.setattr(bp, "PRIORITIES", tmp_path / "missing.md")
    text = bp.build_packet(bp.gather(TODAY))
    assert section(text).splitlines() == [
        "_Calendar unavailable today: the calendar has never synced. Template dates still count; calendar events may be missing._",
        "Heads-ups for today:",
        "- Robin's birthday is in 13 days (Sat Dec 12). Gift ideas?",
        "- Sam Example is in 6 days (Sat Dec 5).",                   # its 7-day heads-up is due, so not repeated below
    ]                                                                 # the dentist is nice-to-know: paper only
    assert len(text) <= bp.MAX_CHARS
