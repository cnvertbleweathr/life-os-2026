"""
checkin/init_priorities: creates priorities.md from the template, never overwrites.

  uv run --with pytest pytest tests/test_checkin_priorities.py -q
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from checkin.init_priorities import TEMPLATE, init_priorities

ROOT = Path(__file__).resolve().parents[1]
SECTIONS = ["This week's priorities", "ONS", "Work", "Personal", "Parking lot"]


def test_template_has_the_five_sections_in_order():
    headings = [l[3:].strip() for l in TEMPLATE.read_text().splitlines() if l.startswith("## ")]
    assert headings == SECTIONS


def test_creates_once_and_never_overwrites(tmp_path):
    target = tmp_path / "priorities.md"
    assert init_priorities(target) is True
    target.write_text("## This week's priorities\n- ship the brief\n")
    assert init_priorities(target) is False
    assert "ship the brief" in target.read_text()


def test_real_priorities_file_is_gitignored():
    out = subprocess.run(["git", "check-ignore", "-q", "checkin/priorities.md"], cwd=ROOT)
    assert out.returncode == 0
