#!/usr/bin/env python3
"""
backup_duckdb.py — Nightly DuckDB backup for ONS.

Snapshots ons.duckdb to a timestamped backup file with DuckDB itself
(ATTACH the warehouse READ_ONLY, COPY FROM DATABASE into a new file): one
transaction, so the backup is consistent even while the API holds the
warehouse open read-only. Never a raw file copy, which can catch a file
mid-write. The backup is verified by per-table row counts against the source,
then old backups beyond the retention window are pruned.

Backup location: data/backups/duckdb/
Filename format: ons_YYYY-MM-DD_HHMMSS.duckdb

Usage:
  python scripts/backup_duckdb.py                  # run backup
  python scripts/backup_duckdb.py --retention 14   # keep 14 days (default: 7)
  python scripts/backup_duckdb.py --dry-run        # show what would happen
  python scripts/backup_duckdb.py --restore <file> # restore from a backup
  python scripts/backup_duckdb.py --restore <file> --target /tmp/x.duckdb  # test restore

Exit codes:
  0 — success
  1 — backup failed (source missing, copy failed, or verification failed)
  2 — restore failed
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT       = Path(__file__).resolve().parents[1]
DB_PATH    = ROOT / "data" / "warehouse" / "ons.duckdb"
BACKUP_DIR = ROOT / "data" / "backups" / "duckdb"
LOG_PATH   = ROOT / "data" / "backups" / "backup_log.jsonl"


# ── Helpers ───────────────────────────────────────────────────────────────────

def log(entry: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def verify_readable(path: Path) -> tuple[bool, str]:
    """
    Open the DuckDB file read-only and run a trivial query.
    Returns (ok, message).
    """
    try:
        import duckdb
        con = duckdb.connect(str(path), read_only=True)
        result = con.execute("SELECT count(*) FROM information_schema.tables").fetchone()
        con.close()
        table_count = result[0] if result else 0
        return True, f"{table_count} tables readable"
    except Exception as e:
        return False, str(e)


def _sql_path(path: Path) -> str:
    return str(path).replace("'", "''")


def snapshot_copy(src: Path, dest: Path) -> None:
    """Consistent copy of `src` into a new database file `dest`, in one transaction.

    Writes `<dest>.partial` and renames it when complete, so a crash never
    leaves a half-written file that looks like a backup."""
    import duckdb
    tmp = dest.with_name(dest.name + ".partial")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(":memory:")
    try:
        con.execute(f"ATTACH '{_sql_path(src)}' AS src (READ_ONLY)")
        con.execute(f"ATTACH '{_sql_path(tmp)}' AS bak")
        con.execute("COPY FROM DATABASE src TO bak")
        con.execute("DETACH bak")
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    finally:
        con.close()
    tmp.rename(dest)


def table_counts(path: Path) -> dict[str, int]:
    """{schema.table: row count} for every base table, read-only."""
    import duckdb
    con = duckdb.connect(str(path), read_only=True)
    try:
        tables = con.execute(
            "select table_schema, table_name from information_schema.tables "
            "where table_type = 'BASE TABLE' order by 1, 2").fetchall()
        return {f"{s}.{t}": con.execute(f'select count(*) from "{s}"."{t}"').fetchone()[0]
                for s, t in tables}
    finally:
        con.close()


def human_size(path: Path) -> str:
    b = path.stat().st_size
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


# ── Backup ────────────────────────────────────────────────────────────────────

def do_backup(retention_days: int, dry_run: bool) -> int:
    started = datetime.now()
    ts      = started.strftime("%Y-%m-%d_%H%M%S")

    print(f"ONS DuckDB Backup — {started.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Source:    {DB_PATH}")
    print(f"  Retention: {retention_days} days")
    print()

    # ── Source exists? ────────────────────────────────────────────────────────
    if not DB_PATH.exists():
        msg = f"Source database not found: {DB_PATH}"
        print(f"❌ {msg}")
        log({"ts": ts, "status": "failed", "reason": msg})
        return 1

    src_size = human_size(DB_PATH)
    print(f"  Source size: {src_size}")

    # ── Verify source is readable before copying ──────────────────────────────
    print("  Verifying source is readable...")
    ok, detail = verify_readable(DB_PATH)
    if not ok:
        msg = f"Source database is not readable: {detail}"
        print(f"❌ {msg}")
        log({"ts": ts, "status": "failed", "reason": msg})
        return 1
    print(f"  ✅ Source OK — {detail}")

    # ── Copy ─────────────────────────────────────────────────────────────────
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dest = BACKUP_DIR / f"ons_{ts}.duckdb"

    if dry_run:
        print(f"\n  [dry-run] Would copy → {dest}")
        print(f"  [dry-run] Would verify backup is readable")
        print(f"  [dry-run] Would prune backups older than {retention_days} days")
        return 0

    print(f"\n  Snapshotting to {dest.name} (COPY FROM DATABASE)...")
    try:
        snapshot_copy(DB_PATH, dest)
    except Exception as e:
        msg = f"Snapshot failed: {e}"
        print(f"❌ {msg}")
        log({"ts": ts, "status": "failed", "reason": msg})
        return 1

    dest_size = human_size(dest)
    print(f"  ✅ Copy complete — {dest_size}")

    # ── Verify backup ────────────────────────────────────────────────────────
    print("  Verifying row counts against the source...")
    try:
        src_counts, bak_counts = table_counts(DB_PATH), table_counts(dest)
    except Exception as e:
        src_counts, bak_counts = {"error": str(e)}, {}
    if src_counts != bak_counts:
        diff = sorted(k for k in set(src_counts) | set(bak_counts) if src_counts.get(k) != bak_counts.get(k))
        msg = f"Backup verification failed: row counts differ for {len(diff)} table(s): {diff[:5]}"
        print(f"❌ {msg}")
        dest.unlink(missing_ok=True)            # never keep a backup that doesn't match
        log({"ts": ts, "status": "failed", "reason": msg})
        return 1
    detail = f"{len(bak_counts)} tables, {sum(bak_counts.values())} rows match the source"
    print(f"  ✅ Backup verified — {detail}")

    duration = (datetime.now() - started).total_seconds()

    # ── Prune old backups ────────────────────────────────────────────────────
    cutoff  = datetime.now() - timedelta(days=retention_days)
    backups = sorted(BACKUP_DIR.glob("ons_*.duckdb"))
    pruned  = []

    for old in backups:
        if old == dest:
            continue
        try:
            # Parse timestamp from filename: ons_YYYY-MM-DD_HHMMSS.duckdb
            stem  = old.stem  # ons_2026-01-01_120000
            parts = stem.split("_", 1)
            if len(parts) < 2:
                continue
            file_ts = datetime.strptime(parts[1], "%Y-%m-%d_%H%M%S")
            if file_ts < cutoff:
                old.unlink()
                pruned.append(old.name)
        except Exception:
            continue

    remaining = len(list(BACKUP_DIR.glob("ons_*.duckdb")))

    print()
    print(f"  Pruned {len(pruned)} old backup(s) — {remaining} remaining")
    if pruned:
        for name in pruned:
            print(f"    - {name}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print(f"✅ Backup complete in {duration:.1f}s")
    print(f"   {dest}")

    log({
        "ts":          ts,
        "status":      "ok",
        "source_size": DB_PATH.stat().st_size,
        "backup_file": dest.name,
        "tables":      detail,
        "duration_s":  round(duration, 2),
        "pruned":      pruned,
        "remaining":   remaining,
    })

    return 0


# ── Restore ───────────────────────────────────────────────────────────────────

def do_restore(backup_name: str, dry_run: bool, target: Path | None = None) -> int:
    target = Path(target) if target else DB_PATH
    # Accept either a filename or a full path
    backup_path = Path(backup_name)
    if not backup_path.is_absolute():
        backup_path = BACKUP_DIR / backup_name
    if not backup_path.suffix:
        backup_path = backup_path.with_suffix(".duckdb")

    print(f"ONS DuckDB Restore")
    print(f"  Backup: {backup_path}")
    print(f"  Target: {target}")
    print()

    if not backup_path.exists():
        # Try glob
        matches = list(BACKUP_DIR.glob(f"*{backup_name}*"))
        if not matches:
            print(f"❌ Backup not found: {backup_path}")
            print(f"   Available backups:")
            for b in sorted(BACKUP_DIR.glob("ons_*.duckdb"))[-5:]:
                print(f"     {b.name}  ({human_size(b)})")
            return 2
        backup_path = sorted(matches)[-1]
        print(f"  Resolved to: {backup_path.name}")

    # Verify backup before overwriting live DB
    print("  Verifying backup is readable...")
    ok, detail = verify_readable(backup_path)
    if not ok:
        print(f"❌ Backup is not readable: {detail}")
        return 2
    print(f"  ✅ Backup OK — {detail}")

    if dry_run:
        print(f"\n  [dry-run] Would overwrite {target} with {backup_path.name}")
        return 0

    # Safety: copy the current target to .bak before overwriting.
    # (Stop the API and any sync first when the target is the live warehouse.)
    if target.exists():
        bak = target.with_suffix(".duckdb.bak")
        shutil.copy2(str(target), str(bak))
        print(f"  Saved current DB as {bak.name} (safety copy)")

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(backup_path), str(target))     # a backup is a closed, finished file

    counts = table_counts(target)
    if counts != table_counts(backup_path):
        print("❌ Restored DB doesn't match the backup's row counts")
        return 2
    detail = f"{len(counts)} tables, {sum(counts.values())} rows"

    print()
    print(f"✅ Restored successfully to {target} — {detail}")
    log({
        "ts":           datetime.now().strftime("%Y-%m-%d_%H%M%S"),
        "status":       "restored",
        "from_backup":  backup_path.name,
        "target":       str(target),
    })
    return 0


# ── List ──────────────────────────────────────────────────────────────────────

def do_list() -> int:
    backups = sorted(BACKUP_DIR.glob("ons_*.duckdb"), reverse=True)
    if not backups:
        print("No backups found in", BACKUP_DIR)
        return 0
    print(f"{'Backup':<35} {'Size':>8}  {'Age'}")
    print("-" * 60)
    now = datetime.now()
    for b in backups:
        try:
            stem = b.stem
            ts   = datetime.strptime(stem.split("_", 1)[1], "%Y-%m-%d_%H%M%S")
            age  = now - ts
            days = age.days
            age_str = f"{days}d ago" if days > 0 else "today"
        except Exception:
            age_str = "unknown"
        print(f"  {b.name:<33} {human_size(b):>8}  {age_str}")
    return 0


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description="ONS DuckDB backup utility")
    p.add_argument("--retention", type=int, default=7,
                   help="Days of backups to keep (default: 7)")
    p.add_argument("--dry-run",  action="store_true",
                   help="Show what would happen without doing it")
    p.add_argument("--restore",  type=str, default=None,
                   help="Restore from a named backup file")
    p.add_argument("--target",   type=Path, default=None,
                   help="Restore into this path instead of the live warehouse (test restores)")
    p.add_argument("--list",     action="store_true",
                   help="List available backups")
    args = p.parse_args()

    if args.list:
        return do_list()
    if args.restore:
        return do_restore(args.restore, args.dry_run, args.target)
    return do_backup(args.retention, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
