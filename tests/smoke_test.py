#!/usr/bin/env python3
"""
tests/smoke_test.py — ONS critical workflow smoke tests.

Fast sanity checks that catch broken environments, missing files,
and import errors before the daily sync runs. Not unit tests —
these validate that the system is in a runnable state.

Usage:
  python tests/smoke_test.py
  python tests/smoke_test.py --only cfb
  python tests/smoke_test.py --only sync metrics

Exit codes:
  0 — all smoke tests passed
  1 — one or more smoke tests failed
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

PASS  = "✅"
FAIL  = "❌"
SKIP  = "⏭"
WARN  = "⚠️"

results: list[dict] = []


def load_module(name: str, path: Path):
    """
    Load a module by file path for smoke testing.

    Registers the module in sys.modules before exec_module() runs —
    required for dataclasses and other constructs that rely on the
    module being resolvable via sys.modules during class/type processing.
    Without this, dataclass field resolution can fail with obscure
    'NoneType has no attribute __dict__' errors.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def check(name: str, group: str = ""):
    """Decorator — wraps a check function and records pass/fail."""
    def decorator(fn):
        def wrapper():
            try:
                msg = fn()
                results.append({"name": name, "group": group, "status": "pass", "msg": msg or ""})
                print(f"  {PASS}  {name}" + (f" — {msg}" if msg else ""))
            except AssertionError as e:
                results.append({"name": name, "group": group, "status": "fail", "msg": str(e)})
                print(f"  {FAIL}  {name} — {e}")
            except Exception as e:
                results.append({"name": name, "group": group, "status": "fail", "msg": repr(e)})
                print(f"  {FAIL}  {name} — {repr(e)}")
        return wrapper
    return decorator


# ── Group: environment ────────────────────────────────────────────────────────

@check("DuckDB warehouse exists", "env")
def check_duckdb():
    p = ROOT / "data" / "warehouse" / "ons.duckdb"
    assert p.exists(), f"Missing: {p}"
    size_mb = p.stat().st_size / 1_048_576
    assert size_mb > 0.1, f"Suspiciously small: {size_mb:.1f}MB"
    return f"{size_mb:.0f}MB"


@check("DuckDB is readable", "env")
def check_duckdb_readable():
    import duckdb
    db = duckdb.connect(str(ROOT / "data" / "warehouse" / "ons.duckdb"), read_only=True)
    rows = db.execute("SELECT count(*) FROM information_schema.tables").fetchone()
    db.close()
    assert rows and rows[0] > 0, "No tables found in warehouse"
    return f"{rows[0]} tables"


@check("Goals YAML exists", "env")
def check_goals_yaml():
    year = date.today().year
    p    = ROOT / "goals" / f"{year}.yaml"
    assert p.exists(), f"Missing: {p} — create goals/{year}.yaml"
    return str(p.name)


@check(".env or environment variables present", "env")
def check_env():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    import os
    keys = ["CFBD_API_TOKEN", "SPOTIFY_CLIENT_ID", "HARDCOVER_TOKEN", "STRAVA_CLIENT_ID"]
    missing = [k for k in keys if not os.getenv(k)]
    if missing:
        raise AssertionError(f"Missing env vars: {', '.join(missing)}")
    return f"{len(keys)} keys found"


@check("Backup directory writable", "env")
def check_backup_dir():
    bdir = ROOT / "data" / "backups" / "duckdb"
    bdir.mkdir(parents=True, exist_ok=True)
    test = bdir / ".smoke_write_test"
    test.write_text("ok")
    test.unlink()
    return str(bdir)


# ── Group: sync ───────────────────────────────────────────────────────────────

@check("daily_sync.py imports cleanly", "sync")
def check_sync_import():
    mod = load_module("daily_sync", ROOT / "scripts" / "daily_sync.py")
    assert hasattr(mod, "build_steps"), "build_steps() not found"
    assert hasattr(mod, "run_step"), "run_step() not found"
    return "ok"


@check("daily_sync build_steps() returns steps", "sync")
def check_sync_steps():
    mod = load_module("daily_sync", ROOT / "scripts" / "daily_sync.py")
    steps = mod.build_steps(date.today().year)
    assert len(steps) > 5, f"Only {len(steps)} steps — expected more"
    required = [s for s in steps if s.required]
    assert required, "No required steps found"
    return f"{len(steps)} steps, {len(required)} required"


@check("backup_duckdb.py imports cleanly", "sync")
def check_backup_import():
    p = ROOT / "scripts" / "backup_duckdb.py"
    assert p.exists(), "backup_duckdb.py not found"
    spec = importlib.util.spec_from_file_location("backup_duckdb", p)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "do_backup"), "do_backup() not found"
    return "ok"


@check("Last sync health summary exists", "sync")
def check_last_health():
    today     = date.today().isoformat()
    yesterday = (date.today().replace(day=date.today().day - 1)).isoformat()
    for d in [today, yesterday]:
        h = ROOT / "data" / "daily" / d / "health.txt"
        if h.exists():
            txt = h.read_text()
            assert "ok" in txt.lower() or "failed" in txt.lower(), "health.txt looks malformed"
            lines = txt.splitlines()
            return f"{d}: {lines[0] if lines else 'found'}"
    # Not a failure — just warn
    results[-1]["status"] = "warn"
    print(f"      {WARN}  No recent health.txt — run daily_sync.py first")
    return "no recent health found"


# ── Group: cfb ────────────────────────────────────────────────────────────────

@check("backtest_walk_forward.py imports cleanly", "cfb")
def check_wf_import():
    p = ROOT / "scripts" / "backtest_walk_forward.py"
    assert p.exists(), "backtest_walk_forward.py not found"
    mod = load_module("bwf", p)
    assert hasattr(mod, "score_game"), "score_game() not found"
    assert hasattr(mod, "safe_float"), "safe_float() not found"
    return "score_game() available"


@check("generate_picks.py imports score_game from walk-forward", "cfb")
def check_picks_import():
    p = ROOT / "scripts" / "generate_picks.py"
    assert p.exists(), "generate_picks.py not found"
    txt = p.read_text()
    assert "from backtest_walk_forward import score_game" in txt, \
        "generate_picks.py does not import score_game() from walk-forward — MODEL DIVERGENCE"
    return "unified scorer confirmed"


@check("todays_picks.json schema valid (if exists)", "cfb")
def check_picks_schema():
    p = ROOT / "data" / "bets" / "todays_picks.json"
    if not p.exists():
        results[-1]["status"] = "warn"
        return "no picks file — off-season or not yet generated"
    picks = json.loads(p.read_text())
    if not picks:
        return "empty picks file"
    required_keys = {"matchup", "bet", "model_score", "edge", "n_edges"}
    for pick in picks:
        missing = required_keys - set(pick.keys())
        assert not missing, f"Pick missing keys: {missing}"
        assert "confidence" not in pick, \
            "Old 'confidence' field found — should be 'model_score'"
        assert pick.get("model_score", 0) >= 70, \
            f"Pick with model_score < 70 in output: {pick['matchup']}"
    return f"{len(picks)} picks, all valid"


@check("No SP+ or havoc signals in picks output", "cfb")
def check_disabled_signals():
    p = ROOT / "data" / "bets" / "todays_picks.json"
    if not p.exists():
        results[-1]["status"] = "warn"
        return "no picks file"
    picks = json.loads(p.read_text())
    for pick in picks:
        edge = pick.get("edge", "")
        assert "SP+" not in edge, f"Disabled SP+ signal in pick: {pick['matchup']}"
        assert "havoc" not in edge.lower(), f"Disabled havoc signal in pick: {pick['matchup']}"
    return f"{len(picks)} picks clean"


@check("generate_picks_report.py imports cleanly", "cfb")
def check_report_import():
    p = ROOT / "scripts" / "generate_picks_report.py"
    assert p.exists(), "generate_picks_report.py not found"
    mod = load_module("gpr", p)
    assert hasattr(mod, "generate_report"), "generate_report() not found"
    return "ok"


# ── Group: metrics ────────────────────────────────────────────────────────────

@check("Key mart tables exist in DuckDB", "metrics")
def check_mart_tables():
    import duckdb
    db = duckdb.connect(str(ROOT / "data" / "warehouse" / "ons.duckdb"), read_only=True)
    expected = [
        "main_marts.mart_cfbd_game_context",
        "main_marts.mart_cfbd_line_accuracy",
        "main_marts.mart_goal_progress",
    ]
    missing = []
    for tbl in expected:
        schema, name = tbl.split(".")
        rows = db.execute(f"""
            SELECT count(*) FROM information_schema.tables
            WHERE table_schema = '{schema}' AND table_name = '{name}'
        """).fetchone()
        if not rows or rows[0] == 0:
            missing.append(tbl)
    db.close()
    if missing:
        raise AssertionError(f"Missing mart tables: {missing}")
    return f"{len(expected)} marts present"


@check("Strava activities table has data", "metrics")
def check_strava_data():
    import duckdb
    db   = duckdb.connect(str(ROOT / "data" / "warehouse" / "ons.duckdb"), read_only=True)
    rows = db.execute("SELECT count(*) FROM strava.activities").fetchone()
    db.close()
    assert rows and rows[0] > 0, "strava.activities is empty"
    return f"{rows[0]} activities"


@check("CFBD line accuracy mart has data", "metrics")
def check_cfbd_data():
    import duckdb
    db   = duckdb.connect(str(ROOT / "data" / "warehouse" / "ons.duckdb"), read_only=True)
    rows = db.execute("SELECT count(*) FROM main_marts.mart_cfbd_line_accuracy").fetchone()
    db.close()
    assert rows and rows[0] > 0, "mart_cfbd_line_accuracy is empty — run dbt"
    return f"{rows[0]} games"


@check("spotify_metrics output CSV exists for current year", "metrics")
def check_spotify_metrics():
    year = date.today().year
    p    = ROOT / "data" / "spotify" / "metrics" / f"spotify_summary_{year}.csv"
    if not p.exists():
        results[-1]["status"] = "warn"
        return f"no spotify_summary_{year}.csv — run spotify_metrics.py"
    import csv
    rows = list(csv.DictReader(p.open()))
    assert rows, "spotify metrics CSV is empty"
    return f"{len(rows)} rows"


# ── Runner ────────────────────────────────────────────────────────────────────

ALL_CHECKS = [
    check_duckdb, check_duckdb_readable, check_goals_yaml,
    check_env, check_backup_dir,
    check_sync_import, check_sync_steps, check_backup_import, check_last_health,
    check_wf_import, check_picks_import, check_picks_schema,
    check_disabled_signals, check_report_import,
    check_mart_tables, check_strava_data, check_cfbd_data, check_spotify_metrics,
]

GROUP_MAP = {
    "env":     [check_duckdb, check_duckdb_readable, check_goals_yaml, check_env, check_backup_dir],
    "sync":    [check_sync_import, check_sync_steps, check_backup_import, check_last_health],
    "cfb":     [check_wf_import, check_picks_import, check_picks_schema, check_disabled_signals, check_report_import],
    "metrics": [check_mart_tables, check_strava_data, check_cfbd_data, check_spotify_metrics],
}


def main() -> int:
    p = argparse.ArgumentParser(description="ONS smoke tests")
    p.add_argument("--only", nargs="+", metavar="GROUP",
                   help=f"Run only these groups: {list(GROUP_MAP.keys())}")
    args = p.parse_args()

    if args.only:
        checks = []
        for g in args.only:
            assert g in GROUP_MAP, f"Unknown group '{g}'. Valid: {list(GROUP_MAP.keys())}"
            checks.extend(GROUP_MAP[g])
    else:
        checks = ALL_CHECKS

    groups_to_run = sorted({
        next(r["group"] for r in [{"group": g}
                                   for g, cs in GROUP_MAP.items()
                                   if c in cs])
        for c in checks
        for g, cs in GROUP_MAP.items()
        if c in cs
    })

    print(f"\nONS Smoke Tests — {date.today()}")
    print(f"Running {len(checks)} checks across: {', '.join(groups_to_run)}\n")

    for g in groups_to_run:
        print(f"── {g.upper()} ──")
        for c in checks:
            for grp, cs in GROUP_MAP.items():
                if c in cs and grp == g:
                    c()
        print()

    passed  = sum(1 for r in results if r["status"] == "pass")
    warned  = sum(1 for r in results if r["status"] == "warn")
    failed  = sum(1 for r in results if r["status"] == "fail")

    print(f"{'='*50}")
    print(f"  {PASS} {passed:2d} passed   {WARN} {warned:2d} warned   {FAIL} {failed:2d} failed")
    print(f"{'='*50}\n")

    if failed:
        print("Failed checks:")
        for r in results:
            if r["status"] == "fail":
                print(f"  {FAIL}  {r['name']}: {r['msg']}")
        print()

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
