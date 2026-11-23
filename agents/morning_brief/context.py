"""
The brief's view of the week: main_marts.brief_context_7d, grouped by domain.

brief_context_7d (dbt) is one row per item: a run, a pick, a game, a news story.
This module reads it read-only and returns a compact dict the writer can take
in one prompt and the evaluator can check against:

    {
      "date": "2026-11-21", "weekday": "Saturday", "built_for": "2026-11-21",
      "domains": {
        "fitness":   {"items": [{"ref", "date", "kind", "title", "url", "facts"}, ...],
                      "notes": ["..."]},
        "music": ..., "cfb_picks": ..., "cfb_games": ..., "team_games": ...,
        "news":      {"items": [... + "already_featured", "featured_on"], "notes": [...]}
      },
      "warnings": ["..."]
    }

`ref` is the id a brief's source_refs must use; refs(ctx) flattens the dict to
{ref: item} for the evaluator. Null facts are dropped to keep the prompt small.
News is capped per category, unfeatured and newest first.

A fixture is a saved copy of this dict, so the agent runs without the warehouse:

    uv run python -m agents.morning_brief.context                 # live, full JSON
    uv run python -m agents.morning_brief.context --summary       # counts + notes only
    uv run python -m agents.morning_brief.context --fixture       # committed sample
    uv run python -m agents.morning_brief.context --fixture 2026-11-21   # a saved capture
    uv run python -m agents.morning_brief.context --save-fixture  # capture today (gitignored)

The committed sample (tests/fixtures/morning_brief/context_sample.json) is made
up: the repo is public, so real captures stay under data/ (gitignored).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import duckdb

from api.store import data_dir, today_local
from agents.morning_brief.tools import DB_PATH, ROOT

DOMAINS = ["fitness", "music", "cfb_picks", "cfb_games", "team_games", "news"]
NEWS_PER_CATEGORY = 15          # most recent unfeatured first; keeps the prompt cheap
NEWS_SUMMARY_CHARS = 280

SAMPLE_FIXTURE = ROOT / "tests" / "fixtures" / "morning_brief" / "context_sample.json"


def fixture_dir() -> Path:
    return data_dir() / "ai" / "morning_brief" / "fixtures"


# ── building ─────────────────────────────────────────────────────────────────

def _compact(facts: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in facts.items() if v is not None}
    if isinstance(out.get("summary"), str) and len(out["summary"]) > NEWS_SUMMARY_CHARS:
        out["summary"] = out["summary"][:NEWS_SUMMARY_CHARS].rsplit(" ", 1)[0] + "…"
    return out


def _item(row: dict[str, Any]) -> dict[str, Any]:
    item = {
        "ref": row["ref"],
        "date": row["item_date"].isoformat() if row["item_date"] else None,
        "kind": row["kind"],
        "title": row["title"],
        "url": row["url"],
        "facts": _compact(json.loads(row["facts"]) if isinstance(row["facts"], str) else row["facts"]),
    }
    if row["domain"] == "news":
        item["already_featured"] = bool(row["already_featured"])
        item["featured_on"] = row["featured_on"].isoformat() if row["featured_on"] else None
    return {k: v for k, v in item.items() if v is not None or k in ("date",)}


def _cap_news(items: list[dict]) -> list[dict]:
    by_cat: dict[str, list[dict]] = {}
    for it in items:
        by_cat.setdefault(it["kind"], []).append(it)
    kept = []
    for cat in sorted(by_cat):
        ranked = sorted(by_cat[cat], key=lambda i: (i.get("already_featured", False),
                                                     -(date.fromisoformat(i["date"]).toordinal() if i["date"] else 0)))
        kept += ranked[:NEWS_PER_CATEGORY]
    return kept


def _notes(domain: str, items: list[dict], today: date) -> list[str]:
    """Deterministic hints about gaps, so the writer doesn't invent around them."""
    notes: list[str] = []
    week = next((i for i in items if i["kind"] == "week_summary"), None)
    if domain == "music" and week:
        newest = week["facts"].get("newest_play_date")
        if not week["facts"].get("plays"):
            notes.append(
                f"No listening data this week (Spotify export is refreshed a few times a year; "
                f"newest play {newest or 'unknown'}). Don't describe this week's listening; "
                "the Daily 10 playlist, if present, is fair game."
            )
    if domain == "fitness" and week:
        f = week["facts"]
        if f.get("newest_crossfit_date") is None and not any(i["kind"] == "crossfit" for i in items):
            notes.append("CrossFit (SugarWOD) is a manual export; no workouts this week doesn't mean none were done.")
        if f.get("run_streak_days") == 0:
            notes.append("No active run streak (no run today or yesterday). Don't invent one.")
    if domain == "cfb_picks":
        if any(i["facts"].get("outcome") == "pending" for i in items if i["kind"] == "pick"):
            notes.append("Some picks are pending: their games haven't been graded. Don't call them wins or losses.")
    if domain in ("cfb_games", "team_games"):
        if any(i["kind"] == "upcoming_game" and i["date"] == today.isoformat() for i in items):
            notes.append("A followed team plays today; preview it, don't report a result.")
    if domain == "news" and items and all(i.get("already_featured") for i in items):
        notes.append("Every story here already ran; only use one as an explicit follow-up.")
    if not items:
        notes.append("Nothing in this domain this week.")
    return notes


def build_context(rows: list[dict[str, Any]], today: date) -> dict[str, Any]:
    """Group brief_context_7d rows (as dicts) into the brief's context."""
    domains: dict[str, dict] = {d: {"items": [], "notes": []} for d in DOMAINS}
    built_for = None
    for row in rows:
        built_for = built_for or row.get("built_for")
        d = row["domain"]
        domains.setdefault(d, {"items": [], "notes": []})["items"].append(_item(row))

    domains["news"]["items"] = _cap_news(domains["news"]["items"])
    for d, block in domains.items():
        block["notes"] = _notes(d, block["items"], today)

    warnings = []
    built = built_for.isoformat() if hasattr(built_for, "isoformat") else built_for
    if built and built != today.isoformat():
        warnings.append(f"brief_context_7d was built for {built}, not {today}; dbt hasn't run today.")
    if not rows:
        warnings.append("brief_context_7d is empty.")

    return {
        "date": today.isoformat(),
        "weekday": today.strftime("%A"),
        "built_for": built,
        "domains": domains,
        "warnings": warnings,
    }


def load_context(today: date | None = None, db_path: Path | str | None = None) -> dict[str, Any]:
    """Read brief_context_7d read-only (safe while the API holds the warehouse)."""
    today = today or today_local()
    try:
        con = duckdb.connect(str(db_path or DB_PATH), read_only=True)
    except duckdb.IOException as e:
        raise SystemExit(f"Can't open the warehouse read-only ({e}). Is a sync writing right now?") from e
    try:
        cur = con.execute("SELECT * FROM main_marts.brief_context_7d ORDER BY domain, item_date, ref")
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    except duckdb.CatalogException as e:
        raise SystemExit("main_marts.brief_context_7d doesn't exist; run dbt first.") from e
    finally:
        con.close()
    return build_context(rows, today)


# ── fixtures and helpers ─────────────────────────────────────────────────────

def load_fixture(name: str | None = None) -> dict[str, Any]:
    """No name: the committed sample. A date or name: a saved capture. A path: that file."""
    if not name:
        path = SAMPLE_FIXTURE
    elif Path(name).suffix == ".json" and Path(name).exists():
        path = Path(name)
    else:
        path = fixture_dir() / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"No fixture at {path}")
    return json.loads(path.read_text())


def save_fixture(ctx: dict[str, Any]) -> Path:
    path = fixture_dir() / f"{ctx['date']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ctx, indent=2, ensure_ascii=False))
    return path


def refs(ctx: dict[str, Any]) -> dict[str, dict]:
    """{ref: item} across every domain: what source_refs may point at."""
    return {it["ref"]: it for block in ctx["domains"].values() for it in block["items"]}


def urls(ctx: dict[str, Any]) -> set[str]:
    return {it["url"] for it in refs(ctx).values() if it.get("url")}


def summary(ctx: dict[str, Any]) -> str:
    lines = [f"{ctx['date']} ({ctx['weekday']}), built_for {ctx['built_for']}"]
    for d, block in ctx["domains"].items():
        kinds: dict[str, int] = {}
        for it in block["items"]:
            kinds[it["kind"]] = kinds.get(it["kind"], 0) + 1
        lines.append(f"  {d:<11} {len(block['items']):>3}  " + ", ".join(f"{k} {n}" for k, n in sorted(kinds.items())))
        lines += [f"      note: {n}" for n in block["notes"]]
    lines += [f"  WARNING: {w}" for w in ctx["warnings"]]
    size = len(json.dumps(ctx, ensure_ascii=False))
    lines.append(f"  ~{size // 4:,} tokens as JSON ({size:,} chars)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fixture", nargs="?", const="", default=None,
                   help="load a fixture instead of the warehouse (no value: the committed sample)")
    p.add_argument("--save-fixture", action="store_true", help="save today's live context (gitignored)")
    p.add_argument("--summary", action="store_true", help="print counts and notes, not the JSON")
    p.add_argument("--date", type=date.fromisoformat, help="treat this day as today (live only)")
    args = p.parse_args(argv)

    ctx = load_fixture(args.fixture) if args.fixture is not None else load_context(args.date)
    print(summary(ctx) if args.summary else json.dumps(ctx, indent=2, ensure_ascii=False))
    if args.save_fixture:
        if args.fixture is not None:
            print("--save-fixture saves live context; ignored with --fixture", file=sys.stderr)
        else:
            print(f"saved {save_fixture(ctx)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
