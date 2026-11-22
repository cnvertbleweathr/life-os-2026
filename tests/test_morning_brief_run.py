"""
run.py: the write → evaluate → revise loop, saving, and record_featured.
One fake client plays both writer and judge (by tool name), so no API calls;
ONS_DATA_DIR is a temp dir and featured news goes to a throwaway DuckDB file.

  uv run --with pytest pytest tests/test_morning_brief_run.py -q
"""

from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

from agents.morning_brief import evaluators as E
from agents.morning_brief import featured as F
from agents.morning_brief import run as R
from agents.morning_brief import context as C
from agents.morning_brief import writer as W

CLEAN = json.loads((Path(__file__).parent / "fixtures" / "morning_brief" / "edition_sample.json").read_text())
CLEAN.pop("_comment")
CTX = C.load_fixture()
GOOD = {"accuracy": 5, "positive_tone": 5, "humor": 4, "coverage": 4}
FLAT = {"accuracy": 5, "positive_tone": 5, "humor": 2, "coverage": 4}


def broken():
    ed = copy.deepcopy(CLEAN)
    ed["sections"][0]["items"][1]["body"] = ed["sections"][0]["items"][1]["body"].replace("11.8 miles", "12 miles")
    return ed


class FakeClient:
    """Replies to submit_edition with the next edition, to submit_review with the next scores."""

    def __init__(self, editions, scores):
        self.editions, self.scores = list(editions), list(scores)
        self.requests = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.requests.append(kw)
        if kw["tools"][0]["name"] == "submit_edition":
            reply = self.editions.pop(0)
        else:
            s = self.scores.pop(0)
            reply = {k: {"score": v, "reason": f"{k} because"} for k, v in s.items()}
            reply["fix_instructions"] = [] if min(s.values()) >= 3 else ["Add a joke to the Sports Desk."]
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=reply)],
                               usage=SimpleNamespace(input_tokens=10000, output_tokens=2000), stop_reason="tool_use")

    def writer_prompts(self):
        return [r["messages"][0]["content"] for r in self.requests if r["tools"][0]["name"] == "submit_edition"]


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ONS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(F, "DB_PATH", tmp_path / "wh.duckdb")
    return tmp_path


def loop(client):
    return R.run_loop(CTX, [], client=client, judge_client=client, log=lambda *_: None)


def test_passes_first_time():
    client = FakeClient([CLEAN], [GOOD])
    res = loop(client)
    assert res["status"] == "published" and res["revisions"] == 0
    assert res["attempts"][0]["scores"] == GOOD
    # writer 10K/2K on Sonnet = 0.04, judge 10K/2K on Haiku = 0.002
    assert res["cost_usd"] == pytest.approx(0.042)


def test_revises_with_feedback_then_passes():
    client = FakeClient([broken(), CLEAN], [GOOD, GOOD])
    res = loop(client)
    assert res["status"] == "published" and res["revisions"] == 1
    assert not res["attempts"][0]["passed"]
    second = client.writer_prompts()[1]
    assert "Your previous draft failed review" in second
    assert "12 not found in the cited facts" in second           # code check fed back verbatim
    assert res["edition"] == CLEAN


def test_judge_feedback_is_sent_back_too():
    client = FakeClient([CLEAN, CLEAN], [FLAT, GOOD])
    res = loop(client)
    assert res["revisions"] == 1
    assert "Judge: humor scored 2/5" in client.writer_prompts()[1]


def test_gives_up_after_two_revisions_and_keeps_the_best():
    client = FakeClient([broken(), CLEAN, broken()], [GOOD, FLAT, GOOD])
    res = loop(client)
    assert res["status"] == "needs_review" and res["revisions"] == 2
    assert len(res["attempts"]) == 3
    assert res["edition"] == CLEAN                                # 0 code problems beats 1
    assert res["evaluation"]["problems"][0].startswith("Judge: humor")


def test_save_writes_json_and_preview(_isolated):
    res = {"date": "2026-11-21", **loop(FakeClient([broken()] * 3, [GOOD] * 3))}
    path = R.save(res, W.brief_dir())
    saved = json.loads(path.read_text())
    assert saved["status"] == "needs_review"
    md = path.with_suffix(".md").read_text()
    assert md.startswith("> **NEEDS REVIEW**") and "Not recorded as featured" in md
    assert "12 not found" in md


def test_record_featured_only_news_links(_isolated):
    res = {"date": "2026-11-21", **loop(FakeClient([CLEAN], [GOOD]))}
    R.record(res)
    assert res["featured_recorded"] and res["featured_links"] == 3 and res["featured_added"] == 3
    con = duckdb.connect(str(_isolated / "wh.duckdb"), read_only=True)
    rows = con.execute("SELECT url, section, featured_on FROM brief.featured_news ORDER BY url").fetchall()
    con.close()
    assert [r[1] for r in rows] == ["Good News", "Good News", "Science"]
    assert {r[2] for r in rows} == {date(2026, 11, 21)}


def test_record_failure_is_noted_not_raised(monkeypatch):
    def locked(*a, **k):
        raise duckdb.IOException("Could not set lock on file")
    monkeypatch.setattr(F, "record_featured", locked)
    res = {"date": "2026-11-21", **loop(FakeClient([CLEAN], [GOOD]))}
    R.record(res)
    assert res["featured_recorded"] is False and "lock" in res["featured_error"]


def test_cli_fixture_saves_outside_data_brief_and_skips_featured(_isolated, monkeypatch, capsys):
    client = FakeClient([CLEAN], [GOOD])
    monkeypatch.setattr(W, "default_client", lambda: client)
    monkeypatch.setattr(E, "default_client", lambda: client)
    assert R.main(["--fixture"]) == 0
    runs = _isolated / "data" / "ai" / "morning_brief" / "fixture_runs"
    assert (runs / "2026-11-21.json").exists() and (runs / "2026-11-21.md").exists()
    assert not (_isolated / "data" / "brief").exists()
    assert not (_isolated / "wh.duckdb").exists()
    # a second run the same day is skipped: already published
    assert R.main(["--fixture"]) == 0
    assert "already published" in capsys.readouterr().out


def test_cli_dry_run_writes_nothing(_isolated, monkeypatch):
    client = FakeClient([broken()] * 3, [GOOD] * 3)
    monkeypatch.setattr(W, "default_client", lambda: client)
    monkeypatch.setattr(E, "default_client", lambda: client)
    assert R.main(["--fixture", "--dry-run"]) == 2               # needs_review
    assert not (_isolated / "data" / "ai" / "morning_brief" / "fixture_runs").exists()
