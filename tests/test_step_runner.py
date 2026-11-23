"""
scripts/step_runner.py: how daily_sync runs a step's command.

Real subprocesses: a hung step must be stopped together with every process it
started (on 2026-11-15 a surviving child kept the DuckDB lock and the sync
aborted), and its partial output plus a stack dump must survive.

  uv run --with pytest pytest tests/test_step_runner.py -q
"""

from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("step_runner", ROOT / "scripts" / "step_runner.py")
step_runner = importlib.util.module_from_spec(spec)
sys.modules["step_runner"] = step_runner          # dataclasses look their module up here
spec.loader.exec_module(step_runner)

PY = sys.executable


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_normal_step_returns_output_and_code(tmp_path):
    r = step_runner.run_cmd([PY, "-c", "import sys; print('hi'); print('warn', file=sys.stderr); sys.exit(3)"],
                            cwd=tmp_path, timeout_s=30)
    assert (r.returncode, r.timed_out) == (3, False)
    assert r.stdout.strip() == "hi" and r.stderr.strip() == "warn"


def test_timeout_keeps_partial_output_and_a_stack_dump(tmp_path):
    code = ("import time\n"
            "def stuck_here():\n"
            "    print('loading habits', flush=True)\n"
            "    time.sleep(60)\n"
            "stuck_here()\n")
    r = step_runner.run_cmd([PY, "-c", code], cwd=tmp_path, timeout_s=1, grace_s=3)
    assert r.timed_out and r.returncode is None
    assert "loading habits" in r.stdout
    assert "stuck_here" in r.stderr                          # faulthandler traceback


def test_timeout_kills_grandchildren_that_would_hold_the_lock(tmp_path):
    pidfile = tmp_path / "child.pid"
    code = ("import subprocess, sys, time\n"
            f"c = subprocess.Popen([{PY!r}, '-c', 'import time; time.sleep(60)'])\n"
            f"open({str(pidfile)!r}, 'w').write(str(c.pid))\n"
            "time.sleep(60)\n")
    r = step_runner.run_cmd([PY, "-c", code], cwd=tmp_path, timeout_s=2, grace_s=1)
    assert r.timed_out
    child = int(pidfile.read_text())
    for _ in range(20):
        if not alive(child):
            break
        time.sleep(0.1)
    assert not alive(child)


def test_stop_active_kills_the_running_step(tmp_path):
    # daily_sync calls this when it is itself stopped (SIGTERM), so the step
    # doesn't keep holding the warehouse after the API is restarted.
    import threading
    out = {}
    t = threading.Thread(target=lambda: out.setdefault(
        "r", step_runner.run_cmd([PY, "-c", "import time; time.sleep(60)"], cwd=tmp_path, timeout_s=60)))
    t.start()
    for _ in range(50):
        if step_runner.ACTIVE:
            break
        time.sleep(0.1)
    assert step_runner.ACTIVE
    step_runner.stop_active()
    t.join(timeout=10)
    assert not t.is_alive() and not step_runner.ACTIVE


def test_a_child_left_running_after_a_normal_exit_is_not_waited_on_forever(tmp_path):
    # A step that exits but leaves a background child holding stdout open must not hang the sync.
    code = ("import subprocess, sys\n"
            f"subprocess.Popen([{PY!r}, '-c', 'import time; time.sleep(60)'])\n"
            "print('done')\n")
    start = time.monotonic()
    r = step_runner.run_cmd([PY, "-c", code], cwd=tmp_path, timeout_s=3, grace_s=1)
    assert time.monotonic() - start < 10
    assert "done" in r.stdout
