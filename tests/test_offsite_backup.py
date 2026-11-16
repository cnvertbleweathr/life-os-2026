"""ops/macmini/offsite_backup.sh against a local destination folder."""
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "ops" / "macmini" / "offsite_backup.sh"


def _backup(src: Path, day: date, hhmmss: str = "020000", age_min: int = 60) -> Path:
    p = src / f"ons_{day.isoformat()}_{hhmmss}.duckdb"
    p.write_bytes(b"duckdb" + day.isoformat().encode())
    old = time.time() - age_min * 60
    os.utime(p, (old, old))
    return p


def _run(tmp_path: Path, dest: str | None, days: str | None = None) -> subprocess.CompletedProcess:
    env_file = tmp_path / ".env"
    lines = []
    if dest is not None:
        lines.append(f"BACKUP_OFFSITE_DEST={dest}")
    if days is not None:
        lines.append(f"BACKUP_OFFSITE_DAYS={days}")
    env_file.write_text("\n".join(lines) + "\n")
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
        "ONS_ENV_FILE": str(env_file),
        "ONS_BACKUP_DIR": str(tmp_path / "backups" / "duckdb"),
    }
    return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60)


@pytest.fixture()
def src(tmp_path: Path) -> Path:
    d = tmp_path / "backups" / "duckdb"
    d.mkdir(parents=True)
    return d


def test_unset_destination_is_a_noop(tmp_path, src):
    _backup(src, date.today())
    r = _run(tmp_path, dest=None)
    assert r.returncode == 0
    assert "not set" in r.stdout


def test_copies_finished_backups_and_skips_in_progress(tmp_path, src):
    today = date.today()
    _backup(src, today - timedelta(days=1))
    _backup(src, today)
    _backup(src, today, hhmmss="090500", age_min=1)  # still being written
    dest = tmp_path / "offsite"
    r = _run(tmp_path, dest=str(dest))
    assert r.returncode == 0, r.stderr
    got = sorted(p.name for p in dest.iterdir())
    assert got == [
        f"ons_{(today - timedelta(days=1)).isoformat()}_020000.duckdb",
        f"ons_{today.isoformat()}_020000.duckdb",
    ]
    log = [json.loads(line) for line in (tmp_path / "backups" / "offsite_log.jsonl").read_text().splitlines()]
    assert log[-1]["status"] == "ok"


def test_prunes_old_copies_but_keeps_newest_and_foreign_files(tmp_path, src):
    today = date.today()
    _backup(src, today)
    dest = tmp_path / "offsite"
    dest.mkdir()
    old = dest / f"ons_{(today - timedelta(days=40)).isoformat()}_020000.duckdb"
    edge = dest / f"ons_{(today - timedelta(days=30)).isoformat()}_020000.duckdb"
    foreign = dest / "notes.txt"
    for p in (old, edge, foreign):
        p.write_text("x")
    r = _run(tmp_path, dest=str(dest), days="30")
    assert r.returncode == 0, r.stderr
    assert not old.exists()
    assert edge.exists()  # exactly 30 days old is kept
    assert foreign.exists()
    assert (dest / f"ons_{today.isoformat()}_020000.duckdb").exists()


def test_never_prunes_the_only_copy(tmp_path, src):
    ancient = date.today() - timedelta(days=90)
    _backup(src, ancient)
    dest = tmp_path / "offsite"
    r = _run(tmp_path, dest=str(dest), days="30")
    assert r.returncode == 0, r.stderr
    assert (dest / f"ons_{ancient.isoformat()}_020000.duckdb").exists()


def test_fails_when_nothing_to_copy(tmp_path, src):
    r = _run(tmp_path, dest=str(tmp_path / "offsite"))
    assert r.returncode == 1
    assert "no finished backups" in r.stderr


def test_rejects_bad_retention(tmp_path, src):
    _backup(src, date.today())
    r = _run(tmp_path, dest=str(tmp_path / "offsite"), days="thirty")
    assert r.returncode == 1


def test_rejects_unsafe_destination_path(tmp_path, src):
    _backup(src, date.today())
    r = _run(tmp_path, dest="kg@plex-server:ons;rm -rf ~")
    assert r.returncode == 1
    assert "won't pass to a shell" in r.stderr
