"""
checkin/post_slack: mrkdwn conversion, retry-once, logging, secret hygiene. No network.

  uv run --with pytest pytest tests/test_checkin_post_slack.py -q
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from checkin import post_slack as ps

DAY = date(2026, 3, 11)
FAKE_URL = "https://hooks.slack.com/services/TFAKE/BFAKE/notarealsecret"
PACKET = """# Check-in — Wednesday, Mar 11, 2026
Days since last check-in: 2 (last packet 2026-03-09)

## My priorities
## This week's priorities

- Finish **the planter** & paint it
  - nested <thing>

## Talking points
1. See [the doc](https://example.com/a?b=1)
"""


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path))
    (tmp_path / "checkin").mkdir()
    (tmp_path / "checkin" / f"{DAY}.md").write_text(PACKET)
    return tmp_path


def posts(tmp_path):
    f = tmp_path / "checkin" / "packet_posts.jsonl"
    return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []


class FakePoster:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, payload):
        self.calls.append((url, payload))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_mrkdwn_conversion():
    text = ps.to_mrkdwn(PACKET, DAY)
    lines = text.splitlines()
    assert lines[0] == "ONS CHECK-IN — 2026-03-11"
    assert "# Check-in" not in text
    assert "*My priorities*" in lines and "*This week's priorities*" in lines
    assert "• Finish *the planter* &amp; paint it" in text
    assert "    ◦ nested &lt;thing&gt;" in text
    assert "<https://example.com/a?b=1|the doc>" in text


def test_dry_run_prints_and_posts_nothing(capsys, data_dir):
    poster = FakePoster()
    assert ps.run(DAY, dry_run=True, url=FAKE_URL, poster=poster) == 0
    out = capsys.readouterr().out
    assert out.startswith("ONS CHECK-IN — 2026-03-11")
    assert poster.calls == [] and posts(data_dir) == []


def test_posts_once_and_logs(data_dir):
    poster = FakePoster((200, "ok"))
    assert ps.run(DAY, url=FAKE_URL, poster=poster, sleep=lambda s: None) == 0
    payload = poster.calls[0][1]
    assert payload["text"].startswith("ONS CHECK-IN — 2026-03-11") and payload["mrkdwn"] is True
    [rec] = posts(data_dir)
    assert rec["ok"] is True and rec["attempts"] == 1 and rec["date"] == "2026-03-11"


def test_retries_once_then_succeeds(data_dir):
    poster = FakePoster(ConnectionError("boom"), (200, "ok"))
    slept = []
    assert ps.run(DAY, url=FAKE_URL, poster=poster, sleep=slept.append) == 0
    assert len(poster.calls) == 2 and slept == [ps.RETRY_DELAY_S]
    assert posts(data_dir)[0]["attempts"] == 2


def test_fails_after_two_attempts_and_never_leaks_the_url(capsys, data_dir):
    leaky = ConnectionError(f"Max retries exceeded with url: {FAKE_URL}")
    poster = FakePoster(leaky, (404, f"no_service {FAKE_URL}"))
    assert ps.run(DAY, url=FAKE_URL, poster=poster, sleep=lambda s: None) == 1
    [rec] = posts(data_dir)
    assert rec["ok"] is False and rec["attempts"] == 2 and rec["status"] == 404
    captured = capsys.readouterr()
    everything = captured.out + captured.err + (data_dir / "checkin" / "packet_posts.jsonl").read_text()
    assert "notarealsecret" not in everything and "hooks.slack.com" not in everything
    assert "[webhook]" in rec["error"]


def test_once_a_day_unless_forced(data_dir):
    poster = FakePoster((200, "ok"), (200, "ok"))
    ps.run(DAY, url=FAKE_URL, poster=poster, sleep=lambda s: None)
    assert ps.run(DAY, url=FAKE_URL, poster=poster, sleep=lambda s: None) == 0
    assert len(poster.calls) == 1
    assert ps.run(DAY, url=FAKE_URL, poster=poster, sleep=lambda s: None, force=True) == 0
    assert len(poster.calls) == 2


def test_missing_webhook_is_an_error_not_a_crash(monkeypatch, capsys, data_dir):
    monkeypatch.delenv(ps.ENV_VAR, raising=False)
    assert ps.run(DAY, poster=FakePoster()) == 1
    assert ps.ENV_VAR in capsys.readouterr().err
    assert posts(data_dir) == []


def test_builds_the_packet_if_missing(monkeypatch, data_dir):
    (data_dir / "checkin" / f"{DAY}.md").unlink()
    monkeypatch.setattr(ps.bp, "gather", lambda day: ps.bp.Inputs(today=day))
    monkeypatch.setattr(ps.bp, "build_packet", lambda inp: "# Check-in\n## Talking points\n1. hi\n")
    assert ps.run(DAY, dry_run=True) == 0
    assert (data_dir / "checkin" / f"{DAY}.md").exists()


def test_successful_post_feeds_days_since_last_checkin(data_dir):
    ps.run(DAY, url=FAKE_URL, poster=FakePoster((200, "ok")), sleep=lambda s: None)
    rows = ps.bp.post_log().rows()
    assert rows[0]["ok"] and rows[0]["date"] == DAY.isoformat()
