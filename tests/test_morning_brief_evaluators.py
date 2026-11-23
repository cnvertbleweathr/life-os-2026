"""
The evaluator: code checks against the sample context, and the judge with a
fake client. No API calls; ONS_DATA_DIR is a temp dir.

The sample edition is clean; each test breaks it one way and checks that the
right check catches it with a fix the writer can act on.

  uv run --with pytest pytest tests/test_morning_brief_evaluators.py -q
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.morning_brief import context as C
from agents.morning_brief import evaluators as E

EDITION = json.loads((Path(__file__).parent / "fixtures" / "morning_brief" / "edition_sample.json").read_text())
EDITION.pop("_comment")
CTX = C.load_fixture()
RECENT = [{"date": "2026-11-18", "weekday": "Wednesday", "lead_headline": "Otters!", "stories": []}]


@pytest.fixture(autouse=True)
def _tmp_data(tmp_path, monkeypatch):
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path))
    return tmp_path


def edited(section: str, i: int, **changes):
    ed = copy.deepcopy(EDITION)
    item = next(s for s in ed["sections"] if s["name"] == section)["items"][i]
    item.update(changes)
    return ed


def problems(ed, recent=RECENT):
    return [p for ps in E.deterministic_checks(ed, CTX, recent).values() for p in ps]


def test_sample_edition_is_clean():
    assert problems(EDITION) == []


def test_unknown_ref_and_link():
    ps = problems(edited("Sports Desk", 0, source_refs=["pick:2026:12:nope"], link="https://made.up/x"))
    assert any("aren't in the context" in p for p in ps)
    assert any("isn't a url in the context" in p for p in ps)


def test_news_link_must_match_cited_story():
    ps = problems(edited("Science", 0, link="https://example.org/good/library-rebuild"))
    assert any("set link to the cited story's url (https://example.org/science/battery)" in p for p in ps)


def test_wrong_number_is_caught_and_exact_copy_required():
    body = EDITION["sections"][0]["items"][1]["body"].replace("11.8 miles", "12 miles")
    ps = problems(edited("Your Week", 1, body=body))
    assert any("12 not found in the cited facts" in p for p in ps)
    body = EDITION["sections"][0]["items"][1]["body"].replace("6.2 miles", "6 miles")   # rounding
    assert any("6 not found" in p for p in problems(edited("Your Week", 1, body=body)))


def test_number_must_come_from_a_cited_ref():
    # 285 is real, but this item doesn't cite the deadlift
    body = EDITION["sections"][0]["items"][1]["body"] + " Plus that 285 deadlift."
    assert any("285 not found" in p for p in problems(edited("Your Week", 1, body=body)))


def test_records_and_scores_with_hyphens_match_facts():
    body = EDITION["sections"][1]["items"][1]["body"].replace("7-4", "9-4")
    assert any("9 not found" in p for p in problems(edited("Sports Desk", 1, body=body)))


def test_weekday_must_match_a_cited_date():
    body = EDITION["sections"][0]["items"][0]["body"].replace("Monday's", "Thursday's")
    assert any("Thursday doesn't match" in p for p in problems(edited("Your Week", 0, body=body)))


def test_featured_story_needs_follow_up_framing():
    ps = problems(edited("Good News", 1, headline="The Otters Are Staying",
                         body="Otters are back in a river that took two decades to clean. Cameras have now caught "
                              "them breeding, which is the river's way of leaving a five-star review for everyone."))
    assert any("frame it as a follow-up" in p for p in ps)


def test_call_back_needs_a_real_edition():
    assert any("points at an edition that doesn't exist" in p
               for p in problems(EDITION, recent=[]) + problems(
                   edited("Good News", 1, body=EDITION["sections"][2]["items"][1]["body"].replace("Wednesday", "Tuesday"))))


def test_same_story_twice():
    ed = copy.deepcopy(EDITION)
    ed["sections"][2]["items"][1] = copy.deepcopy(ed["sections"][2]["items"][0])
    assert any("already ran in Good News item 1" in p for p in problems(ed))


def test_copying_from_the_story_is_caught():
    body = ("A group of retirees spent a year restoring a shuttered library, and the town is delighted "
            "with the result, which now has thousands of donated books for every reader in town.")
    assert any("is copied from the story" in p for p in problems(edited("Good News", 0, body=body)))


def test_numbers_alone_are_not_copying():
    body = ("Lab results show the sodium-based cell kept 90% of its capacity after 10,000 cycles, "
            "and the cheerful news is that storage keeps getting sturdier, one patient test at a time.")
    assert not any("copied" in p for p in problems(edited("Science", 0, body=body)))


def test_field_names_and_refs_in_prose():
    body = EDITION["sections"][0]["items"][1]["body"].replace("11.8 miles", "11.8 run_miles (fitness:week)")
    ps = problems(edited("Your Week", 1, body=body))
    assert any("run_miles" in p and "fitness:week" in p for p in ps)


def test_schema_failure_short_circuits_and_skips_judge():
    ev = E.evaluate({"date": "2026-11-21"}, CTX, RECENT, client=None)
    assert list(ev.checks) == ["structure"] and ev.judgement is None and not ev.passed


# ── judge ────────────────────────────────────────────────────────────────────

class FakeJudge:
    def __init__(self, scores, fixes=()):
        self.requests = []
        self.messages = SimpleNamespace(create=self._create)
        self.reply = {k: {"score": v, "reason": f"{k} reason"} for k, v in scores.items()}
        self.reply["fix_instructions"] = list(fixes)

    def _create(self, **kw):
        self.requests.append(kw)
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=self.reply)],
                               usage=SimpleNamespace(input_tokens=10000, output_tokens=800), stop_reason="tool_use")


def test_judge_pass_and_cost(_tmp_data):
    client = FakeJudge({"accuracy": 5, "positive_tone": 4, "humor": 3, "coverage": 4})
    ev = E.evaluate(EDITION, CTX, RECENT, client=client)
    assert ev.passed
    req = client.requests[0]
    assert req["model"] == "claude-haiku-5-5" and req["tools"][0]["strict"] is True
    assert "## Draft edition" in req["messages"][0]["content"]
    assert ev.cost_usd == pytest.approx(0.0014)          # 10K in * $0.10 + 800 out * $0.50 per M
    log = (_tmp_data / "ai" / "generations.jsonl").read_text().splitlines()
    assert json.loads(log[-1])["analyzer_name"] == "morning_brief_judge"


def test_low_scores_fail_with_fix_instructions():
    client = FakeJudge({"accuracy": 5, "positive_tone": 4, "humor": 2, "coverage": 4},
                       fixes=["Sports Desk item 1: add a joke about the pending pick."])
    ev = E.evaluate(EDITION, CTX, RECENT, client=client)
    assert not ev.passed
    assert ev.problems[0].startswith("Judge: humor scored 2/5 (needs 3)")
    assert "Judge fix: Sports Desk item 1" in ev.problems[1]


def test_code_problems_and_judge_feedback_combine():
    ed = edited("Science", 0, link=None)
    ev = E.evaluate(ed, CTX, RECENT, client=FakeJudge({k: 5 for k in E.THRESHOLDS}))
    assert not ev.passed and ev.judgement is not None
    assert any("news items need the story's url" in p for p in ev.problems)
