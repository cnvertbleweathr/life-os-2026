"""
Read check-in RECAPs posted in Slack, in the check-in channel or a packet's thread (voice-mode Claude
posts its RECAP there), and queue them for ingest_recap, the same as a website paste.

The packet itself is posted with an incoming webhook, which can't read anything. Reading needs a
Slack app's bot token, in .env (secrets; never commit):

  SLACK_BOT_TOKEN=xoxb-…            scopes: groups:history (private channel) or channels:history
  SLACK_CHECKIN_CHANNEL_ID=C…       the channel the packet posts to; invite the app to it

Without them this step says "not configured" and exits 0, so the website paste still works.

Each run looks back LOOKBACK_DAYS at the channel's messages and every thread under them, finds
messages containing a RECAP block (a line starting with "RECAP"; Slack bold, bullets and code fences
are fine), and queues each message once: data/checkin/recaps.jsonl, source "slack",
source_id "slack:<channel>:<ts>". The sync's ingest_recap step then applies it.

  python -m checkin.slack_recaps                # the sync step (runs before ingest_recap)
  python -m checkin.slack_recaps --dry-run      # list the RECAPs it would queue
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from checkin import ingest_recap as IR  # noqa: E402

API = "https://slack.com/api/"
LOOKBACK_DAYS = 14
RECAP_LINE = re.compile(r"^[\s>*_`•-]*RECAP\b", re.I | re.M)

Call = Callable[[str, dict[str, Any]], dict[str, Any]]


def _http(token: str) -> Call:
    import requests

    def call(method: str, params: dict[str, Any]) -> dict[str, Any]:
        r = requests.get(API + method, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=20)
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack {method}: {data.get('error')}")
        return data
    return call


def _pages(call: Call, method: str, params: dict[str, Any]) -> list[dict]:
    out, cursor = [], None
    for _ in range(20):                                   # bounded: 20 pages × 200 messages
        data = call(method, {**params, "limit": 200, **({"cursor": cursor} if cursor else {})})
        out += data.get("messages", [])
        cursor = (data.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            break
    return out


def messages(call: Call, channel: str, oldest: float) -> list[dict]:
    """Top-level messages since `oldest`, plus every reply in their threads."""
    top = _pages(call, "conversations.history", {"channel": channel, "oldest": f"{oldest:.6f}"})
    out = list(top)
    for m in top:
        if m.get("reply_count"):
            replies = _pages(call, "conversations.replies", {"channel": channel, "ts": m["ts"]})
            out += [r for r in replies if r.get("ts") != m.get("ts")]
    return out


def recap_text(slack_text: str) -> str | None:
    """The RECAP block inside a Slack message (from its RECAP line to the end), in plain text."""
    text = html.unescape(slack_text or "")
    m = RECAP_LINE.search(text)
    if not m:
        return None
    block = text[m.start():]
    block = re.sub(r"<(https?://[^|>]+)\|([^>]+)>", r"\2", block)       # Slack links → their label
    block = re.sub(r"^\s*>\s?", "", block, flags=re.M)                   # quote markers
    return block.strip()


def collect(call: Call, channel: str, now: float | None = None) -> dict[str, Any]:
    """Queue every RECAP in the channel (and its threads) not queued before. Returns a summary."""
    now = now or time.time()
    seen = IR.queued_source_ids()
    out: dict[str, Any] = {"queued": [], "skipped": [], "invalid": []}
    for m in messages(call, channel, now - LOOKBACK_DAYS * 86400):
        text = recap_text(m.get("text", ""))
        if not text:
            continue
        sid = f"slack:{channel}:{m['ts']}"
        if sid in seen:
            out["skipped"].append(sid)
            continue
        try:
            row = IR.submit(text, source="slack", source_id=sid)
        except ValueError as e:
            out["invalid"].append(f"{sid}: {e}")
            continue
        seen.add(sid)
        out["queued"].append({"source_id": sid, "recap_date": row["recap_date"]})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="list RECAPs found; queue nothing")
    args = ap.parse_args(argv)
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
    except ImportError:
        pass
    token, channel = os.getenv("SLACK_BOT_TOKEN"), os.getenv("SLACK_CHECKIN_CHANNEL_ID")
    if not token or not channel:
        print("Slack RECAPs: not configured (set SLACK_BOT_TOKEN and SLACK_CHECKIN_CHANNEL_ID in .env); "
              "website pastes still work")
        return 0
    call = _http(token)
    try:
        if args.dry_run:
            found = [(m["ts"], recap_text(m.get("text", ""))) for m in messages(call, channel, time.time() - LOOKBACK_DAYS * 86400)]
            found = [(ts, t) for ts, t in found if t]
            print(f"{len(found)} RECAP message(s) in the last {LOOKBACK_DAYS} days")
            for ts, t in found:
                print(f"  {ts}: {t.splitlines()[0]}")
            return 0
        res = collect(call, channel)
    except Exception as e:                               # token revoked, app not in the channel, network
        print(f"✗ Slack RECAPs not read: {e}", file=sys.stderr)
        return 1
    print(f"Slack RECAPs: {len(res['queued'])} queued, {len(res['skipped'])} already queued, "
          f"{len(res['invalid'])} not valid RECAPs")
    for q in res["queued"]:
        print(f"  queued RECAP {q['recap_date']} ({q['source_id']})")
    for i in res["invalid"]:
        print(f"  ! {i}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
