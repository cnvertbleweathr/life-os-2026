"""
print_edition: layout and print rules. Chrome and lp are faked, so nothing
renders or prints; editions live in a temp ONS_DATA_DIR.

  uv run --with pytest pytest tests/test_morning_brief_print.py -q
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from agents.morning_brief import print_edition as P

EDITION = json.loads((Path(__file__).parent / "fixtures" / "morning_brief" / "edition_sample.json").read_text())
EDITION.pop("_comment")
SATURDAY, MONDAY = date(2026, 11, 21), date(2026, 11, 23)


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ONS_PRINT_AT", "00:00")         # these tests aren't about the print time
    monkeypatch.setenv("ONS_PRINT_UNTIL", "23:59")
    calls = {"pdf": [], "lp": []}

    def fake_pdf(page, pdf_path):
        calls["pdf"].append(page)
        pdf_path.write_bytes(b"%PDF /Type /Page >>")          # one page
        return pdf_path

    monkeypatch.setattr(P, "to_pdf", fake_pdf)
    monkeypatch.setattr(P, "send_to_printer", lambda pdf, title, printer=None: calls["lp"].append(title) or "Q-1")

    def make(status="published", **extra):
        folder = tmp_path / "brief"
        folder.mkdir(exist_ok=True)
        path = folder / "2026-11-21.json"
        path.write_text(json.dumps({"date": "2026-11-21", "status": status, "edition": EDITION,
                                    "revisions": 1, "evaluation": {"judge": {"scores": {"humor": 4}}}, **extra}))
        return path
    make.calls = calls
    return make


def test_html_has_masthead_sections_and_sources():
    page = P.render_html({"status": "published", "edition": EDITION, "revisions": 0})
    assert "The ONS Morning Edition" in page and "Saturday, November 21, 2026" in page
    assert page.index("Your Week") < page.index("Tip of the Day")
    assert '<div class="src">example.org</div>' in page
    assert "NEEDS REVIEW" not in page
    assert "&lt;" not in P.render_html({"status": "published", "edition": EDITION})   # escaped, not mangled


def test_prints_published_edition_once(saved):
    path = saved()
    out = P.print_edition(path, auto=True, today=MONDAY)
    assert out["printed"] and out["job"] == "Q-1" and out["pages"] == 1
    assert json.loads(path.read_text())["print_job"] == "Q-1"
    again = P.print_edition(path, auto=True, today=MONDAY)
    assert not again["printed"] and "already printed" in again["reason"]
    assert len(saved.calls["lp"]) == 1


def test_auto_skips_weekends(saved):
    out = P.print_edition(saved(), auto=True, today=SATURDAY)
    assert not out["printed"] and "weekdays only" in out["reason"]
    assert saved.calls["lp"] == []


def test_auto_waits_for_print_time(saved, monkeypatch):
    monkeypatch.setenv("ONS_PRINT_AT", "05:00")
    path = saved()
    early = P.print_edition(path, auto=True, now=datetime(2026, 11, 23, 4, 25))
    assert not early["printed"] and "05:00" in early["reason"]
    assert saved.calls["lp"] == [] and "printed_at" not in json.loads(path.read_text())
    assert P.print_edition(path, auto=True, now=datetime(2026, 11, 23, 5, 0))["printed"]


def test_late_sync_prints_inside_the_window_but_not_after_six(saved, monkeypatch):
    monkeypatch.setenv("ONS_PRINT_AT", "05:00")
    monkeypatch.setenv("ONS_PRINT_UNTIL", "06:00")
    late = P.print_edition(saved(), auto=True, now=datetime(2026, 11, 23, 9, 40))
    assert not late["printed"] and "06:00" in late["reason"]
    assert P.print_edition(saved(), auto=True, now=datetime(2026, 11, 23, 5, 40))["printed"]


# ── the 5:00 launchd job: --scheduled ────────────────────────────────────────

class Clock:
    """Fake wall clock; sleep() advances it."""
    def __init__(self, start):
        self.t = start
        self.sleeps = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += timedelta(seconds=s)


def write_edition(tmp_path, day, status="published"):
    folder = tmp_path / "brief"
    folder.mkdir(exist_ok=True)
    path = folder / f"{day}.json"
    path.write_text(json.dumps({"date": str(day), "status": status, "edition": EDITION, "revisions": 2,
                                "evaluation": {"problems": ["Number 7 isn't in the cited facts."]}}))
    return path


def print_log(tmp_path):
    f = tmp_path / "brief" / "print_log.jsonl"
    return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []


@pytest.fixture
def window(saved, monkeypatch):
    monkeypatch.setenv("ONS_PRINT_AT", "05:00")
    monkeypatch.setenv("ONS_PRINT_UNTIL", "06:00")
    return saved


def test_scheduled_prints_todays_edition_once(window, tmp_path):
    write_edition(tmp_path, MONDAY)
    clock = Clock(datetime(2026, 11, 23, 5, 0))
    out = P.scheduled_print(MONDAY, now=clock.now, sleep=clock.sleep, notify=lambda t: True)
    assert out["printed"] and clock.sleeps == []
    assert window.calls["lp"] == ["ONS Morning Edition 2026-11-23"]
    assert print_log(tmp_path)[-1]["outcome"] == "printed"


def test_scheduled_retries_every_ten_minutes_until_the_edition_appears(window, tmp_path):
    clock = Clock(datetime(2026, 11, 23, 5, 0))

    def sleep(s):
        clock.sleep(s)
        if clock.t >= datetime(2026, 11, 23, 5, 20):
            write_edition(tmp_path, MONDAY)               # the sync finishes at ~5:20
    out = P.scheduled_print(MONDAY, now=clock.now, sleep=sleep, notify=lambda t: True)
    assert out["printed"] and clock.sleeps == [600, 600]


def test_scheduled_gives_up_at_six_and_logs_it(window, tmp_path):
    clock = Clock(datetime(2026, 11, 23, 5, 0))
    out = P.scheduled_print(MONDAY, now=clock.now, sleep=clock.sleep, notify=lambda t: True)
    assert not out["printed"] and clock.t == datetime(2026, 11, 23, 6, 0)
    assert len(clock.sleeps) == 6 and window.calls["lp"] == []
    assert print_log(tmp_path)[-1]["outcome"] == "skipped_no_edition"


def test_scheduled_never_prints_yesterdays_edition(window, tmp_path):
    path = write_edition(tmp_path, MONDAY)
    path.write_text(path.read_text().replace('"2026-11-23"', '"2026-11-22"'))   # stale content
    clock = Clock(datetime(2026, 11, 23, 5, 55))
    out = P.scheduled_print(MONDAY, now=clock.now, sleep=clock.sleep, notify=lambda t: True)
    assert not out["printed"] and window.calls["lp"] == []


def test_needs_review_posts_a_slack_note_instead_of_printing(window, tmp_path):
    write_edition(tmp_path, MONDAY, status="needs_review")
    notes = []
    clock = Clock(datetime(2026, 11, 23, 5, 0))
    out = P.scheduled_print(MONDAY, now=clock.now, sleep=clock.sleep, notify=lambda t: notes.append(t) or True)
    assert not out["printed"] and window.calls["lp"] == []
    [note] = notes
    assert note.startswith("ONS MORNING BRIEF — 2026-11-23: needs review, not printed")
    assert "Number 7" in note
    assert print_log(tmp_path)[-1]["outcome"] == "needs_review_noted"
    # a second run the same day doesn't post again
    P.scheduled_print(MONDAY, now=clock.now, sleep=clock.sleep, notify=lambda t: notes.append(t) or True)
    assert len(notes) == 1


def test_manual_print_ignores_print_time(saved, monkeypatch):
    monkeypatch.setenv("ONS_PRINT_AT", "05:00")
    assert P.print_edition(saved(), now=datetime(2026, 11, 23, 3, 0))["printed"]


def test_bad_print_time_falls_back_to_five(saved, monkeypatch):
    monkeypatch.setenv("ONS_PRINT_AT", "five-ish")
    assert not P.print_edition(saved(), auto=True, now=datetime(2026, 11, 23, 4, 59))["printed"]


def test_cli_reports_missing_edition_without_failing(saved, capsys):
    assert P.main(["--auto", "--date", "2026-11-23"]) == 0
    assert "No edition" in capsys.readouterr().out


def test_needs_review_prints_only_when_forced(saved):
    path = saved(status="needs_review")
    assert not P.print_edition(path, auto=True, today=MONDAY)["printed"]
    assert not P.print_edition(path, today=MONDAY)["printed"]
    assert P.print_edition(path, force=True, today=MONDAY)["printed"]
    assert "NEEDS REVIEW" in saved.calls["pdf"][-1]


def test_shrinks_until_it_fits_one_page(saved, monkeypatch):
    zooms = []

    def two_then_one(page, pdf_path):
        zooms.append(page)
        pdf_path.write_bytes(b"/Type /Page /Type /Page " if len(zooms) < 3 else b"/Type /Page ")
        return pdf_path

    monkeypatch.setattr(P, "to_pdf", two_then_one)
    out = P.print_edition(saved(), pdf_only=True)
    assert out["pages"] == 1 and len(zooms) == 3 and "zoom: 0.88" in zooms[-1]
