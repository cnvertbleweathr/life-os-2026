"""
Build the ONS check-in packet: a short Markdown summary to talk through in a
Claude voice chat. Deterministic: no LLM call.

    uv run python -m checkin.build_packet            # build today's, save, print
    uv run python -m checkin.build_packet --no-save  # print only

Sources, all read-only:
  - checkin/priorities.md (copied word for word, minus the HTML comment)
  - main_marts.brief_context_7d (fitness, music, CFB picks, followed teams)
  - main_marts.mart_habit_performance (one row per log_date)
  - data/brief/<date>.json (today's morning brief)
  - git log / gh pr list, and the ROADMAP.md 🟡 In Progress and 🔴 Blocked rows
  - data/checkin/packet_posts.jsonl (written by post_slack.py) for "days since
    last check-in"; the app's data/checkin/checkin_log.jsonl is shown separately

Saved to data/checkin/<date>.md. Kept under MAX_CHARS by shortening lists
("+N more") before anything else.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

from agents.morning_brief.tools import DB_PATH
from api.store import JsonlLog, data_dir, today_local
from checkin.init_priorities import PRIORITIES

ROOT = Path(__file__).resolve().parents[1]
ROADMAP = ROOT / "ROADMAP.md"
MAX_CHARS = 3000
LIST_LIMITS = (6, 4, 3, 2, 1)        # tried in order until the packet fits
KM_PER_MILE = 1.609344
WINDOW_DAYS = 7
HABITS = ["meditation", "pushups_100", "nonfiction_pages_10", "fiction_pages_10"]
STOPWORDS = {
    "this", "that", "with", "from", "into", "have", "will", "week", "more", "less",
    "some", "then", "than", "them", "they", "what", "when", "about", "make", "finish",
    "start", "keep", "each", "every", "daily", "done", "ship", "work", "also", "just",
    "the", "and", "for", "get", "out", "new", "all", "day", "per", "one", "two", "three",
    "four", "five", "time", "once", "twice", "least", "try", "not", "but", "its",
    "year", "month", "help", "want", "need", "much", "possible", "important", "yet", "set",
}


def post_log() -> JsonlLog:
    return JsonlLog("checkin", "packet_posts.jsonl")


def app_checkin_log() -> JsonlLog:
    return JsonlLog("checkin", "checkin_log.jsonl")


def packet_dir() -> Path:
    return data_dir() / "checkin"


# ── inputs ───────────────────────────────────────────────────────────────────

@dataclass
class Inputs:
    today: date
    priorities: str | None = None                       # raw priorities.md text
    context: list[dict[str, Any]] = field(default_factory=list)   # brief_context_7d rows
    habits: list[dict[str, Any]] = field(default_factory=list)    # mart_habit_performance rows
    habits_log_latest: date | None = None               # newest date in habits_log.jsonl
    brief: dict[str, Any] | None = None
    commits: list[dict[str, str]] | None = None         # None = git unavailable
    merged_prs: list[dict[str, Any]] | None = None      # None = gh unavailable
    open_prs: list[dict[str, Any]] | None = None
    roadmap: str | None = None
    last_post: date | None = None
    last_app_checkin: date | None = None
    warnings: list[str] = field(default_factory=list)


def _date(v: Any) -> date | None:
    if v is None or isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _facts(row: dict[str, Any]) -> dict[str, Any]:
    f = row.get("facts")
    if isinstance(f, str):
        try:
            return json.loads(f)
        except json.JSONDecodeError:
            return {}
    return f or {}


def _run(cmd: list[str], timeout: int = 20) -> str | None:
    try:
        out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout if out.returncode == 0 else None


def load_warehouse(inp: Inputs, db_path: Path | str | None = None) -> None:
    """brief_context_7d (minus news) and mart_habit_performance, read-only."""
    try:
        con = duckdb.connect(str(db_path or DB_PATH), read_only=True)
    except duckdb.Error as e:
        inp.warnings.append(f"warehouse unavailable ({type(e).__name__})")
        return
    try:
        for attr, sql in [
            ("context", "SELECT * FROM main_marts.brief_context_7d WHERE domain <> 'news'"),
            ("habits", "SELECT * FROM main_marts.mart_habit_performance ORDER BY log_date"),
        ]:
            try:
                cur = con.execute(sql)
                cols = [c[0] for c in cur.description]
                setattr(inp, attr, [dict(zip(cols, r)) for r in cur.fetchall()])
            except duckdb.Error as e:
                inp.warnings.append(f"{sql.split('FROM ')[1].split()[0]} unavailable ({type(e).__name__})")
    finally:
        con.close()


def load_git(inp: Inputs) -> None:
    since = (inp.today - timedelta(days=WINDOW_DAYS - 1)).isoformat()
    out = _run(["git", "log", f"--since={since} 00:00", "--no-merges", "--date=short",
                "--pretty=%h%x09%ad%x09%s", "HEAD"])
    if out is not None:
        inp.commits = [dict(zip(("sha", "date", "subject"), l.split("\t", 2)))
                       for l in out.splitlines() if l.count("\t") >= 2]
    merged = _run(["gh", "pr", "list", "--state", "merged", "--search", f"merged:>={since}",
                   "--json", "number,title,mergedAt", "--limit", "50"])
    opened = _run(["gh", "pr", "list", "--state", "open",
                   "--json", "number,title,createdAt,headRefName", "--limit", "100"])
    if merged is not None and opened is not None:
        inp.merged_prs = sorted(json.loads(merged), key=lambda p: p["number"])
        inp.open_prs = sorted(json.loads(opened), key=lambda p: p["number"])


def gather(today: date | None = None, db_path: Path | str | None = None) -> Inputs:
    inp = Inputs(today=today or today_local())
    if PRIORITIES.exists():
        inp.priorities = PRIORITIES.read_text()
    load_warehouse(inp, db_path)
    habits_file = data_dir() / "habits" / "habits_log.jsonl"
    if habits_file.exists():
        dates = [_date(json.loads(l).get("date")) for l in habits_file.read_text().splitlines() if l.strip()]
        inp.habits_log_latest = max((d for d in dates if d), default=None)
    brief = data_dir() / "brief" / f"{inp.today.isoformat()}.json"
    if brief.exists():
        inp.brief = json.loads(brief.read_text())
    load_git(inp)
    if ROADMAP.exists():
        inp.roadmap = ROADMAP.read_text()
    posts = [_date(r.get("date")) for r in post_log().rows() if r.get("ok")]
    inp.last_post = max((d for d in posts if d and d < inp.today), default=None)
    checkins = [_date(r.get("date")) for r in app_checkin_log().rows()]
    inp.last_app_checkin = max((d for d in checkins if d), default=None)
    return inp


# ── sections ─────────────────────────────────────────────────────────────────

def cap(items: list[str], n: int) -> list[str]:
    return items if len(items) <= n else items[:n] + [f"+{len(items) - n} more"]


def _ago(d: date | None, today: date) -> str:
    if d is None:
        return "never"
    n = (today - d).days
    return f"{d.isoformat()}, {'today' if n == 0 else '1 day ago' if n == 1 else f'{n} days ago'}"


def priorities_body(text: str | None) -> tuple[str, bool]:
    """(verbatim priorities without the HTML comment and H1, is_blank_template)."""
    if text is None:
        return "_No checkin/priorities.md yet. Create it with `python -m checkin.init_priorities`._", True
    body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    lines = [l for l in body.splitlines() if not re.match(r"#\s", l)]
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    blank = not any(re.match(r"\s*[-*]\s*\S", l) for l in lines)
    if blank:
        return "_priorities.md is still the blank template._", True
    return body, False


def priority_items(text: str | None) -> list[str]:
    """Bullets under "This week's priorities"."""
    if not text:
        return []
    m = re.search(r"^## This week's priorities\s*$(.*?)(?=^## |\Z)", text, flags=re.M | re.S)
    if not m:
        return []
    return [re.sub(r"^\s*[-*]\s*(\[.\]\s*)?", "", l).strip()
            for l in m.group(1).splitlines() if re.match(r"\s*[-*]\s*\S", l)]


def _rows(inp: Inputs, domain: str, kind: str) -> list[dict[str, Any]]:
    return [r for r in inp.context if r.get("domain") == domain and r.get("kind") == kind]


def _in_window(d: date | None, today: date) -> bool:
    return d is not None and today - timedelta(days=WINDOW_DAYS - 1) <= d <= today


def _record(f: dict[str, Any]) -> str:
    return f"{f.get('wins', 0)}-{f.get('losses', 0)}" + (f"-{f['pushes']}" if f.get("pushes") else "")


def _score(f: dict[str, Any], us: str, them: str) -> str:
    a, b = f.get(us), f.get(them)
    if a is None or b is None:
        return ""
    return f"{max(a, b)}-{min(a, b)}"       # winner first


def tracking_lines(inp: Inputs, limit: int) -> list[str]:
    t = inp.today
    lines: list[str] = []

    acts = [r for r in _rows(inp, "fitness", "activity") if _in_window(_date(r["item_date"]), t)]
    km = sum((_facts(r).get("distance_miles") or 0) for r in acts) * KM_PER_MILE
    cf = [r for r in _rows(inp, "fitness", "crossfit") if _in_window(_date(r["item_date"]), t)]
    cf_days = len({_date(r["item_date"]) for r in cf})
    prs = sum(1 for r in cf if _facts(r).get("pr"))
    workout = f"{len(acts)} Strava ({km:.1f} km)" if acts else "0 Strava"
    sessions = f"{cf_days} SugarWOD session{'s' if cf_days != 1 else ''}"
    if cf:
        sessions += f" ({len(cf)} workouts, {prs} PR{'s' if prs != 1 else ''})"
    lines.append(f"- *Workouts:* {len(acts) + cf_days} — {workout}, {sessions}")

    top = sorted(_rows(inp, "music", "top_artist"), key=lambda r: _facts(r).get("rank", 99))
    week = next(iter(_rows(inp, "music", "week_summary")), None)
    if top:
        lines.append("- *Top artists:* " + ", ".join(cap([r["title"] for r in top], min(limit, 5))))
    else:
        newest = _facts(week).get("newest_play_date") if week else None
        lines.append(f"- *Music:* no plays this week (newest export play {newest or 'unknown'})")

    weeks = sorted(_rows(inp, "cfb_picks", "week_record"), key=lambda r: _facts(r).get("week", 0))
    season = next(iter(_rows(inp, "cfb_picks", "season_record")), None)
    if weeks:
        f = _facts(weeks[-1])
        rec = _record(f)
        pend = f", {f['pending']} pending" if f.get("pending") else ""
        line = f"- *CFB picks, week {f.get('week')}:* {rec}, {f.get('units', 0):+.2f}u{pend}"
        if season:
            s = _facts(season)
            line += f" (season {_record(s)}, {s.get('units', 0):+.2f}u)"
        lines.append(line)

    results: list[str] = []
    for r in sorted(_rows(inp, "cfb_games", "game"), key=lambda r: _date(r["item_date"]) or t):
        f = _facts(r)
        if not _in_window(_date(r["item_date"]), t):
            continue
        verb = "beat" if f.get("result") == "W" else "lost to" if f.get("result") == "L" else "tied"
        results.append(f"{f.get('team')} {verb} {f.get('opponent')} {_score(f, 'team_points', 'opp_points')}"
                       + (f" ({f['record_after']})" if f.get("record_after") else ""))
    by_team: dict[str, list[dict[str, Any]]] = {}
    for r in sorted(_rows(inp, "team_games", "game"), key=lambda r: _date(r["item_date"]) or t):
        if _in_window(_date(r["item_date"]), t):
            f = _facts(r)
            by_team.setdefault(f.get("team_name") or f.get("team"), []).append(f)
    for team, games in by_team.items():
        w = sum(g.get("result") == "W" for g in games)
        l = len(games) - w
        detail = ", ".join(f"{g.get('result')} {_score(g, 'team_score', 'opp_score')} "
                           f"{'vs' if g.get('venue') == 'home' else 'at'} {g.get('opponent')}" for g in games)
        rec = games[-1].get("season_record")
        results.append(f"{team.split()[-1]} {w}-{l}: {detail}" + (f" ({rec})" if rec else ""))
    if results:
        lines.append("- *Teams:*")
        lines += [f"  - {x}" for x in cap(results, limit)]
    return lines


def habit_lines(inp: Inputs) -> tuple[list[str], list[str]]:
    """(section lines, talking-point candidates)."""
    t = inp.today
    rows = [r for r in inp.habits if _date(r.get("log_date"))]
    rows.sort(key=lambda r: _date(r["log_date"]))
    week = [r for r in rows if _in_window(_date(r["log_date"]), t)]
    latest = _date(rows[-1]["log_date"]) if rows else None
    lines: list[str] = []
    points: list[str] = []
    if not week:
        lines.append(f"- No habit logs in the last 7 days (latest {_ago(latest, t)})")
    else:
        pct = sum(float(r.get("daily_completion_pct") or 0) for r in week) / len(week)
        lines.append(f"- Logged {len(week)} of 7 days, {pct:.0f}% average completion (latest {_ago(latest, t)})")
        counts = ", ".join(f"{h} {sum(int(r.get(h) or 0) for r in week)}/{len(week)}" for h in HABITS)
        lines.append(f"- {counts}")
    if latest and (t - latest).days >= 3:
        points.append(f"Habits haven't been logged for {(t - latest).days} days. Still tracking them?")
    if len(rows) >= 2:
        prev, last = rows[-2], rows[-1]
        broken = [h for h in HABITS if int(prev.get(h) or 0) and not int(last.get(h) or 0)]
        if broken:
            lines.append(f"- Streak broken on {last['log_date']}: {', '.join(broken)}")
            points.append(f"Broken streak: {', '.join(broken)} done on {prev['log_date']} but not {last['log_date']}.")
    if inp.habits_log_latest and latest and inp.habits_log_latest > latest:
        lines.append(f"- _The mart lags the habit log (log has {inp.habits_log_latest}); dbt hasn't rebuilt it._")
    return lines, points


def brief_lines(inp: Inputs) -> tuple[list[str], list[str]]:
    b = inp.brief
    if not b:
        return ["- No brief for today."], ["Today's morning brief didn't publish. Check the sync log."]
    status = "pass" if b.get("status") == "published" else b.get("status", "unknown")
    head = (b.get("edition") or {}).get("lead_headline", "(no headline)")
    revs = b.get("revisions")
    line = f"- \"{head}\" — *{status}*" + (f", {revs} revision{'s' if revs != 1 else ''}" if revs is not None else "")
    if b.get("cost_usd") is not None:
        line += f", ${b['cost_usd']:.2f}"
    points = []
    if status != "pass":
        points.append("Today's brief is flagged needs_review. Read it before it goes to print.")
    return [line], points


def roadmap_items(text: str | None) -> list[tuple[str, str]]:
    """(emoji, item name) for ROADMAP table rows marked 🔴 Blocked or 🟡 In Progress, blocked first.

    Skips data-source tables (first header cell "Source"): a dead upstream
    feed is a permanent fact, not work to talk through.
    """
    if not text:
        return []
    items: list[tuple[str, str]] = []
    header: list[str] = []
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            header = []                                   # a blank or prose line ends the table
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not header:
            header = cells                                # first row of a table is its header
            continue
        if header[0].lower() == "source":
            continue
        mark = "🔴" if any(c.startswith("🔴") for c in cells) else "🟡" if any(c.startswith("🟡") for c in cells) else None
        if not mark:
            continue
        name = next((c for c in cells if c and not c.startswith(("🔴", "🟡")) and not c.isdigit()), "")
        name = re.sub(r"[*`]", "", name).strip()
        if name:
            items.append((mark, name))
    return sorted(items, key=lambda x: x[0] != "🔴")


def build_lines(inp: Inputs, limit: int) -> tuple[list[str], list[str]]:
    lines: list[str] = []
    points: list[str] = []
    if inp.commits is None:
        lines.append("- Commits: git unavailable")
    else:
        lines.append(f"- {len(inp.commits)} commit{'s' if len(inp.commits) != 1 else ''} in 7 days")
        lines += [f"  - {s}" for s in cap([c["subject"][:80] for c in inp.commits], limit)]
    if inp.merged_prs is None:
        lines.append("- PRs: gh unavailable")
    else:
        since = inp.today - timedelta(days=WINDOW_DAYS - 1)
        merged = [f"#{p['number']} {p['title'][:60]}" for p in inp.merged_prs]
        lines.append("- Merged: " + ("; ".join(cap(merged, limit)) if merged else "none"))
        new_open = [p for p in inp.open_prs or [] if (_date(p.get("createdAt")) or since) >= since]
        bots = [p for p in inp.open_prs or [] if str(p.get("headRefName", "")).startswith("dependabot/")]
        other = [f"#{p['number']} {p['title'][:60]}" for p in new_open if p not in bots]
        lines.append("- Opened this week, still open: " + ("; ".join(cap(other, limit)) if other else "none")
                     + (f" ({len(bots)} older Dependabot PRs open)" if bots else ""))
    items = roadmap_items(inp.roadmap)
    if items:
        lines.append("- ROADMAP open items:")
        shown = cap([f"{m} {n}" for m, n in items], limit)
        lines += [f"  - {s}" for s in shown]
        blocked = [n for m, n in items if m == "🔴"]
        if blocked:
            points.append(f"{len(blocked)} ROADMAP item{'s are' if len(blocked) != 1 else ' is'} blocked "
                          f"({blocked[0]}{', …' if len(blocked) > 1 else ''}). Still worth tracking?")
    return lines, points


def _keywords(text: str) -> set[str]:
    words = {w.lower().rstrip("s") for w in re.findall(r"[A-Za-z][A-Za-z0-9]+", text)}
    return {w for w in words if len(w) >= 3 and w not in STOPWORDS}


def activity_corpus(inp: Inputs) -> set[str]:
    text = []
    for r in inp.context:
        if _in_window(_date(r.get("item_date")), inp.today):
            text += [r.get("domain", ""), r.get("kind", ""), r.get("title") or ""]
    text += [c.get("subject", "") for c in inp.commits or []]
    text += [p.get("title", "") for p in inp.merged_prs or []]
    corpus = _keywords(" ".join(text))
    if any(r.get("domain") == "fitness" for r in inp.context if _in_window(_date(r.get("item_date")), inp.today)):
        corpus |= {"run", "running", "workout", "crossfit", "fitnes", "training", "gym"}
    if any(_in_window(_date(r.get("log_date")), inp.today) for r in inp.habits):
        corpus |= {"habit", "meditation", "meditate", "read", "reading", "pushup"}
    return corpus


def talking_points(inp: Inputs, extra: list[str]) -> list[str]:
    points: list[str] = []
    # Most priorities (family, job search, friends) are invisible to ONS, so
    # "no activity" isn't news. Ask about one of them a day, rotating by
    # date, and leave the other slots to points the data can actually support.
    corpus = activity_corpus(inp)
    untracked = [p for p in priority_items(inp.priorities) if _keywords(p) and not _keywords(p) & corpus]
    if untracked:
        p = untracked[inp.today.toordinal() % len(untracked)]
        label = p.split(":", 1)[0].strip()[:60]
        points.append(f"Check in on {label}: nothing in ONS tracks it this week. How's it going?")
    points += extra
    fit = next(iter(_rows(inp, "fitness", "week_summary")), None)
    if fit:
        f = _facts(fit)
        newest = _date(f.get("newest_activity_date"))
        if newest and (inp.today - newest).days >= 4:
            points.append(f"No Strava activity since {newest} ({(inp.today - newest).days} days).")
    if inp.last_app_checkin and (inp.today - inp.last_app_checkin).days > 7:
        points.append(f"Last app check-in was {_ago(inp.last_app_checkin, inp.today)}.")
    fallback = ["What's the one thing that has to happen this week?",
                "Anything in the parking lot ready to come off it, or to drop?",
                "What's draining time that isn't on the list?"]
    for f in fallback:
        if len(points) >= 3:
            break
        points.append(f)
    return points[:3]


# ── assemble ─────────────────────────────────────────────────────────────────

def render(inp: Inputs, limit: int, priorities_max_lines: int | None = None) -> str:
    t = inp.today
    since = "first packet" if inp.last_post is None else (
        f"{(t - inp.last_post).days} (last packet {inp.last_post.isoformat()})")
    pri, _ = priorities_body(inp.priorities)
    if priorities_max_lines is not None:
        pl = pri.splitlines()
        if len(pl) > priorities_max_lines:
            pri = "\n".join(pl[:priorities_max_lines] + [f"_+{len(pl) - priorities_max_lines} more lines in priorities.md_"])
    habits, habit_points = habit_lines(inp)
    brief, brief_points = brief_lines(inp)
    build, build_points = build_lines(inp, limit)
    points = talking_points(inp, brief_points + habit_points + build_points)

    out = [f"# Check-in — {t.strftime('%A, %b')} {t.day}, {t.year}",
           f"Days since last check-in: {since}",
           f"App check-in log: last entry {_ago(inp.last_app_checkin, t)}",
           "", "## My priorities", pri,
           "", "## Last 7 days", *tracking_lines(inp, limit),
           "", "## Habits", *habits,
           "", "## Today's brief", *brief,
           "", "## ONS build", *build,
           "", "## Talking points", *[f"{i}. {p}" for i, p in enumerate(points, 1)]]
    if inp.warnings:
        out += ["", "_Missing data: " + "; ".join(inp.warnings) + "_"]
    return "\n".join(out).strip() + "\n"


def build_packet(inp: Inputs, max_chars: int = MAX_CHARS) -> str:
    text = ""
    for limit in LIST_LIMITS:
        text = render(inp, limit)
        if len(text) <= max_chars:
            return text
    for keep in (12, 8, 4, 0):
        text = render(inp, LIST_LIMITS[-1], priorities_max_lines=keep)
        if len(text) <= max_chars:
            return text
    return text[: max_chars - 20].rstrip() + "\n_…truncated_\n"


def save(text: str, today: date) -> Path:
    path = packet_dir() / f"{today.isoformat()}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", type=date.fromisoformat, help="build for this date (default today)")
    ap.add_argument("--no-save", action="store_true", help="print only")
    args = ap.parse_args(argv)
    inp = gather(args.date)
    text = build_packet(inp)
    print(text)
    print(f"[{len(text)} chars]")
    if not args.no_save:
        print(f"saved {save(text, inp.today)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
