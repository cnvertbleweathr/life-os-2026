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
