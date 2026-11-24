"""
checkin/slack_recaps.py: RECAPs posted in the Slack check-in channel or a packet's thread are queued for
ingest_recap, once each. Slack is faked; temp ONS_DATA_DIR; made-up names.

  uv run --with pytest pytest tests/test_secretary_slack_recaps.py -q
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest

from checkin import ingest_recap as IR
from checkin import slack_recaps as SR

ROOT = Path(__file__).resolve().parents[1]
CH = "C0TEST"
NOW = 1_765_400_000.0

# What voice-mode Claude posts through Slack: mrkdwn bold, bullets, &amp; escapes, maybe a lead-in line.
THREAD_RECAP = ("Here's today's recap:\n*RECAP 2026-12-04*\n• *Wins:* pool tour booked &amp; three runs\n"
                "• *Done:* Robin's swim school — Sign-up opens\n• *New critical person:* Alex Sample")
CHANNEL_RECAP = "```RECAP 2026-12-05\nDone: Robin's swim school — Pick a time slot\n```"


class FakeSlack:
    def __init__(self):
        self.calls = []
        self.history = [
            {"ts": "100.0", "text": "ONS CHECK-IN — 2026-12-04\n…packet…", "reply_count": 2},
            {"ts": "200.0", "text": CHANNEL_RECAP},
            {"ts": "300.0", "text": "ONS MORNING BRIEF — not a recap"},
            {"ts": "400.0", "text": "RECAP someday\nnot really"},          # no date: still a RECAP (dated today)
        ]
        self.replies = {"100.0": [{"ts": "100.0", "text": "ONS CHECK-IN — 2026-12-04"},
                                  {"ts": "101.0", "text": THREAD_RECAP},
                                  {"ts": "102.0", "text": "thanks!"}]}

    def __call__(self, method, params):
        self.calls.append((method, params))
        if method == "conversations.history":
            assert params["channel"] == CH and float(params["oldest"]) == pytest.approx(NOW - 14 * 86400)
            return {"ok": True, "messages": self.history}
        if method == "conversations.replies":
            return {"ok": True, "messages": self.replies[params["ts"]]}
        raise AssertionError(method)


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("ONS_DEV", raising=False)
    f = tmp_path / "data" / "secretary"
    f.mkdir(parents=True)
    (f / "projects.yaml").write_text("""
- key: swim
  name: Robin's swim school
  tier: critical
  milestones:
    - {key: signup_opens, title: Sign-up opens, due: 2026-12-01}
    - {key: slot, title: Pick a time slot, due: 2026-12-09}
""")
    return f


def test_recap_text_handles_slack_formatting():
    t = SR.recap_text(THREAD_RECAP)
    assert t.startswith("*RECAP 2026-12-04*") and "pool tour booked & three runs" in t
    assert SR.recap_text("> RECAP 2026-12-04\n> Done: A — B") == "RECAP 2026-12-04\nDone: A — B"
    assert SR.recap_text("no recap in here") is None
    r = IR.parse(t)
    assert r.date == date(2026, 12, 4) and r.done == [("Robin's swim school", "Sign-up opens")]
    assert r.sections["wins"] == ["pool tour booked & three runs"] and r.new_people == ["Alex Sample"]


def test_collect_reads_channel_and_threads_once_each(folder):
    slack = FakeSlack()
    res = SR.collect(slack, CH, now=NOW)
    assert [q["source_id"] for q in res["queued"]] == [f"slack:{CH}:200.0", f"slack:{CH}:400.0", f"slack:{CH}:101.0"]
    assert ("conversations.replies", {"channel": CH, "ts": "100.0", "limit": 200}) in slack.calls
    rows = IR.recaps_log().rows()
    assert {r["source"] for r in rows} == {"slack"}

    again = SR.collect(FakeSlack(), CH, now=NOW)                         # the next morning's run
    assert again["queued"] == [] and len(again["skipped"]) == 3
    assert len(IR.recaps_log().rows()) == 3


def test_slack_recaps_flow_through_ingest(folder):
    SR.collect(FakeSlack(), CH, now=NOW)
    results = {r["recap_date"]: r for r in IR.ingest(date(2026, 12, 6))}
    assert results["2026-12-04"]["done"] == ["Robin's swim school — Sign-up opens"]
    assert results["2026-12-04"]["proposed_people"] == ["Alex Sample"]
    assert results["2026-12-05"]["done"] == ["Robin's swim school — Pick a time slot"]


def test_not_configured_is_a_clean_skip(folder, monkeypatch, capsys):
    monkeypatch.setattr(SR, "ROOT", folder)                              # no .env there
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_CHECKIN_CHANNEL_ID", raising=False)
    assert SR.main([]) == 0
    assert "not configured" in capsys.readouterr().out


def test_slack_error_fails_the_step_without_queuing(folder, monkeypatch, capsys):
    monkeypatch.setattr(SR, "ROOT", folder)
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_CHECKIN_CHANNEL_ID", CH)

    def broken(token):
        def call(method, params):
            raise RuntimeError("Slack conversations.history: not_in_channel")
        return call
    monkeypatch.setattr(SR, "_http", broken)
    assert SR.main([]) == 1
    assert "not_in_channel" in capsys.readouterr().err and not IR.recaps_log().path.exists()


def test_sync_reads_slack_before_ingesting():
    tree = ast.parse((ROOT / "scripts" / "daily_sync.py").read_text())   # parse, never import
    lines = {kw.value.value: node.lineno for node in ast.walk(tree)
             if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Step"
             for kw in node.keywords if kw.arg == "name"}
    assert lines["slack_recaps"] < lines["ingest_recap"] < lines["secretary_config"]
