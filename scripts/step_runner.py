"""
Run one daily_sync step's command so a hung step can't take the rest of the
sync down with it.

Each step runs in its own process group. On timeout:
  1. SIGABRT to the group: Python steps (PYTHONFAULTHANDLER=1) print every
     thread's stack to stderr, so the log shows where it was stuck;
  2. after `grace_s`, SIGKILL to the whole group, so no child process
     (uv → python, dlt workers, ...) survives holding the DuckDB lock.

Partial stdout/stderr are always returned. subprocess.run(timeout=) only kills
the direct child; on 2026-11-15 and 11-20 a survivor held the warehouse and
every later step failed on the lock until the sync aborted.
"""

from __future__ import annotations

import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path

GRACE_S = 10
ACTIVE: set[int] = set()            # process groups of steps running right now


def stop_active() -> None:
    """Kill every running step's process group (daily_sync's signal handler)."""
    for pgid in list(ACTIVE):
        _signal_group(pgid, signal.SIGKILL)


@dataclass
class CmdResult:
    returncode: int | None          # None if the step itself was stopped
    stdout: str
    stderr: str
    timed_out: bool = False
    killed_leftovers: bool = False  # the step exited but left processes behind


def _signal_group(pgid: int, sig: int) -> None:
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _collect(proc: subprocess.Popen, timeout: float | None) -> tuple[str, str]:
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _signal_group(proc.pid, signal.SIGKILL)
        out, err = proc.communicate()
    return out or "", err or ""


def run_cmd(cmd: list[str], *, cwd: Path | str, timeout_s: float, env: dict | None = None,
            grace_s: float = GRACE_S) -> CmdResult:
    env = dict(os.environ if env is None else env)
    env.setdefault("PYTHONFAULTHANDLER", "1")        # SIGABRT → Python prints all thread stacks
    proc = subprocess.Popen(cmd, cwd=str(cwd), env=env, text=True,
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=True)  # own process group (pgid == pid)
    ACTIVE.add(proc.pid)
    try:
        return _finish(proc, timeout_s, grace_s)
    finally:
        ACTIVE.discard(proc.pid)


def _finish(proc: subprocess.Popen, timeout_s: float, grace_s: float) -> CmdResult:
    try:
        out, err = proc.communicate(timeout=timeout_s)
        return CmdResult(proc.returncode, out or "", err or "")
    except subprocess.TimeoutExpired:
        pass

    if proc.poll() is not None:
        # The step finished, but something it started still holds its output open.
        _signal_group(proc.pid, signal.SIGKILL)
        out, err = _collect(proc, grace_s)
        return CmdResult(proc.returncode, out, err, killed_leftovers=True)

    _signal_group(proc.pid, signal.SIGABRT)
    out, err = _collect(proc, grace_s)
    _signal_group(proc.pid, signal.SIGKILL)            # anything still left in the group
    return CmdResult(None, out, err, timed_out=True)
