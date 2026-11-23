"""
The writer: prompt, validation, logging and cost. A fake Anthropic client, so no
API calls; ONS_DATA_DIR is a temp dir, so generations.jsonl and saved editions
are never the real ones.

  uv run --with pytest pytest tests/test_morning_brief_writer.py -q
"""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from agents.morning_brief import context as C
from agents.morning_brief import llm
from agents.morning_brief import writer as W


@pytest.fixture(autouse=True)
def _tmp_data(tmp_path, monkeypatch):
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path))
    return tmp_path


class FakeClient:
    """Stands in for anthropic.Anthropic(): records requests, returns canned replies."""

    def __init__(self, tool_input, prose_first=False, stop_reason="tool_use"):
        self.requests = []
        self.messages = SimpleNamespace(create=self._create)
        self._input, self._prose_first, self._stop = tool_input, prose_first, stop_reason

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        usage = SimpleNamespace(input_tokens=9000, output_tokens=2000)
        if self._prose_first and len(self.requests) == 1:
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="Extra! Extra!")],
                                   usage=usage, stop_reason="end_turn")
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=self._input)],
                               usage=usage, stop_reason=self._stop)


BODY = ("Your correspondent can confirm a deadlift of 285 on Monday, a personal record, "
        "followed by three runs that added up to 11.8 miles for the week. The training "
        "ledger is in the black and the shoes are asking for a raise.")

GOOD = {
    "date": "2026-11-21",
    "masthead_tagline": "All the miles that are fit to print",
    "lead_headline": "Deadlift PR Rocks the Week",
    "sections": [
        {"name": "Your Week", "items": [
            {"headline": "Barbell Bends, Records Break", "body": BODY,
             "source_refs": ["sugarwod:2026-11-16:aaaa0001", "fitness:week"], "link": None}]},
        {"name": "Sports Desk", "items": [
            {"headline": "UCF Wins in the Desert", "body": BODY, "source_refs": ["cfb_game:100000001"], "link": None},
            {"headline": "Penn State Hosts Rutgers Today", "body": BODY, "source_refs": ["cfb_game:100000002"], "link": None}]},
        {"name": "Good News", "items": [
            {"headline": "Retirees Reopen a Library", "body": BODY, "source_refs": ["news:0000000000000001"],
             "link": "https://example.org/good/library-rebuild"},
            {"headline": "Follow-up: Otters Settle In", "body": BODY, "source_refs": ["news:0000000000000002"],
             "link": "https://example.org/good/otters"}]},
        {"name": "Science", "items": [
            {"headline": "A Battery That Will Not Quit", "body": BODY, "source_refs": ["news:0000000000000003"],
             "link": "https://example.org/science/battery"}]},
        {"name": "Tip of the Day", "items": [
            {"headline": "Rest Is Training Too", "body": BODY, "source_refs": ["fitness:training_load"], "link": None}]},
    ],
}


def test_valid_edition_has_no_problems():
    assert W.validate_edition(GOOD, "2026-11-21") == []


def test_structural_problems_are_phrased_as_fixes():
    bad = copy.deepcopy(GOOD)
    bad["sections"] = bad["sections"][:4]                     # no Tip of the Day
    bad["sections"][2]["items"][0]["link"] = None             # news without link
    bad["sections"][0]["items"][0]["body"] = "Too short."
    bad["lead_headline"] = "word " * 20
    probs = W.validate_edition(bad, "2026-11-22")
    text = "\n".join(probs)
    assert "Set date to 2026-11-22" in text
    assert "Shorten the lead headline" in text
    assert "Sections must be exactly" in text
    assert "news items need the story's url" in text
    assert "body is 2 words" in text


def test_schema_violations_are_reported_not_raised():
    probs = W.validate_edition({"date": "2026-11-21", "sections": []})
    assert any("masthead_tagline" in p for p in probs)


def test_write_sends_context_and_logs_cost(_tmp_data):
    client = FakeClient(GOOD)
    ed = W.write(C.load_fixture(), client=client, recent=[])
    req = client.requests[0]
    assert req["model"] == W.MODEL
    assert req["tools"][0]["strict"] is True
    assert req["tool_choice"] == {"type": "auto"}            # forced tool_choice 400s on 5.5 models
    assert req["output_config"] == {"effort": W.EFFORT}
    prompt = req["messages"][0]["content"]
    assert '"ref":"fitness:week"' in prompt and "## news" in prompt
    assert "(none saved yet" in prompt
    assert ed.problems == []
    # 9000 in / 2000 out on Sonnet 5.5 = 0.018 + 0.020
    assert ed.cost_usd == pytest.approx(0.038)
    log = [json.loads(l) for l in (_tmp_data / "ai" / "generations.jsonl").read_text().splitlines()]
    assert log[-1]["analyzer_name"] == "morning_brief_writer"
    assert log[-1]["cost_usd"] == pytest.approx(0.038)
    assert log[-1]["status"] == "success"


def test_revision_includes_previous_draft_and_fixes():
    ed = W.Edition(data=GOOD)
    msgs = W.build_messages(C.load_fixture(), [], feedback=["Science: use a science story."], previous=ed)
    text = msgs[0]["content"]
    assert "Your previous draft failed review" in text
    assert "- Science: use a science story." in text
    assert "Deadlift PR Rocks the Week" in text


def test_recent_editions_read_saved_briefs(_tmp_data):
    (_tmp_data / "brief").mkdir()
    (_tmp_data / "brief" / "2026-11-18.json").write_text(json.dumps({"edition": GOOD}))
    recent = W.recent_editions(__import__("datetime").date(2026, 11, 21))
    assert recent[0]["weekday"] == "Wednesday"
    assert recent[0]["lead_headline"] == GOOD["lead_headline"]
    assert "https://example.org/good/otters" in [s["link"] for s in recent[0]["stories"]]


def test_prose_reply_gets_one_nudge_and_failures_are_logged(_tmp_data):
    client = FakeClient(GOOD, prose_first=True)
    W.write(C.load_fixture(), client=client, recent=[])
    assert len(client.requests) == 2
    with pytest.raises(RuntimeError, match="max_tokens"):
        W.write(C.load_fixture(), client=FakeClient(GOOD, stop_reason="max_tokens"), recent=[])
    last = json.loads((_tmp_data / "ai" / "generations.jsonl").read_text().splitlines()[-1])
    assert last["status"] == "failed" and "max_tokens" in last["error_message"]


def test_budget_guard_refuses_when_month_is_spent(_tmp_data):
    llm.GENERATIONS_LOG.append({"timestamp": llm.now_local().isoformat(), "cost_usd": llm.MONTHLY_BUDGET_USD})
    with pytest.raises(llm.BudgetExceeded):
        W.write(C.load_fixture(), client=FakeClient(GOOD), recent=[])


def test_markdown_preview():
    md = W.to_markdown(GOOD)
    assert "Saturday, November 21, 2026" in md
    assert "[Read more](https://example.org/good/otters)" in md
    assert md.index("### Your Week") < md.index("### Tip of the Day")
