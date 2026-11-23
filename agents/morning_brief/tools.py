"""
Stage 1 of the morning-brief agent: the data tools.

A tool answers one narrow question about the day ("how is running going?")
and returns a ToolResult. Every tool follows three rules:

1. No LLM calls. Tools are plain, deterministic Python you can unit-test.
2. Facts are flat and named. Each value in `facts` gets an id such as
   "running.miles_7d". Later stages depend on those ids: the writer (stage 2)
   cites them, and the grounding evaluator (stage 3) checks every claim the
   brief makes against them.
3. Say what you don't know. A tool reports how fresh its data is (`as_of`,
   `stale`) and records gaps in `notes` or `error` instead of returning a
   confident zero. The old OpenClaw brief broke this rule: it sent the model
   one number from a stale mart and let it make up the rest.

Tools read the warehouse read-only plus the small files the web app and the
daily sync keep under data/ (habit log, shows, calendar, Spotify).
"""

from __future__ import annotations

import csv
import json
import os
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb

from api.store import HABITS_LOG, data_dir

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("ONS_DB_PATH", ROOT / "data" / "warehouse" / "ons.duckdb"))


# ── Plumbing ─────────────────────────────────────────────────────────────────

@dataclass
class Ctx:
    """What every tool gets: a read-only warehouse connection and 'today'."""
    con: duckdb.DuckDBPyConnection
    today: date
    tz: ZoneInfo


@dataclass
class ToolResult:
    name: str
    facts: dict[str, Any] = field(default_factory=dict)
    as_of: str | None = None         # ISO date of the newest record behind the facts
    stale: bool = False              # newest record is older than freshness_days
    freshness_days: int | None = None
    notes: list[str] = field(default_factory=list)  # context for the writer
    error: str | None = None         # the tool failed; facts are empty

    def mark_as_of(self, newest: date, today: date) -> None:
        self.as_of = newest.isoformat()
        # Also a citable fact, so "you haven't logged since Nov 6" has a source.
        self.facts["newest_data"] = _day(newest)
        if self.freshness_days is not None:
            self.stale = (today - newest).days > self.freshness_days

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rows(con: duckdb.DuckDBPyConnection, sql: str, params: list | None = None) -> list[dict]:
    cur = con.execute(sql, params or [])
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _local_date(value: Any, tz: ZoneInfo) -> date:
    """Timestamps in the warehouse are UTC; the brief thinks in Denver days."""
    if isinstance(value, datetime):
        return value.astimezone(tz).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    return _local_date(datetime.fromisoformat(str(value)), tz)


def _day(d: date) -> str:
    return d.strftime("%a %b %-d")   # "Sun Nov 15"


def _num(x: Any, places: int = 1) -> float | None:
    return None if x is None else round(float(x), places)


# ── Tools ────────────────────────────────────────────────────────────────────

def running(ctx: Ctx) -> ToolResult:
    r = ToolResult("running", freshness_days=14)
    rows = _rows(ctx.con, """
        SELECT name, start_date, distance_miles
        FROM strava.activities
        WHERE is_run
        ORDER BY start_date
    """)
    runs = [(_local_date(x["start_date"], ctx.tz), x) for x in rows]
    runs = [(d, x) for d, x in runs if d <= ctx.today]
    if not runs:
        r.notes.append("No runs recorded in Strava.")
        return r

    week = [x for d, x in runs if d > ctx.today - timedelta(days=7)]
    ytd = [x for d, x in runs if d.year == ctx.today.year]
    last_day, last = runs[-1]
    r.facts = {
        "runs_7d": len(week),
        "miles_7d": _num(sum(x["distance_miles"] or 0 for x in week)),
        "runs_ytd": len(ytd),
        "miles_ytd": _num(sum(x["distance_miles"] or 0 for x in ytd)),
        "last_run_date": _day(last_day),
        "last_run_days_ago": (ctx.today - last_day).days,
        "last_run_name": last["name"],
        "last_run_miles": _num(last["distance_miles"]),
    }
    r.mark_as_of(last_day, ctx.today)
    return r


def training_load(ctx: Ctx) -> ToolResult:
    r = ToolResult("training_load", freshness_days=3)
    rows = _rows(ctx.con, """
        SELECT CAST(day AS DATE) AS day, ctl, atl, tsb, readiness_signal
        FROM main_marts.mart_training_load
        WHERE CAST(day AS DATE) <= ?
        ORDER BY day DESC
        LIMIT 1
    """, [ctx.today])
    if not rows:
        r.notes.append("No training-load rows yet.")
        return r
    x = rows[0]
    r.facts = {
        "fitness_ctl": _num(x["ctl"]),
        "fatigue_atl": _num(x["atl"]),
        "form_tsb": _num(x["tsb"]),
        "readiness": x["readiness_signal"],
    }
    r.notes.append(
        "CTL is long-term fitness, ATL is short-term fatigue, TSB (form) is CTL minus ATL; "
        "negative form means carrying fatigue. Readiness is green / yellow / red."
    )
    r.mark_as_of(x["day"], ctx.today)
    return r


def crossfit(ctx: Ctx) -> ToolResult:
    r = ToolResult("crossfit", freshness_days=14)
    rows = _rows(ctx.con, """
        SELECT date, title, pr
        FROM sugarwod.workouts
        WHERE date <= ?
        ORDER BY date DESC
    """, [ctx.today])
    if not rows:
        r.notes.append("No SugarWOD workouts imported.")
        return r
    last = rows[0]
    r.facts = {
        "workouts_7d": sum(1 for x in rows if x["date"] > ctx.today - timedelta(days=7)),
        "prs_30d": sum(1 for x in rows if x["pr"] and x["date"] > ctx.today - timedelta(days=30)),
        "last_workout_date": _day(last["date"]),
        "last_workout_days_ago": (ctx.today - last["date"]).days,
        "last_workout_title": last["title"],
    }
    r.mark_as_of(last["date"], ctx.today)
    if r.stale:
        r.notes.append(
            "SugarWOD only updates when its CSV export is imported, so a gap here "
            "means the import is behind, not that workouts stopped."
        )
    return r


def _streak(done: dict[date, bool], today: date) -> int:
    """Consecutive done days ending today, or ending yesterday if today isn't done yet."""
    d = today if done.get(today) else today - timedelta(days=1)
    n = 0
    while done.get(d):
        n += 1
        d -= timedelta(days=1)
    return n


def habits(ctx: Ctx) -> ToolResult:
    # Read the JSONL log the Habits page writes to. main_marts.mart_habit_streaks
    # is built from habits.habit_log, which has fallen behind that log.
    r = ToolResult("habits", freshness_days=2)
    by_day: dict[date, dict] = {}
    for key, row in HABITS_LOG.latest_by("date").items():
        try:
            d = date.fromisoformat(str(key))
        except ValueError:
            continue
        if d <= ctx.today:
            by_day[d] = row
    if not by_day:
        r.notes.append("No habits logged yet.")
        return r

    names = sorted({k for row in by_day.values() for k in row if k not in ("date", "logged_at")})
    yesterday = ctx.today - timedelta(days=1)
    week = [ctx.today - timedelta(days=i) for i in range(1, 8)]   # the 7 days before today

    r.facts["tracked"] = names
    r.facts["logged_yesterday"] = yesterday in by_day
    if yesterday in by_day:
        r.facts["done_yesterday"] = [h for h in names if by_day[yesterday].get(h)]
        r.facts["missed_yesterday"] = [h for h in names if not by_day[yesterday].get(h)]
    r.facts["done_today_so_far"] = [h for h in names if by_day.get(ctx.today, {}).get(h)]
    r.facts["days_logged_7d"] = sum(1 for d in week if d in by_day)
    for h in names:
        done = {d: bool(row.get(h)) for d, row in by_day.items()}
        r.facts[f"{h}_done_7d"] = sum(1 for d in week if done.get(d))
        r.facts[f"{h}_streak"] = _streak(done, ctx.today)

    r.mark_as_of(max(by_day), ctx.today)
    r.notes.append("Habits are logged by hand; a day with no log is unknown, not a miss.")
    return r


def reading(ctx: Ctx) -> ToolResult:
    r = ToolResult("reading")   # no freshness window: gaps between books are normal
    rows = _rows(ctx.con, """
        SELECT title, authors, marked_read_at
        FROM hardcover.books_read
        WHERE marked_read_at IS NOT NULL
        ORDER BY marked_read_at
    """)
    books = [(_local_date(x["marked_read_at"], ctx.tz), x) for x in rows]
    books = [(d, x) for d, x in books if d <= ctx.today]
    r.notes.append("Hardcover only tracks finished books; there is no currently-reading data.")
    if not books:
        return r
    last_day, last = books[-1]
    r.facts = {
        "books_finished_ytd": sum(1 for d, _ in books if d.year == ctx.today.year),
        "last_finished_title": last["title"],
        "last_finished_author": last["authors"],
        "last_finished_date": _day(last_day),
        "days_since_last_finished": (ctx.today - last_day).days,
    }
    r.mark_as_of(last_day, ctx.today)
    return r


def film(ctx: Ctx) -> ToolResult:
    r = ToolResult("film")
    rows = _rows(ctx.con, """
        SELECT title, film_year, watch_date, rating, is_rewatch
        FROM main_marts.mart_film_watches
        WHERE watch_date <= ?
        ORDER BY watch_date DESC
    """, [ctx.today])
    if not rows:
        r.notes.append("No film watches recorded.")
        return r
    last = rows[0]
    r.facts = {
        "films_7d": sum(1 for x in rows if x["watch_date"] > ctx.today - timedelta(days=7)),
        "films_ytd": sum(1 for x in rows if x["watch_date"].year == ctx.today.year),
        "last_film_title": last["title"],
        "last_film_year": last["film_year"],
        "last_film_date": _day(last["watch_date"]),
        "last_film_rewatch": bool(last["is_rewatch"]),
    }
    if last["rating"] is not None:
        r.facts["last_film_rating_of_5"] = _num(last["rating"])
    r.mark_as_of(last["watch_date"], ctx.today)
    return r


def shows(ctx: Ctx) -> ToolResult:
    r = ToolResult("shows", freshness_days=3)
    path = data_dir() / "shows" / "my_artist_shows.json"
    if not path.exists():
        r.error = f"{path.name} not found"
        return r
    payload = json.loads(path.read_text())
    upcoming, seen = [], set()
    for s in payload.get("shows", []):
        try:
            start = datetime.fromisoformat(s["start_datetime"]).astimezone(ctx.tz)
        except (KeyError, ValueError):
            continue
        # Ticket sites list one show several times ("Ages 16+", "Club Seating",
        # a second venue spelling). Same start time + same venue = same show.
        venue = (s.get("venue") or "").split(" - ")[0].strip().lower()
        if (start, venue) in seen:
            continue
        seen.add((start, venue))
        if ctx.today <= start.date() <= ctx.today + timedelta(days=30):
            upcoming.append((start, s))
    upcoming.sort(key=lambda t: t[0])

    def label(start: datetime, s: dict) -> str:
        return f"{_day(start.date())}: {s.get('title') or s.get('artist')} at {s.get('venue')} ({start:%-I:%M %p})"

    r.facts = {
        "tonight": [label(st, s) for st, s in upcoming if st.date() == ctx.today],
        "next_7d": [label(st, s) for st, s in upcoming
                    if ctx.today < st.date() <= ctx.today + timedelta(days=7)][:8],
        "count_30d": len(upcoming),
    }
    r.notes.append(
        "These are Denver shows by artists in your Spotify playlists, matched by name. "
        "They are not tickets you hold, and name matching sometimes picks the wrong band."
    )
    if payload.get("fetched_at"):
        r.mark_as_of(_local_date(payload["fetched_at"], ctx.tz), ctx.today)
    return r


def calendar(ctx: Ctx) -> ToolResult:
    r = ToolResult("calendar", freshness_days=2)   # exported daily
    folder = data_dir() / "calendar" / "processed"
    files = [folder / f"events_clean_{y}.csv" for y in (ctx.today.year, ctx.today.year + 1)]
    files = [f for f in files if f.exists()]
    if not files:
        r.error = "no calendar export found"
        return r

    today_items, week_items = [], []
    for f in files:
        with f.open(newline="") as fh:
            for row in csv.DictReader(fh):
                start, title = row.get("start", ""), (row.get("summary") or "").strip()
                if not start or not title:
                    continue
                if len(start) == 10:                         # all-day: "2026-11-16"
                    d, when = date.fromisoformat(start), "All day"
                else:
                    dt = datetime.fromisoformat(start).astimezone(ctx.tz)
                    d, when = dt.date(), f"{dt:%-I:%M %p}"
                if d == ctx.today:
                    today_items.append(f"{when}: {title}")
                elif ctx.today < d <= ctx.today + timedelta(days=7):
                    week_items.append((d, f"{_day(d)}: {title}"))

    week_items.sort(key=lambda t: t[0])
    r.facts = {"today": today_items, "next_7d": [w for _, w in week_items][:12]}
    newest = max(datetime.fromtimestamp(f.stat().st_mtime, ctx.tz).date() for f in files)
    r.mark_as_of(newest, ctx.today)
    return r


def goals(ctx: Ctx) -> ToolResult:
    r = ToolResult("goals")
    rows = _rows(ctx.con, """
        SELECT goal_key, current_value, target_numeric, progress_percent,
               expected_progress_ratio, pace_status
        FROM main_marts.mart_goal_pacing
        WHERE year = ?
        ORDER BY domain, goal_key
    """, [ctx.today.year])
    tracked = [x for x in rows if x["current_value"] is not None and x["target_numeric"]]
    r.facts["goals_total"] = len(rows)
    r.facts["goals_with_progress_data"] = len(tracked)
    for x in tracked:
        k = x["goal_key"]
        r.facts[f"{k}_current"] = _num(x["current_value"])
        r.facts[f"{k}_target"] = _num(x["target_numeric"])
        r.facts[f"{k}_pct"] = _num(x["progress_percent"])
        if x["expected_progress_ratio"] is not None:
            r.facts[f"{k}_expected_pct"] = _num(x["expected_progress_ratio"] * 100)
        r.facts[f"{k}_pace"] = x["pace_status"]
    if len(tracked) < len(rows):
        r.notes.append(
            f"{len(rows) - len(tracked)} goals have no progress data yet; "
            "don't describe them as behind."
        )
    return r


def music(ctx: Ctx) -> ToolResult:
    r = ToolResult("music", freshness_days=7)
    folder = data_dir() / "spotify" / "processed"

    daily10 = folder / "daily10_latest.json"
    if daily10.exists():
        d10 = json.loads(daily10.read_text())
        r.facts["daily10_date"] = d10.get("date")
        r.facts["daily10_discovery_artists"] = d10.get("tewnidge_artists", [])

    streams = folder / "streams_clean.csv"
    if streams.exists():
        since = ctx.today - timedelta(days=7)
        counts: Counter[str] = Counter()
        newest: date | None = None
        with streams.open(newline="") as fh:
            for row in csv.DictReader(fh):
                try:
                    d = datetime.fromisoformat(row["played_at"]).date()
                except (KeyError, ValueError):
                    continue
                if d > ctx.today:
                    continue
                newest = d if newest is None or d > newest else newest
                if d > since:
                    counts[row.get("artist_name") or "?"] += 1
        r.facts["top_artists_7d"] = [a for a, _ in counts.most_common(5)]
        if newest:
            r.mark_as_of(newest, ctx.today)
            if r.stale:
                r.notes.append(
                    "Listening history comes from Spotify's data export, which is behind; "
                    "don't describe recent listening from it."
                )
    if not r.facts:
        r.error = "no Spotify files found"
    return r


TOOLS = [running, training_load, crossfit, habits, reading, film, shows, calendar, goals, music]
