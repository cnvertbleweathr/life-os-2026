#!/usr/bin/env python3
"""
scripts/notify.py — ONS push notifications via ntfy.sh.

Sends push notifications to your phone for:
  - Thursday picks report (weekly)
  - Daily sync failures
  - Backup failures
  - Morning digest (optional)

ntfy.sh is free, open-source, and requires no account for self-hosted.
For the hosted version (ntfy.sh), pick a unique topic name.

Setup:
  1. Install ntfy on your phone: https://ntfy.sh
  2. Subscribe to your topic: e.g. "ons-karey-2026" (make it unique)
  3. Set NTFY_TOPIC in .env
  4. Optionally set NTFY_SERVER if self-hosting (default: https://ntfy.sh)

Usage:
  python scripts/notify.py picks          # send picks report
  python scripts/notify.py sync-ok        # send sync health summary
  python scripts/notify.py sync-fail      # send sync failure alert
  python scripts/notify.py test           # send a test notification

Called automatically:
  - generate_picks_report.py calls: python scripts/notify.py picks
  - daily_sync.py can call:         python scripts/notify.py sync-ok/sync-fail
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_env():
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


_load_env()

NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
NTFY_TOPIC  = os.getenv("NTFY_TOPIC", "")


def send(
    title:    str,
    message:  str,
    priority: str = "default",  # min, low, default, high, urgent
    tags:     list[str] | None = None,
    topic:    str | None = None,
) -> bool:
    """
    Send a push notification via ntfy.sh.
    Returns True on success, False on failure (never raises).
    """
    t = topic or NTFY_TOPIC
    if not t:
        print("⚠️  NTFY_TOPIC not set — notification skipped. Add to .env")
        return False

    url  = f"{NTFY_SERVER}/{t}"
    data = {
        "title":    title,
        "message":  message,
        "priority": priority,
    }
    if tags:
        data["tags"] = tags

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            ok = r.status == 200
            if not ok:
                print(f"ntfy returned {r.status}")
            return ok
    except Exception as e:
        print(f"Notification failed: {e}")
        return False


# ── Notification builders ─────────────────────────────────────────────────────

def notify_picks() -> bool:
    """Send Thursday picks briefing."""
    picks_path = ROOT / "data" / "bets" / "todays_picks.json"
    if not picks_path.exists():
        return send(
            title="🏈 Degenerates Corner",
            message="No qualifying picks this week — edges don't meet criteria.",
            priority="low",
            tags=["football"],
        )

    try:
        picks = json.loads(picks_path.read_text())
    except Exception:
        picks = []

    if not picks:
        return send(
            title="🏈 Degenerates Corner",
            message="No qualifying picks this week.",
            priority="low",
            tags=["football"],
        )

    week    = picks[0].get("week", "?")
    n       = len(picks)
    top     = picks[0]  # already sorted by model_score desc
    score   = top.get("model_score", 0)
    matchup = top.get("matchup", "")
    bet     = top.get("bet", "")

    lines = [
        f"📊 {n} qualifying picks for Week {week}",
        f"",
        f"Top pick: {matchup}",
        f"Bet: {bet}",
        f"Score: {score}/100 · {top.get('n_edges', 0)} signals",
    ]

    if n > 1:
        lines.append(f"")
        lines.append(f"+ {n - 1} more pick{'s' if n > 2 else ''}")

    # Include warnings if top pick has any
    warnings = top.get("warnings") or []
    if warnings:
        lines.append(f"⚠️  {warnings[0]}")

    return send(
        title=f"🏈 Degenerates Corner · Week {week}",
        message="\n".join(lines),
        priority="high",
        tags=["football", "money_with_wings"],
    )


def notify_sync_ok() -> bool:
    """Send daily sync success summary."""
    today      = date.today().isoformat()
    health_path = ROOT / "data" / "daily" / today / "health.txt"

    if not health_path.exists():
        return send(
            title="✅ ONS Daily Sync",
            message=f"Sync completed — {today}",
            priority="low",
            tags=["white_check_mark"],
        )

    txt   = health_path.read_text()
    lines = txt.splitlines()
    # Extract counts from health.txt
    summary_lines = [l for l in lines[:8] if l.strip()]
    message = "\n".join(summary_lines[:6])

    return send(
        title="✅ ONS Daily Sync",
        message=message or f"Sync completed — {today}",
        priority="low",
        tags=["white_check_mark"],
    )


def notify_sync_fail(failed_step: str = "", error: str = "") -> bool:
    """Send daily sync failure alert."""
    today   = date.today().isoformat()
    message = f"Sync failed on {today}"
    if failed_step:
        message += f"\nStep: {failed_step}"
    if error:
        # Truncate long errors
        message += f"\n{error[:200]}"

    return send(
        title="❌ ONS Sync Failed",
        message=message,
        priority="urgent",
        tags=["rotating_light", "x"],
    )


def notify_backup_fail(error: str = "") -> bool:
    """Send DuckDB backup failure alert."""
    return send(
        title="❌ ONS Backup Failed",
        message=f"DuckDB backup failed — {date.today()}\n{error[:200]}",
        priority="urgent",
        tags=["rotating_light", "floppy_disk"],
    )


def notify_test() -> bool:
    """Send a test notification to verify setup."""
    return send(
        title="🧪 ONS Test",
        message=f"Notifications working — {date.today()}",
        priority="default",
        tags=["test_tube"],
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

COMMANDS = {
    "picks":       notify_picks,
    "sync-ok":     notify_sync_ok,
    "sync-fail":   notify_sync_fail,
    "backup-fail": notify_backup_fail,
    "test":        notify_test,
}


def main() -> int:
    p = argparse.ArgumentParser(description="ONS push notifications via ntfy.sh")
    p.add_argument("command", choices=list(COMMANDS.keys()),
                   help="Notification to send")
    p.add_argument("--topic", default=None,
                   help="Override NTFY_TOPIC from .env")
    p.add_argument("--step",  default="", help="Failed step name (for sync-fail)")
    p.add_argument("--error", default="", help="Error message (for sync-fail)")
    args = p.parse_args()

    if args.topic:
        global NTFY_TOPIC
        NTFY_TOPIC = args.topic

    if not NTFY_TOPIC:
        print("❌ NTFY_TOPIC not set.")
        print("   Add to .env:  NTFY_TOPIC=ons-yourname-2026")
        print("   Then install ntfy on your phone: https://ntfy.sh")
        return 1

    print(f"Sending {args.command!r} → {NTFY_SERVER}/{NTFY_TOPIC}")

    fn = COMMANDS[args.command]
    if args.command == "sync-fail":
        ok = notify_sync_fail(args.step, args.error)
    else:
        ok = fn()

    if ok:
        print("✅ Sent")
        return 0
    else:
        print("❌ Failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
