"""
checkin/cadence + the daily_sync checkin_packet step.

  uv run --with pytest pytest tests/test_checkin_cadence.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from checkin import cadence

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("value, days", [
    (None, None), ("", None), ("daily", None), (" Daily ", None),
    ("weekdays", [0, 1, 2, 3, 4]),
    ("weekly:sun", [6]), ("weekly:monday", [0]), ("WEEKLY: Fri", [4]),
])
def test_parse(value, days):
    assert cadence.parse(value) == days


@pytest.mark.parametrize("value", ["hourly", "weekly:", "weekly:someday", "weekends"])
def test_bad_values_raise(value):
    with pytest.raises(ValueError):
        cadence.parse(value)


def test_bad_value_falls_back_to_daily_with_warning():
    days, warning = cadence.run_on_days("fortnightly")
    assert days is None and "posting daily" in warning


def test_reads_env(monkeypatch):
    monkeypatch.setenv(cadence.ENV_VAR, "weekly:wed")
    assert cadence.run_on_days() == ([2], None)
    monkeypatch.delenv(cadence.ENV_VAR)
    assert cadence.run_on_days() == (None, None)


def test_daily_sync_runs_checkin_last_after_the_brief_and_not_required():
    src = (ROOT / "scripts" / "daily_sync.py").read_text()
    names = re.findall(r'Step\(\s*name="([^"]+)"', src)
    assert names[-2:] == ["morning_brief", "checkin_packet"]
    block = src[src.index('name="checkin_packet"'):]
    block = block[: block.index(")\n")]
    assert "required=False" in block and "run_on_days=CHECKIN_DAYS" in block
    assert '"checkin.post_slack", "--rebuild"' in block
