"""Stage 3 tests: grounding, style and the tone judge.

The fixture is the real brief from the first working run (Nov 15, 2026). By
hand it looked clean; the grounding check finds the two things it got wrong.
"""

from __future__ import annotations

import pytest

pytest.skip("evaluators.py still checks the old claims-based Draft; it is rewritten "
            "for the newspaper Edition in stage 3 of feat/brief-agent", allow_module_level=True)

from dataclasses import replace
from types import SimpleNamespace

from agents.morning_brief.evaluators import (
    THRESHOLDS, check_grounding, check_style, evaluate, extract_tokens)
from agents.morning_brief.writer import Claim, Draft

FACTS = {
    "shows.tonight": ["Sun Nov 15: The Living Tombstone at Mission Ballroom (7:00 PM)",
                      "Sun Nov 15: The Black Angels at Gothic Theatre (8:00 PM)",
                      "Sun Nov 15: Arcángel - La 8va Maravilla World Tour at Paramount Theatre (8:00 PM)"],
    "film.films_7d": 5, "film.films_ytd": 45,
    "film.last_film_title": "One Flew Over the Cuckoo's Nest", "film.last_film_date": "Thu Nov 12",
    "running.runs_7d": 1, "running.miles_7d": 5.1, "running.last_run_date": "Tue Nov 10",
    "running.last_run_miles": 5.1,
    "goals.running_miles_target": 350.0, "goals.running_miles_current": 282.5,
    "goals.running_miles_pace": "at_risk",
    "reading.last_finished_title": "Empire of the Vampire", "reading.last_finished_date": "Sat Sep 5",
    "reading.days_since_last_finished": 71, "reading.books_finished_ytd": 7,
    "habits.logged_yesterday": False, "habits.days_logged_7d": 0, "habits.newest_data": "Fri Nov 6",
}

BRIEF = (
    "Tonight Denver offers The Living Tombstone at Mission Ballroom at 7:00 PM, plus The Black Angels "
    "at Gothic Theatre and Arcángel at Paramount Theatre, both at 8:00 PM. These are matched from your "
    "playlists, not tickets you hold, so the couch remains a legitimate option.\n\n"
    "You watched five films this past week, the latest being One Flew Over the Cuckoo's Nest on "
    "Thursday, which brings the year to 45. Your running shoes have had a quieter time: one 5.1-mile "
    "run, last Tuesday. Your 350-mile goal sits at 282.5 miles and is flagged at risk, and the clock "
    "is not on your side.\n\n"
    "Meanwhile, the last book you finished was Empire of the Vampire on Sep 5, 71 days ago, with 7 "
    "books finished this year. The habit tracker hasn't heard from you since Nov 6, so I'll assume "
    "you've been busy and not simply avoiding it."
)

C = Claim
REAL = Draft(
    headline="Three concerts tonight, zero tickets, and a very busy couch",
    brief=BRIEF,
    claims=[
        C("Tonight Denver offers The Living Tombstone at Mission Ballroom at 7:00 PM, plus The Black "
          "Angels at Gothic Theatre and Arcángel at Paramount Theatre, both at 8:00 PM.", ["shows.tonight"]),
        C("These are matched from your playlists, not tickets you hold", ["shows.tonight"]),
        C("You watched five films this past week", ["film.films_7d"]),
        C("the latest being One Flew Over the Cuckoo's Nest on Thursday",
          ["film.last_film_title", "film.last_film_date"]),
        C("which brings the year to 45", ["film.films_ytd"]),
        C("one 5.1-mile run, last Tuesday",
          ["running.runs_7d", "running.miles_7d", "running.last_run_date", "running.last_run_miles"]),
        C("Your 350-mile goal sits at 282.5 miles and is flagged at risk",
          ["goals.running_miles_target", "goals.running_miles_current", "goals.running_miles_pace"]),
        C("the last book you finished was Empire of the Vampire on Sep 5, 71 days ago",
          ["reading.last_finished_title", "reading.last_finished_date", "reading.days_since_last_finished"]),
        C("with 7 books finished this year", ["reading.books_finished_ytd"]),
        C("The habit tracker hasn't heard from you since Nov 6",
          ["habits.logged_yesterday", "habits.days_logged_7d"]),
    ],
)


def test_tokens_cover_times_dates_weekdays_and_number_words():
    toks = extract_tokens("five films by Sep 5, 71 days ago, at 7:00 PM on Thursday")
    assert [(t.kind, t.value) for t in toks] == [
        ("number", 5.0), ("date", "Sep 5"), ("number", 71.0), ("time", "7:00 PM"), ("weekday", "Thu")]


def test_real_brief_has_two_grounding_problems():
    problems = check_grounding(REAL, FACTS)
    assert len(problems) == 2, problems
    assert any('"Three" appears in the brief without a claim' in p for p in problems)
    assert any('"Nov 6"' in p and "habits.logged_yesterday" in p for p in problems)


def test_fixed_brief_is_grounded():
    claims = [c if "Nov 6" not in c.text else C(c.text, ["habits.newest_data"]) for c in REAL.claims]
    claims.append(C("Three concerts tonight", ["shows.tonight"]))   # a list's length counts
    assert check_grounding(replace(REAL, claims=claims), FACTS) == []


def test_invented_numbers_and_bad_ids_are_caught():
    d = Draft(headline="Big week", brief="You ran 50 miles this week.",
              claims=[C("You ran 50 miles this week.", ["running.miles_7d", "running.vibes"])])
    problems = check_grounding(d, FACTS)
    assert any("running.vibes" in p for p in problems)
    assert any('"50"' in p for p in problems)


def test_style_flags_first_person():
    problems = check_style(REAL)
    assert any("I'll" in p for p in problems)
    assert not any("paragraphs" in p or "headline" in p for p in problems)


class FakeJudge:
    def __init__(self, scores):
        self.calls = 0
        review = {k: {"score": s, "reason": f"{k} reason"} for k, s in scores.items()}
        review |= {"best_line": "the couch remains a legitimate option",
                   "suggestions": ["Make the habit line a real joke."]}
        self._review = review
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=self._review)],
                               usage=SimpleNamespace(input_tokens=400, output_tokens=200),
                               stop_reason="tool_use")


def test_judge_scores_and_code_decides():
    clean = replace(REAL, brief=BRIEF.replace(", so I'll assume you've been busy and not simply avoiding it",
                                              ", a silence you can interpret however you like"),
                    claims=[c if "Nov 6" not in c.text else C(c.text, ["habits.newest_data"]) for c in REAL.claims]
                    + [C("Three concerts tonight", ["shows.tonight"])])
    judge = FakeJudge({"funny": 2, "kind": 5, "light": 4, "voice": 5})
    # evaluate() takes a snapshot, so rebuild a minimal one from FACTS.
    snapshot = {"sections": {}}
    for fid, v in FACTS.items():
        sec, key = fid.split(".", 1)
        snapshot["sections"].setdefault(sec, {"facts": {}})["facts"][key] = v
    result = evaluate(clean, snapshot, client=judge)

    assert result.grounding == [] and result.style == []
    assert judge.calls == 1
    assert not result.passed
    assert result.problems[0].startswith("Tone: funny scored 2/5 (needs 3)")
    assert "Suggestion: Make the habit line a real joke." in result.problems


def test_judge_is_skipped_when_grounding_fails():
    judge = FakeJudge({k: 5 for k in THRESHOLDS})
    snapshot = {"sections": {"film": {"facts": {"films_7d": 5}}}}
    result = evaluate(REAL, snapshot, client=judge)
    assert result.grounding and result.tone is None and judge.calls == 0
