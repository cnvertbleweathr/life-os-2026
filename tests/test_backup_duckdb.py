"""
scripts/backup_duckdb.py: transactional backups (COPY FROM DATABASE, not a file
copy), verified by per-table row counts, restorable to any path.

  uv run --with pytest pytest tests/test_backup_duckdb.py -q
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("backup_duckdb", ROOT / "scripts" / "backup_duckdb.py")
B = importlib.util.module_from_spec(spec)
sys.modules["backup_duckdb"] = B
spec.loader.exec_module(B)


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    db = tmp_path / "warehouse" / "ons.duckdb"
    db.parent.mkdir()
    con = duckdb.connect(str(db))
    con.execute("create schema raw; create table raw.a as select range as i from range(1000)")
    con.execute("create table main.b(x varchar); insert into main.b values ('one'), ('two')")
    con.execute("create view main.v as select count(*) n from raw.a")
    con.close()
    monkeypatch.setattr(B, "DB_PATH", db)
    monkeypatch.setattr(B, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(B, "LOG_PATH", tmp_path / "backup_log.jsonl")
    return db


def test_backup_is_a_verified_snapshot(warehouse):
    assert B.do_backup(retention_days=7, dry_run=False) == 0
    [bak] = list(B.BACKUP_DIR.glob("ons_*.duckdb"))
    assert B.table_counts(bak) == {"main.b": 2, "raw.a": 1000}
    con = duckdb.connect(str(bak), read_only=True)
    assert con.execute("select n from main.v").fetchone()[0] == 1000     # views come along
    assert not list(B.BACKUP_DIR.glob("*.partial"))


def test_backup_works_while_another_process_holds_it_read_only(warehouse):
    holder = duckdb.connect(str(warehouse), read_only=True)              # stands in for the API
    try:
        assert B.do_backup(retention_days=7, dry_run=False) == 0
    finally:
        holder.close()


def test_count_mismatch_fails_and_removes_the_backup(warehouse, monkeypatch):
    real = B.table_counts
    monkeypatch.setattr(B, "table_counts",
                        lambda p: real(p) if p == warehouse else {**real(p), "raw.a": 999})
    assert B.do_backup(retention_days=7, dry_run=False) == 1
    assert not list(B.BACKUP_DIR.glob("ons_*"))
    assert "row counts differ" in B.LOG_PATH.read_text()


def test_restore_to_another_path_leaves_the_live_db_alone(warehouse, tmp_path):
    B.do_backup(retention_days=7, dry_run=False)
    [bak] = list(B.BACKUP_DIR.glob("ons_*.duckdb"))
    before = warehouse.stat().st_mtime_ns
    target = tmp_path / "restore" / "ons.duckdb"
    assert B.do_restore(bak.name, dry_run=False, target=target) == 0
    assert B.table_counts(target) == {"main.b": 2, "raw.a": 1000}
    assert warehouse.stat().st_mtime_ns == before
