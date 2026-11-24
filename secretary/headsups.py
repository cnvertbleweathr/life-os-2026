"""
Secretary step 4: the heads-up engine → secretary.headsups.

Each event in dbt's int_events_tiered gets the milestones of its rhythm
(secretary/config.py: the template's own, else the tier's). A milestone is due
from `days_before` days ahead until the event. One row per (event, milestone):

  headsup_id   <event_key>@<days_before>
  status       open · done · dismissed (you) · superseded · expired · gone (the sync)
  shown_count  days it has been shown; last_shown_on = the latest

`refresh(today)` runs once in the daily sync, after dbt, while the API is stopped
(DuckDB has one writer). It is idempotent: a second run the same day changes nothing.
  1. apply done/dismiss clicks from data/secretary/headsup_actions.jsonl. The website
     can't write to DuckDB (read-only connection), so it appends there, like habits.
  2. add the current milestone of each upcoming event; refresh text and tier of open ones.
     Only the latest due milestone counts: a newer one supersedes the older, and after
     a missed sync (or on first install) old milestones aren't replayed.
  3. expire open heads-ups whose day has passed; mark ones whose event vanished "gone".
  4. pick today's heads-ups and count the showing (once per day, however many reruns).

Nag limit: a heads-up that isn't critical is shown on at most `nag_limit` days
(secretary.yaml, default 2). Critical ones show every day until done or superseded.
A heads-up counts as shown only on a day one of its surfaces goes out: the paper
daily, the check-in packet on ONS_CHECKIN_CADENCE days.

The paper and the packet (written later in the same sync) read today's picks with
`shown_today()`; the website lists `open_headsups()`. Nothing here sends to a phone.

  python -m secretary.headsups --refresh [--date YYYY-MM-DD]   # the sync step (writes; then the
                                                               # day sheet, secretary/sheet.py)
  python -m secretary.headsups [--date …]                      # what's open/shown (read-only)
  python -m secretary.headsups --done ID | --dismiss ID | --reopen ID   # appends to the log
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secretary import config as SC  # noqa: E402

TIER_RANK = {"critical": 0, "important": 1, "nice_to_know": 2, "trivia": 3}
DAILY_SURFACES = {"paper", "paper_lead"}
ACTIONS = {"done": "done", "dismiss": "dismissed", "dismissed": "dismissed", "reopen": "open", "open": "open"}
CLOSED_BY_YOU = ("done", "dismissed")

DDL = """
CREATE SCHEMA IF NOT EXISTS secretary;
CREATE TABLE IF NOT EXISTS secretary.headsups (
    headsup_id      VARCHAR PRIMARY KEY,
    event_key       VARCHAR NOT NULL,
    source          VARCHAR NOT NULL,      -- calendar · template · project (step 6)
    title           VARCHAR NOT NULL,
    tier            VARCHAR NOT NULL,
    event_date      DATE NOT NULL,
    days_before     INTEGER NOT NULL,
    due_date        DATE NOT NULL,
    surfaces        VARCHAR[] NOT NULL,
    text            VARCHAR NOT NULL,
    status          VARCHAR NOT NULL,
    shown_count     INTEGER NOT NULL DEFAULT 0,
    first_shown_on  DATE,
    last_shown_on   DATE,
    created_at      TIMESTAMPTZ NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL,
    closed_at       TIMESTAMPTZ,
    closed_by       VARCHAR               -- website · cli · recap · sync
);
-- `at` of the last queued action the sync has seen for this row: the website compares it
-- with the log to tell a click the sync hasn't applied yet. (Added after the first release.)
ALTER TABLE secretary.headsups ADD COLUMN IF NOT EXISTS last_action_at VARCHAR;
"""


def actions_log():
    from api.store import JsonlLog          # stdlib-only module; same flock'd append as habits
    return JsonlLog("secretary", "headsup_actions.jsonl")


def record_action(headsup_id: str, action: str, by: str = "cli") -> dict:
    """Queue a done / dismiss / reopen. Safe while the API is running; the sync applies it."""
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {sorted(ACTIONS)}")
    return actions_log().append({"headsup_id": headsup_id, "status": ACTIONS[action], "by": by,
                                 "at": datetime.now(SC.TZ).isoformat(timespec="seconds")})


def pending_actions() -> dict[str, dict]:
    """Latest queued action per heads-up (the website overlays these until the sync applies them)."""
    return actions_log().latest_by("headsup_id")


# ── candidates ────────────────────────────────────────────────────────────────

@dataclass
class Milestone:
    headsup_id: str
    event_key: str
    source: str
    title: str
    tier: str
    event_date: date
    days_before: int
    due_date: date
    surfaces: list[str]
    text: str


def max_lead(cfg: SC.Config) -> int:
    rhythms = list(cfg.settings["rhythms"].values()) + [t.milestones for t in cfg.templates]
    return max([m["days_before"] for r in rhythms for m in (r or [])] + [0])


def event_rows(con, today: date, horizon: int) -> list[dict]:
    rows = con.execute(
        """SELECT event_key, source, display_title, tier, event_date, is_birthday, template_key
           FROM main_intermediate.int_events_tiered
           WHERE event_date BETWEEN ? AND ?""",
        [today, today + timedelta(days=horizon)]).fetchall()
    keys = ("event_key", "source", "title", "tier", "event_date", "is_birthday", "template_key")
    return [dict(zip(keys, r)) for r in rows]


def current_milestones(cfg: SC.Config, events: list[dict], today: date) -> list[Milestone]:
    """For each event, the latest milestone already due (due_date <= today <= event_date)."""
    out = []
    for e in events:
        rhythm = SC.rhythm_for(cfg, e["tier"], is_birthday=bool(e["is_birthday"]), template_key=e["template_key"])
        due = [m for m in rhythm if e["event_date"] - timedelta(days=m["days_before"]) <= today <= e["event_date"]]
        if not due:
            continue
        m = min(due, key=lambda m: m["days_before"])            # the closest to the event
        out.append(Milestone(
            headsup_id=f"{e['event_key']}@{m['days_before']}", event_key=e["event_key"], source=e["source"],
            title=e["title"], tier=e["tier"], event_date=e["event_date"], days_before=m["days_before"],
            due_date=e["event_date"] - timedelta(days=m["days_before"]), surfaces=list(m["surfaces"]),
            text=SC.render_text(m["text"], name=e["title"], on=e["event_date"], today=today)))
    return out


def surfaces_out_today(today: date) -> set[str]:
    from checkin.cadence import run_on_days
    days, _ = run_on_days()
    return DAILY_SURFACES | ({"checkin"} if days is None or today.weekday() in days else set())


# ── refresh (the sync step; the only writer) ──────────────────────────────────

def refresh(today: date, *, cfg: SC.Config | None = None, path: Path | None = None,
            surfaces_today: set[str] | None = None, now: datetime | None = None) -> dict[str, int]:
    import duckdb

    cfg = cfg or SC.load()
    surfaces_today = surfaces_out_today(today) if surfaces_today is None else surfaces_today
    now = now or datetime.now(SC.TZ)
    nag = int(cfg.settings["nag_limit"])
    con = duckdb.connect(str(path or SC.db_path()))
    try:
        con.execute(DDL)
        events = event_rows(con, today, max_lead(cfg))          # read before the transaction
        current = current_milestones(cfg, events, today)
        counts = {"actions": 0, "added": 0, "superseded": 0, "expired": 0, "gone": 0, "shown": 0}
        con.execute("BEGIN")

        # 1. done / dismiss / reopen queued by the website or the CLI
        for hid, a in pending_actions().items():
            status = a.get("status")
            if status not in ("open", *CLOSED_BY_YOU):
                continue
            n = con.execute(
                """UPDATE secretary.headsups
                   SET status = ?, updated_at = ?,
                       closed_at = CASE WHEN ? = 'open' THEN NULL ELSE ? END,
                       closed_by = CASE WHEN ? = 'open' THEN NULL ELSE ? END
                   WHERE headsup_id = ? AND status <> ? AND status IN ('open', 'done', 'dismissed')
                   RETURNING 1""",
                [status, now, status, now, status, a.get("by") or "website", hid, status]).fetchall()
            counts["actions"] += len(n)
            con.execute("""UPDATE secretary.headsups SET last_action_at = ?
                           WHERE headsup_id = ? AND last_action_at IS DISTINCT FROM ?""",
                        [a.get("at"), hid, a.get("at")])

        # 2. add the current milestone of each event; keep open ones' wording up to date
        for m in current:
            n = con.execute(
                """INSERT INTO secretary.headsups (headsup_id, event_key, source, title, tier, event_date,
                       days_before, due_date, surfaces, text, status, shown_count, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', 0, ?, ?)
                   ON CONFLICT (headsup_id) DO NOTHING
                   RETURNING 1""",
                [m.headsup_id, m.event_key, m.source, m.title, m.tier, m.event_date, m.days_before,
                 m.due_date, m.surfaces, m.text, now, now]).fetchall()
            counts["added"] += len(n)
            con.execute(
                """UPDATE secretary.headsups SET title = ?, tier = ?, surfaces = ?, text = ?, updated_at = ?
                   WHERE headsup_id = ? AND status = 'open'
                     AND (title <> ? OR tier <> ? OR surfaces <> ? OR text <> ?)""",
                [m.title, m.tier, m.surfaces, m.text, now, m.headsup_id, m.title, m.tier, m.surfaces, m.text])
            counts["superseded"] += len(con.execute(
                """UPDATE secretary.headsups SET status = 'superseded', updated_at = ?, closed_at = ?, closed_by = 'sync'
                   WHERE event_key = ? AND days_before > ? AND status = 'open' RETURNING 1""",
                [now, now, m.event_key, m.days_before]).fetchall())

        # 3. the day has passed, or the event left the calendar
        counts["expired"] = len(con.execute(
            """UPDATE secretary.headsups SET status = 'expired', updated_at = ?, closed_at = ?, closed_by = 'sync'
               WHERE status = 'open' AND event_date < ? RETURNING 1""", [now, now, today]).fetchall())
        live = [e["event_key"] for e in events]
        counts["gone"] = len(con.execute(
            """UPDATE secretary.headsups SET status = 'gone', updated_at = ?, closed_at = ?, closed_by = 'sync'
               WHERE status = 'open' AND source <> 'project' AND NOT list_contains(CAST(? AS VARCHAR[]), event_key) RETURNING 1""",
            [now, now, live]).fetchall())

        # 4. today's picks: due, under the nag limit (or critical), on a surface that goes out today
        counts["shown"] = len(con.execute(
            """UPDATE secretary.headsups
               SET shown_count = shown_count + 1, first_shown_on = coalesce(first_shown_on, ?),
                   last_shown_on = ?, updated_at = ?
               WHERE status = 'open' AND due_date <= ? AND ? <= event_date
                 AND last_shown_on IS DISTINCT FROM ?
                 AND (tier = 'critical' OR shown_count < ?)
                 AND len(list_intersect(surfaces, CAST(? AS VARCHAR[]))) > 0
               RETURNING 1""",
            [today, today, now, today, today, today, nag, sorted(surfaces_today)]).fetchall())
        con.execute("COMMIT")
        counts["showing_today"] = con.execute(
            "SELECT count(*) FROM secretary.headsups WHERE status = 'open' AND last_shown_on = ?", [today]
        ).fetchone()[0]
        return counts
    except Exception:
        try:
            con.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        con.close()


# ── reads (read-only; for the paper, the packet and the website) ──────────────

COLUMNS = ("headsup_id", "event_key", "source", "title", "tier", "event_date", "days_before", "due_date",
           "surfaces", "text", "status", "shown_count", "first_shown_on", "last_shown_on")


def _select(con, where: str, params: list) -> list[dict]:
    try:
        rows = con.execute(f"SELECT {', '.join(COLUMNS)} FROM secretary.headsups WHERE {where}", params).fetchall()
    except Exception:                                   # table not created yet: nothing to show
        return []
    out = [dict(zip(COLUMNS, r)) for r in rows]
    return sorted(out, key=lambda h: (TIER_RANK.get(h["tier"], 9), h["event_date"], h["title"]))


def shown_today(con, today: date, surface: str | None = None) -> list[dict]:
    """What the sync picked for today, optionally only those meant for one surface."""
    rows = _select(con, "status = 'open' AND last_shown_on = ?", [today])
    return [h for h in rows if surface is None or surface in h["surfaces"]]


def open_headsups(con, today: date) -> list[dict]:
    """Every open heads-up still ahead of its event (the website's list), nag limit or not."""
    return _select(con, "status = 'open' AND due_date <= ? AND ? <= event_date", [today, today])


def report(con, today: date) -> str:
    lines = [f"Heads-ups for {today:%a %b} {today.day}:"]
    picked = {h["headsup_id"] for h in shown_today(con, today)}
    rows = open_headsups(con, today)
    if not rows:
        lines.append("  (none open)")
    for h in rows:
        mark = "▶" if h["headsup_id"] in picked else "·"
        lines.append(f"  {mark} {h['tier']:<12} {h['event_date']:%a %b %d}  [{'+'.join(h['surfaces'])}] "
                     f"shown {h['shown_count']}×  {h['text']}   ({h['headsup_id']})")
    lines.append("  ▶ = shown today · = open, past the nag limit or not on today's surfaces")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--refresh", action="store_true", help="update secretary.headsups (API must be stopped)")
    p.add_argument("--date", type=date.fromisoformat, help="treat this day as today")
    for a in ("done", "dismiss", "reopen"):
        p.add_argument(f"--{a}", metavar="HEADSUP_ID", help=f"queue '{a}' for the next sync")
    args = p.parse_args(argv)
    today = args.date or SC.today_local()

    for a in ("done", "dismiss", "reopen"):
        if getattr(args, a):
            record_action(getattr(args, a), a, by="cli")
            print(f"queued: {a} {getattr(args, a)} (applied at the next sync)")
            return 0

    if args.refresh:
        try:
            counts = refresh(today)
        except Exception as e:
            print(f"✗ heads-ups not refreshed: {e}", file=sys.stderr)
            return 1
        print("refreshed: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
        from secretary import sheet
        try:
            print(f"day sheet: {sheet.build_and_write(today)}")
        except Exception as e:
            print(f"✗ day sheet not written: {e}", file=sys.stderr)
            return 1

    import duckdb
    try:
        con = duckdb.connect(str(SC.db_path()), read_only=True)
    except Exception as e:
        print(f"can't open the warehouse read-only: {e}", file=sys.stderr)
        return 1
    try:
        print(report(con, today))
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
