"""Stage 2 tests: the writer's prompt and parsing, with a fake Anthropic client."""

from __future__ import annotations

from types import SimpleNamespace

from agents.morning_brief.writer import Draft, build_messages, render_snapshot, write

SNAPSHOT = {
    "date": "2026-11-15",
    "weekday": "Sunday",
    "sections": {
        "running": {"facts": {"miles_7d": 5.1, "runs_7d": 1}, "as_of": "2026-11-10",
                    "stale": False, "notes": [], "error": None},
        "crossfit": {"facts": {"last_workout_date": "Fri Jun 26"}, "as_of": "2026-06-26",
                     "stale": True, "notes": ["CSV import is behind."], "error": None},
        "music": {"facts": {}, "as_of": None, "stale": False, "notes": [], "error": "no files"},
    },
}


class FakeClient:
    """Stands in for anthropic.Anthropic(): records requests, returns canned replies.

    With prose_first=True the first reply is plain text, to exercise the nudge."""

    def __init__(self, tool_input, prose_first=False):
        self.requests = []
        self.messages = SimpleNamespace(create=self._create)
        self._input = tool_input
        self._prose_first = prose_first

    @property
    def request(self):
        return self.requests[-1]

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        usage = SimpleNamespace(input_tokens=900, output_tokens=250)
        if self._prose_first and len(self.requests) == 1:
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="Good morning!")], usage=usage)
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=self._input)], usage=usage)


def test_render_marks_stale_and_error_sections():
    text = render_snapshot(SNAPSHOT)
    assert "- running.miles_7d: 5.1" in text
    assert "## crossfit (STALE, newest data 2026-06-26)" in text
    assert "Note: CSV import is behind." in text
    assert "## music: ERROR (no data)" in text


TOOL_INPUT = {
    "headline": " One run, many films ",
    "brief": "You ran 5.1 miles this week.",
    "claims": [{"text": "You ran 5.1 miles this week.", "fact_ids": ["running.miles_7d"]}],
}


def test_write_offers_the_tool_and_parses_claims():
    client = FakeClient(TOOL_INPUT)
    draft = write(SNAPSHOT, client=client, model="test-model")

    assert client.request["tools"][0]["name"] == "submit_brief"
    assert "running.miles_7d" in client.request["messages"][0]["content"]
    assert draft.headline == "One run, many films"
    assert draft.claims[0].fact_ids == ["running.miles_7d"]
    assert draft.usage == {"input_tokens": 900, "output_tokens": 250}


def test_write_nudges_once_when_the_model_answers_in_prose():
    client = FakeClient(TOOL_INPUT, prose_first=True)
    draft = write(SNAPSHOT, client=client, model="test-model")

    assert len(client.requests) == 2
    assert "submit_brief" in client.requests[1]["messages"][-1]["content"]
    assert draft.brief == "You ran 5.1 miles this week."
    assert draft.usage == {"input_tokens": 1800, "output_tokens": 500}   # both calls counted


def test_revision_prompt_includes_previous_draft_and_feedback():
    prev = Draft(headline="h", brief="You ran 50 miles.", claims=[])
    content = build_messages(SNAPSHOT, ["50 miles isn't in the facts; it's 5.1."], prev)[0]["content"]
    assert "You ran 50 miles." in content
    assert "- 50 miles isn't in the facts; it's 5.1." in content
