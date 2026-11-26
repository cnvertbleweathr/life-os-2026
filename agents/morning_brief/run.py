"""
The morning brief, end to end: context → write → evaluate → revise → save.

    context.py ──► writer ──► evaluators ──pass──► save data/brief/<date>.json + .md
                     ▲            │                 └─► record_featured(news links)
                     └─ feedback ◄┘ fail (max 2 revisions)
                                  │ still failing
                                  ▼
                        save flagged needs_review (best draft), record nothing

Every problem the evaluator reports goes back to the writer verbatim. If the
edition still fails after MAX_REVISIONS, the best attempt (fewest code
problems, then highest judge total) is saved with status "needs_review", and
its stories are not recorded as featured, so they stay fresh for tomorrow.

    uv run python -m agents.morning_brief.run                 # today, live; saves and records featured
    uv run python -m agents.morning_brief.run --dry-run       # full loop, prints, writes nothing
    uv run python -m agents.morning_brief.run --fixture       # committed sample; saves under fixture_runs/
    uv run python -m agents.morning_brief.run --force         # redo a day that's already published
    uv run python -m agents.morning_brief.run --print         # also print it (weekdays; needs_review too)
    uv run python -m agents.morning_brief.run --record-featured 2026-11-22   # retry recording after a lock error

Exit codes: 0 published (or already published), 2 saved as needs_review, 1 error.
record_featured writes the warehouse: run it when nothing else holds the DuckDB
write lock (daily_sync runs this step while the API is stopped). If the lock is
taken, the edition is still saved and `featured_recorded` is false; use
--record-featured to retry.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

from api.store import data_dir, now_local
from agents.morning_brief import context as C
from agents.morning_brief.evaluators import THRESHOLDS, Evaluation, evaluate
from agents.morning_brief.llm import BudgetExceeded
from agents.morning_brief.writer import Edition, brief_dir, recent_editions, to_markdown, write

MAX_REVISIONS = 2
NEWS_SECTIONS = ("Good News", "Science")
# No new revision starts after this; the best attempt is saved instead. Keeps a
# stalled run inside daily_sync's step timeout (900s) with a result on disk.
DEADLINE_S = 480


# ── the loop ─────────────────────────────────────────────────────────────────

def _rank(ev: Evaluation) -> tuple[int, int]:
    """Lower is better: fewest code problems, then highest judge total."""
    total = sum(ev.judgement.scores.values()) if ev.judgement else 0
    return (len(ev.check_problems), -total)


def run_loop(ctx: dict[str, Any], recent: list[dict], *, client: Any = None, judge_client: Any = None,
             max_revisions: int = MAX_REVISIONS, log=print, deadline_s: float = DEADLINE_S,
             clock=time.monotonic) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    previous: Edition | None = None
    feedback: list[str] | None = None
    best: tuple[Edition, Evaluation] | None = None
    stopped_early = None
    started = clock()

    for n in range(max_revisions + 1):
        if n > 0 and clock() - started > deadline_s:
            stopped_early = "deadline"
            log(f"  stopping: {deadline_s:.0f}s deadline passed; keeping the best attempt so far")
            break
        label = "draft" if n == 0 else f"revision {n}"
        ed = write(ctx, feedback=feedback, previous=previous, recent=recent, client=client)
        ev = evaluate(ed.data, ctx, recent, client=judge_client)
        cost = round(ed.cost_usd + ev.cost_usd, 6)
        scores = ev.judgement.scores if ev.judgement else None
        attempts.append({
            "attempt": n, "passed": ev.passed, "scores": scores,
            "problems": ev.problems, "cost_usd": cost,
            "tokens": {"writer": ed.usage, "judge": ev.judgement.usage if ev.judgement else None},
        })
        log(f"  {label:<11} {'PASS' if ev.passed else 'FAIL'}  "
            + ("  ".join(f"{k} {v}" for k, v in scores.items()) if scores else "judge skipped")
            + f"  code problems {len(ev.check_problems)}  ${cost:.4f}")
        if best is None or ev.passed or _rank(ev) < _rank(best[1]):
            best = (ed, ev)
        if ev.passed:
            break
        previous, feedback = ed, ev.problems

    ed, ev = best
    return {
        "status": "published" if ev.passed else "needs_review",
        "edition": ed.data,
        "evaluation": ev.to_dict(),
        "revisions": len(attempts) - 1,
        "stopped_early": stopped_early,
        "attempts": attempts,
        "cost_usd": round(sum(a["cost_usd"] for a in attempts), 6),
        "models": {"writer": ed.model, "judge": ev.judgement.model if ev.judgement else None},
    }


# ── saving ───────────────────────────────────────────────────────────────────

def news_links(edition: dict[str, Any]) -> list[tuple[str, str]]:
    return [(it["link"], s["name"]) for s in edition["sections"] if s["name"] in NEWS_SECTIONS
            for it in s["items"] if it.get("link")]


def to_preview(result: dict[str, Any]) -> str:
    head = ""
    if result["status"] == "needs_review":
        problems = "\n".join(f"> - {p}" for p in result["evaluation"]["problems"][:12])
        head = (f"> **NEEDS REVIEW**: failed evaluation after {result['revisions']} revision(s). "
                f"Not recorded as featured.\n>\n{problems}\n\n")
    scores = (result["evaluation"].get("judge") or {}).get("scores") or {}
    foot = (f"\n---\n*{result['status']} · revisions {result['revisions']} · "
            + " · ".join(f"{k} {v}/5" for k, v in scores.items())
            + f" · ${result['cost_usd']:.4f}*\n")
    return head + to_markdown(result["edition"]) + foot


def save(result: dict[str, Any], folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{result['date']}.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    path.with_suffix(".md").write_text(to_preview(result))
    return path


def record(result: dict[str, Any], path: Path | None = None) -> None:
    """record_featured for a published edition; notes the outcome on the result (and file)."""
    from agents.morning_brief.featured import record_featured
    links = news_links(result["edition"])
    try:
        added = record_featured(links, date.fromisoformat(result["date"]))
        result.update(featured_recorded=True, featured_links=len(links), featured_added=added, featured_error=None)
    except Exception as e:   # usually the DuckDB write lock (API running)
        result.update(featured_recorded=False, featured_error=f"{type(e).__name__}: {e}")
    if path:
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))


# ── entry points ─────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fixture", nargs="?", const="", default=None, help="use a fixture (no value: committed sample)")
    p.add_argument("--dry-run", action="store_true", help="run the loop and print; save nothing, record nothing")
    p.add_argument("--force", action="store_true", help="rerun even if today's edition is already published")
    p.add_argument("--record-featured", metavar="DATE", help="retry record_featured for a saved edition and exit")
    p.add_argument("--max-revisions", type=int, default=MAX_REVISIONS)
    p.add_argument("--print", dest="print_it", action="store_true",
                   help="print the live edition, even a needs_review one (weekdays only; see print_edition.py)")
    args = p.parse_args(argv)

    if args.record_featured:
        path = brief_dir() / f"{args.record_featured}.json"
        result = json.loads(path.read_text())
        if result["status"] != "published":
            print(f"{path.name} is {result['status']}; only published editions are recorded.")
            return 1
        record(result, path)
        print(f"featured_recorded={result['featured_recorded']} {result.get('featured_error') or ''}")
        return 0 if result["featured_recorded"] else 1

    from dotenv import load_dotenv   # the repo's .env holds ANTHROPIC_API_KEY
    load_dotenv()

    fixture = args.fixture is not None
    ctx = C.load_fixture(args.fixture) if fixture else C.load_context()
    today = date.fromisoformat(ctx["date"])
    folder = data_dir() / "ai" / "morning_brief" / "fixture_runs" if fixture else brief_dir()

    existing = folder / f"{today}.json"
    if not (args.force or args.dry_run) and existing.exists():
        if json.loads(existing.read_text()).get("status") == "published":
            print(f"{existing} is already published; use --force to redo it.")
            return 0

    recent = [] if fixture else recent_editions(today)
    for w in ctx.get("warnings", []):
        print(f"warning: {w}", file=sys.stderr)
    print(f"Morning brief {today} ({'fixture' if fixture else 'live'}{', dry run' if args.dry_run else ''}): "
          f"{sum(len(b['items']) for b in ctx['domains'].values())} context items, {len(recent)} recent editions")

    started = time.monotonic()
    try:
        result = run_loop(ctx, recent, max_revisions=args.max_revisions)
    except BudgetExceeded as e:
        print(f"Not written: {e}", file=sys.stderr)
        return 1
    result = {"date": today.isoformat(), "generated_at": now_local().isoformat(timespec="seconds"),
              "source": f"fixture:{args.fixture or 'sample'}" if fixture else "live",
              "context_built_for": ctx.get("built_for"), "context_warnings": ctx.get("warnings", []),
              **result, "duration_s": round(time.monotonic() - started, 1)}

    print(f"\n{result['status'].upper()} after {result['revisions']} revision(s), "
          f"${result['cost_usd']:.4f}, {result['duration_s']}s")
    if args.dry_run:
        print("\n" + to_preview(result))
        return 0 if result["status"] == "published" else 2

    path = save(result, folder)
    print(f"saved {path} (+ .md)")
    if result["status"] == "published" and not fixture:
        record(result, path)
        print(f"featured: {result.get('featured_added', 0)} new of {result.get('featured_links', 0)} links"
              if result["featured_recorded"] else f"featured NOT recorded: {result['featured_error']} "
              f"(retry: python -m agents.morning_brief.run --record-featured {today})")
    elif result["status"] == "needs_review":
        print("needs review: not recorded as featured")
    if args.print_it and not fixture:
        try:
            from agents.morning_brief.print_edition import print_edition
            out = print_edition(path, auto=True)
            print(f"print: job {out['job']}" if out["printed"] else f"print: skipped ({out['reason']})")
        except Exception as e:   # a jammed or sleeping printer must not fail the brief
            print(f"print failed: {type(e).__name__}: {e}", file=sys.stderr)
    return 0 if result["status"] == "published" else 2


if __name__ == "__main__":
    raise SystemExit(main())
