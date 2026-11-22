"""
The evaluator: is this edition fit to print?

Two layers, and every problem from either is phrased as an instruction the
writer can act on, because the revise loop (run.py) sends them back verbatim.

a) Deterministic checks (code, free, run first):
   - structure  the writer's schema + section/length rules (writer.validate_edition)
   - refs       every source_ref is a context ref; every link is a context url;
                a news item's link is the url of a story it cites
   - numbers    every number in an item appears in the facts (or titles/dates)
                of the refs it cites: 5.03 must be 5.03, 6-5 must be 6-5.
                Weekdays must match a cited item's date, today, or an earlier edition.
   - news       no story twice in one edition; an already-featured story must be
                framed as a follow-up; "as reported Tuesday" needs a real
                Tuesday edition; no 7+ word runs copied from a story's text
   - hygiene    no field names or refs leaking into the prose
b) The judge (Haiku 5.5, prompts/judge.md): scores accuracy, positive_tone,
   humor and coverage 1-5 with fix instructions. The judge scores; code decides
   pass/fail with THRESHOLDS.

An edition passes when (a) finds nothing and every score meets its threshold.

    uv run python -m agents.morning_brief.evaluators --fixture                   # write + evaluate the sample
    uv run python -m agents.morning_brief.evaluators --fixture --edition e.json  # evaluate a saved edition
    uv run python -m agents.morning_brief.evaluators --fixture --no-judge        # code checks only, no API call
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from agents.morning_brief import context as C
from agents.morning_brief.llm import call_tool, cost_usd, default_client
from agents.morning_brief.writer import Edition, render_context, validate_edition

JUDGE_PROMPT = Path(__file__).parent / "prompts" / "judge.md"
JUDGE_MODEL = os.getenv("ONS_JUDGE_MODEL", "claude-haiku-5-5")
JUDGE_EFFORT = os.getenv("ONS_JUDGE_EFFORT", "medium")
THRESHOLDS = {"accuracy": 4, "positive_tone": 4, "humor": 3, "coverage": 4}
COPY_RUN = 7          # this many words in a row from a story's title/summary = copying
ANALYZER = "morning_brief_judge"

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:,\d{3})*(?:\.\d+)?")
# "Monday" and "Monday's" name a day; plural "Mondays" is a figure of speech, not a date.
WEEKDAY_RE = re.compile(r"\b(" + "|".join(WEEKDAYS) + r")(?:'s)?\b")
CALLBACK_RE = re.compile(r"\bas (?:reported|noted|covered|featured)(?: here)?(?: on| last)? (" + "|".join(WEEKDAYS) + r")\b", re.I)
FOLLOWUP_RE = re.compile(r"\b(follow-?up|update|as (?:reported|noted|covered|featured)|earlier this week|returns? to)\b", re.I)
FIELD_RE = re.compile(r"\b[a-z]+_[a-z0-9_]+\b|\b(?:news|strava|pick|picks|cfb_game|nba|nhl|sugarwod|music|fitness|draft):[\w:.-]+")


# ── helpers ──────────────────────────────────────────────────────────────────

def _numbers(text: str) -> list[float]:
    return [float(m.group(0).replace(",", "")) for m in NUMBER_RE.finditer(text or "")]


def _values(obj: Any) -> list[Any]:
    if isinstance(obj, dict):
        return [v for x in obj.values() for v in _values(x)]
    if isinstance(obj, list):
        return [v for x in obj for v in _values(x)]
    return [obj]


def allowed_numbers(items: list[dict[str, Any]]) -> set[float]:
    """Every number a writer may quote from these items: numeric facts, numbers
    inside string facts ("6-5", "+10.0 (away fav)"), titles and dates, and list lengths."""
    out: set[float] = set()
    for it in items:
        for v in _values(it.get("facts", {})):
            if isinstance(v, bool) or v is None:
                continue
            if isinstance(v, (int, float)):
                out.add(float(v))
                out.add(abs(float(v)))
            elif isinstance(v, str):
                out.update(_numbers(v))
        for lst in it.get("facts", {}).values():
            if isinstance(lst, list):
                out.add(float(len(lst)))
        out.update(_numbers(it.get("title", "")))
        if it.get("date"):
            d = date.fromisoformat(it["date"])
            out.update({float(d.day), float(d.year), float(d.month)})
    return out


def _weekday(iso: str | None) -> str | None:
    return WEEKDAYS[date.fromisoformat(iso).weekday()] if iso else None


def _copied_run(text: str, source: str, n: int = COPY_RUN) -> str | None:
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    src = " " + " ".join(re.findall(r"[a-z0-9']+", (source or "").lower())) + " "
    for i in range(len(words) - n + 1):
        run = " ".join(words[i:i + n])
        if f" {run} " in src:
            return run
    return None


def _items(edition: dict[str, Any]):
    for s in edition.get("sections", []):
        for i, it in enumerate(s.get("items", []), 1):
            yield s["name"], i, it


def _where(section: str, i: int, it: dict) -> str:
    return f"{section} item {i} (\"{it.get('headline', '')[:45]}\")"


# ── a) deterministic checks ──────────────────────────────────────────────────

def check_refs(edition: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    refs, urls = C.refs(ctx), C.urls(ctx)
    problems = []
    for section, i, it in _items(edition):
        where = _where(section, i, it)
        unknown = [r for r in it["source_refs"] if r not in refs]
        if unknown:
            problems.append(f"{where}: source_refs {unknown} aren't in the context; cite only refs that exist.")
        if not it["source_refs"] and section != "Tip of the Day":
            problems.append(f"{where}: cite the refs this item's facts come from in source_refs.")
        link = it.get("link")
        if link and link not in urls:
            problems.append(f"{where}: link {link} isn't a url in the context; use a context url or null.")
        if section in ("Good News", "Science"):
            cited = [refs[r] for r in it["source_refs"] if r in refs]
            news = [c for c in cited if c["ref"].startswith("news:")]
            want = "good_news" if section == "Good News" else "science"
            if not news:
                problems.append(f"{where}: base it on a {want} story from the news context and cite its ref.")
            elif link not in {c.get("url") for c in news}:
                problems.append(f"{where}: set link to the cited story's url ({news[0].get('url')}).")
            if any(c["kind"] != want for c in news):
                problems.append(f"{where}: {section} needs a {want} story, not a {news[0]['kind']} one.")
    return problems


def check_numbers(edition: dict[str, Any], ctx: dict[str, Any], recent: list[dict] | None = None) -> list[str]:
    refs = C.refs(ctx)
    everything = allowed_numbers(list(refs.values()))
    today = ctx["date"]
    recent_days = {r["weekday"] for r in (recent or [])}
    problems = []

    def check(where: str, text: str, items: list[dict], numbers_ok: set[float]) -> None:
        bad = sorted({n for n in _numbers(text) if n not in numbers_ok})
        if bad:
            shown = ", ".join(f"{n:g}" for n in bad)
            problems.append(f"{where}: {shown} not found in the cited facts; copy numbers exactly from "
                            "the facts of the refs you cite (or cite the ref they come from).")
        days_ok = {_weekday(it.get("date")) for it in items} | {_weekday(it.get("featured_on")) for it in items}
        tomorrow = WEEKDAYS[(date.fromisoformat(today).weekday() + 1) % 7]
        days_ok |= {_weekday(today), tomorrow} | recent_days
        bad_days = sorted({m.group(1) for m in WEEKDAY_RE.finditer(text)} - days_ok)
        if bad_days:
            problems.append(f"{where}: {', '.join(bad_days)} doesn't match the date of anything it cites; "
                            "fix the day or cite the item it refers to.")

    for section, i, it in _items(edition):
        cited = [refs[r] for r in it["source_refs"] if r in refs]
        pool = allowed_numbers(cited) if cited else everything
        check(_where(section, i, it), f"{it['headline']} {it['body']}", cited or list(refs.values()), pool)
    check("Lead headline", edition.get("lead_headline", ""), list(refs.values()), everything)
    check("Masthead tagline", edition.get("masthead_tagline", ""), list(refs.values()), everything)
    return problems


def check_news(edition: dict[str, Any], ctx: dict[str, Any], recent: list[dict] | None = None) -> list[str]:
    refs = C.refs(ctx)
    recent_by_day = {r["weekday"]: r for r in (recent or [])}
    seen: dict[str, str] = {}
    problems = []
    for section, i, it in _items(edition):
        where = _where(section, i, it)
        text = f"{it['headline']} {it['body']}"
        for r in it["source_refs"]:
            item = refs.get(r)
            if not item or not r.startswith("news:"):
                continue
            if r in seen:
                problems.append(f"{where}: this story already ran in {seen[r]}; pick a different one.")
            seen.setdefault(r, where)
            if item.get("already_featured") and not FOLLOWUP_RE.search(text):
                problems.append(f"{where}: this story ran on {item.get('featured_on')}; frame it as a follow-up "
                                "(\"Follow-up:\" or \"as reported …\") or pick a fresh story.")
            for source_text in (item.get("title", ""), item["facts"].get("summary", "")):
                run = _copied_run(it["body"], source_text)
                if run:
                    problems.append(f"{where}: \"{run}\" is copied from the story; summarize in your own words.")
                    break
        for m in CALLBACK_RE.finditer(text):
            day = m.group(1).title()
            featured_days = {_weekday(refs[r].get("featured_on")) for r in it["source_refs"] if r in refs}
            if day not in recent_by_day and day not in featured_days:
                problems.append(f"{where}: \"{m.group(0)}\" points at an edition that doesn't exist; "
                                "drop the call-back or point at a real one.")
    return problems


def check_hygiene(edition: dict[str, Any]) -> list[str]:
    problems = []
    texts = [("Lead headline", edition.get("lead_headline", "")),
             ("Masthead tagline", edition.get("masthead_tagline", ""))]
    texts += [(_where(s, i, it), f"{it['headline']} {it['body']}") for s, i, it in _items(edition)]
    for where, text in texts:
        leaks = sorted(set(FIELD_RE.findall(text)))
        if leaks:
            problems.append(f"{where}: field names or refs in the prose ({', '.join(leaks)}); write them as plain words.")
    return problems


def deterministic_checks(edition: dict[str, Any], ctx: dict[str, Any],
                         recent: list[dict] | None = None) -> dict[str, list[str]]:
    structure = validate_edition(edition, ctx["date"])
    if any(p.startswith("Schema:") for p in structure):
        return {"structure": structure}          # the rest assumes a well-formed edition
    return {
        "structure": structure,
        "refs": check_refs(edition, ctx),
        "numbers": check_numbers(edition, ctx, recent),
        "news": check_news(edition, ctx, recent),
        "hygiene": check_hygiene(edition),
    }


# ── b) the judge ─────────────────────────────────────────────────────────────

def _criterion(desc: str) -> dict:
    return {"type": "object", "additionalProperties": False, "required": ["score", "reason"],
            "properties": {"score": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
                           "reason": {"type": "string"}}, "description": desc}


REVIEW_TOOL = {
    "name": "submit_review",
    "description": "Submit the scores and fix instructions for this edition.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [*THRESHOLDS, "fix_instructions"],
        "properties": {
            "accuracy": _criterion("Says only what the cited context supports."),
            "positive_tone": _criterion("Solutions-focused, upbeat, never saccharine or mean."),
            "humor": _criterion("Would the reader smile or laugh?"),
            "coverage": _criterion("All sections present and using the week's best stories."),
            "fix_instructions": {"type": "array", "items": {"type": "string"}},
        },
    },
}


@dataclass
class Judgement:
    scores: dict[str, int]
    reasons: dict[str, str]
    fix_instructions: list[str]
    model: str = JUDGE_MODEL
    usage: dict[str, int] = field(default_factory=dict)

    @property
    def failing(self) -> list[str]:
        return [k for k, floor in THRESHOLDS.items() if self.scores.get(k, 0) < floor]

    def problems(self) -> list[str]:
        if not self.failing:
            return []
        out = [f"Judge: {k} scored {self.scores[k]}/5 (needs {THRESHOLDS[k]}): {self.reasons[k]}" for k in self.failing]
        return out + [f"Judge fix: {f}" for f in self.fix_instructions]


def judge(edition: dict[str, Any], ctx: dict[str, Any], recent: list[dict] | None = None, *,
          client: Any = None, model: str = JUDGE_MODEL) -> Judgement:
    content = ("## The week's context\n\n" + render_context(ctx, recent or [])
               + "\n\n## Draft edition\n\n" + json.dumps(edition, ensure_ascii=False, indent=1)
               + "\n\nReview it and submit with submit_review.")
    data, usage = call_tool(
        client or default_client(), model=model, system=JUDGE_PROMPT.read_text(),
        messages=[{"role": "user", "content": content}], tool=REVIEW_TOOL, max_tokens=4000,
        effort=JUDGE_EFFORT, analyzer=ANALYZER, tables_read=["main_marts.brief_context_7d"],
    )
    return Judgement(scores={k: int(data[k]["score"]) for k in THRESHOLDS},
                     reasons={k: data[k]["reason"] for k in THRESHOLDS},
                     fix_instructions=list(data.get("fix_instructions", [])),
                     model=model, usage=usage)


# ── together ─────────────────────────────────────────────────────────────────

@dataclass
class Evaluation:
    checks: dict[str, list[str]]
    judgement: Judgement | None

    @property
    def check_problems(self) -> list[str]:
        return [p for probs in self.checks.values() for p in probs]

    @property
    def problems(self) -> list[str]:
        """Everything that failed, phrased as fixes: the writer's next feedback."""
        return self.check_problems + (self.judgement.problems() if self.judgement else [])

    @property
    def passed(self) -> bool:
        return not self.problems and self.judgement is not None

    @property
    def cost_usd(self) -> float:
        return self.judgement and cost_usd(self.judgement.model, self.judgement.usage) or 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "checks": self.checks,
                "judge": asdict(self.judgement) if self.judgement else None,
                "problems": self.problems}


def evaluate(edition: dict[str, Any], ctx: dict[str, Any], recent: list[dict] | None = None, *,
             client: Any = None, use_judge: bool = True) -> Evaluation:
    """Code checks always; the judge too (it's ~$0.001), so one revision can fix both kinds of problem.
    A schema failure skips the judge: there's nothing well-formed to grade."""
    checks = deterministic_checks(edition, ctx, recent)
    schema_broken = any(p.startswith("Schema:") for p in checks.get("structure", []))
    graded = judge(edition, ctx, recent, client=client) if use_judge and not schema_broken else None
    return Evaluation(checks, graded)


def report(ev: Evaluation) -> str:
    lines = []
    for name, probs in ev.checks.items():
        lines.append(f"{name:<10} {'ok' if not probs else f'{len(probs)} problem(s)'}")
        lines += [f"   ✗ {p}" for p in probs]
    if ev.judgement:
        j = ev.judgement
        lines.append("judge      " + "  ".join(f"{k} {j.scores[k]}/5" for k in THRESHOLDS)
                     + f"   (${cost_usd(j.model, j.usage):.4f})")
        lines += [f"   {k}: {j.reasons[k]}" for k in THRESHOLDS]
        lines += [f"   → {f}" for f in j.fix_instructions]
    else:
        lines.append("judge      skipped")
    lines.append("PASS" if ev.passed else "FAIL")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fixture", nargs="?", const="", default=None, help="context fixture (no value: committed sample)")
    p.add_argument("--edition", type=Path, help="evaluate this saved edition JSON instead of writing one")
    p.add_argument("--no-judge", action="store_true", help="code checks only (no API call)")
    args = p.parse_args(argv)

    from dotenv import load_dotenv
    load_dotenv()
    ctx = C.load_fixture(args.fixture) if args.fixture is not None else C.load_context()
    recent: list[dict] = []
    if args.fixture is None:
        from agents.morning_brief.writer import recent_editions
        recent = recent_editions(date.fromisoformat(ctx["date"]))
    if args.edition:
        saved = json.loads(args.edition.read_text())
        edition = {k: v for k, v in saved.get("edition", saved).items()
                   if not k.startswith("_")}   # fixture notes like "_comment"
    else:
        from agents.morning_brief.writer import to_markdown, write
        ed = write(ctx, recent=recent)
        edition = ed.data
        print(to_markdown(edition))
        print(f"-- writer ${ed.cost_usd:.4f} --\n")
    ev = evaluate(edition, ctx, recent, use_judge=not args.no_judge)
    print(report(ev))
    return 0 if ev.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
