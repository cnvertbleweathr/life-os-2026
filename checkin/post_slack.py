"""
Post the check-in packet to a private Slack channel through an incoming webhook.

    uv run python -m checkin.post_slack --dry-run   # print the Slack message, post nothing
    uv run python -m checkin.post_slack             # post today's packet
    uv run python -m checkin.post_slack --date 2026-11-22 --force

Reads data/checkin/<date>.md (built first if missing), converts it to Slack
mrkdwn with the first line "ONS CHECK-IN — <date>", and posts it. Retries once.
Every real attempt is logged to data/checkin/packet_posts.jsonl (which
build_packet reads for "days since last check-in"). Posts at most once a day
unless --force.

The webhook URL comes from SLACK_CHECKIN_WEBHOOK_URL in .env. It is a secret:
it is never printed or logged, and error text is redacted before either.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

from api.store import timestamp, today_local
from checkin import build_packet as bp

ENV_VAR = "SLACK_CHECKIN_WEBHOOK_URL"
TIMEOUT_S = 15
RETRY_DELAY_S = 5


def header(day: date) -> str:
    return f"ONS CHECK-IN — {day.isoformat()}"


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def to_mrkdwn(markdown: str, day: date) -> str:
    """Packet Markdown → Slack mrkdwn. The H1 is replaced by the searchable header line."""
    out = [header(day)]
    for line in markdown.splitlines():
        if re.match(r"#\s", line):
            continue                                          # the packet's own title
        line = _escape(line)
        line = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"<\2|\1>", line)
        line = re.sub(r"\*\*(.+?)\*\*", r"*\1*", line)
        m = re.match(r"#{2,6}\s+(.*)", line)
        if m:
            line = f"*{m.group(1).strip()}*"
        else:
            line = re.sub(r"^(\s*)[-*] (?=\S)", lambda b: ("    ◦ " if b.group(1) else "• "), line)
        out.append(line)
    return "\n".join(out).strip() + "\n"


def redact(text: str, secret: str | None) -> str:
    if secret:
        text = text.replace(secret, "[webhook]")
    return re.sub(r"https://hooks\.slack\.com/\S+", "[webhook]", text)


@dataclass
class PostResult:
    ok: bool
    attempts: int
    status: int | None = None
    error: str | None = None


Poster = Callable[[str, dict], tuple[int, str]]


def _requests_post(url: str, payload: dict) -> tuple[int, str]:
    import requests
    r = requests.post(url, json=payload, timeout=TIMEOUT_S)
    return r.status_code, r.text[:200]


def post(text: str, url: str, *, poster: Poster = _requests_post,
         retry_delay_s: float = RETRY_DELAY_S, sleep: Callable[[float], None] = time.sleep) -> PostResult:
    """POST once, retry once on any failure. Error text never contains the URL."""
    payload = {"text": text, "mrkdwn": True, "unfurl_links": False, "unfurl_media": False}
    status: int | None = None
    error: str | None = None
    for attempt in (1, 2):
        try:
            status, body = poster(url, payload)
            if 200 <= status < 300:
                return PostResult(ok=True, attempts=attempt, status=status)
            error = f"HTTP {status}: {redact(body.strip(), url)[:120]}"
        except Exception as e:                                  # network errors, timeouts
            status = None
            error = f"{type(e).__name__}: {redact(str(e), url)[:120]}"
        if attempt == 1:
            sleep(retry_delay_s)
    return PostResult(ok=False, attempts=2, status=status, error=error)


def already_posted(day: date) -> bool:
    return any(r.get("date") == day.isoformat() and r.get("ok") for r in bp.post_log().rows())


def log_result(day: date, result: PostResult, chars: int) -> None:
    bp.post_log().append({
        "date": day.isoformat(), "posted_at": timestamp(), "ok": result.ok,
        "attempts": result.attempts, "status": result.status, "error": result.error, "chars": chars,
    })


def load_packet(day: date) -> str:
    """data/checkin/<date>.md, built and saved first if it doesn't exist."""
    path = bp.packet_dir() / f"{day.isoformat()}.md"
    if path.exists():
        return path.read_text()
    text = bp.build_packet(bp.gather(day))
    bp.save(text, day)
    return text


def run(day: date, *, dry_run: bool = False, force: bool = False,
        url: str | None = None, poster: Poster = _requests_post,
        sleep: Callable[[float], None] = time.sleep) -> int:
    """0 posted / dry run / already posted today, 1 failed or not configured."""
    message = to_mrkdwn(load_packet(day), day)
    if dry_run:
        print(message)
        print(f"[dry run: {len(message)} chars, not posted]")
        return 0
    if already_posted(day) and not force:
        print(f"already posted the {day} packet; --force to post again")
        return 0
    url = url if url is not None else os.getenv(ENV_VAR, "").strip()
    if not url:
        print(f"{ENV_VAR} isn't set in .env; not posting", file=sys.stderr)
        return 1
    result = post(message, url, poster=poster, sleep=sleep)
    log_result(day, result, len(message))
    if result.ok:
        print(f"posted the {day} check-in packet ({len(message)} chars, attempt {result.attempts})")
        return 0
    print(f"failed to post the {day} packet after {result.attempts} attempts: {result.error}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", type=date.fromisoformat, help="packet date (default today)")
    ap.add_argument("--dry-run", action="store_true", help="print the Slack message instead of posting")
    ap.add_argument("--force", action="store_true", help="post even if today's packet was already posted")
    args = ap.parse_args(argv)
    from dotenv import load_dotenv
    load_dotenv(bp.ROOT / ".env")
    return run(args.date or today_local(), dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
