"""
The writer: one LLM call that turns the week's context into a newspaper edition.

In: context.py's dict (live or fixture) plus the headlines of recent saved
editions, so "as reported Tuesday" can point at something real.
Out: an Edition, validated against EDITION_SCHEMA:

    { date, masthead_tagline, lead_headline,
      sections: [{ name, items: [{ headline, body, source_refs: [...], link }] }] }

Sections, in order: Your Week, Sports Desk, Good News, Science, Tip of the Day.

The model answers by "calling" submit_edition (strict schema), so the edition
arrives as JSON. Code then checks what a JSON schema can't say cheaply (every
section once and in order, item counts, lengths) and records problems on the
Edition rather than raising: stage 4's loop sends them back as feedback.
Whether the facts are right is the evaluator's job, not this module's.

    uv run python -m agents.morning_brief.writer --fixture            # committed sample, one API call
    uv run python -m agents.morning_brief.writer --fixture 2026-11-21 # a saved capture
    uv run python -m agents.morning_brief.writer                      # live context
    uv run python -m agents.morning_brief.writer --fixture --show-prompt   # no API call
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import jsonschema

from api.store import data_dir
from agents.morning_brief import context as C
from agents.morning_brief.llm import call_tool, cost_usd, default_client

PROMPT_PATH = Path(__file__).parent / "prompts" / "writer.md"
MODEL = os.getenv("ONS_BRIEF_MODEL", "claude-sonnet-5-5")
EFFORT = os.getenv("ONS_BRIEF_EFFORT", "medium")   # Sonnet 5.5 defaults to high; medium keeps thinking cheap
MAX_TOKENS = 12000                                  # edition ~2K tokens + thinking; truncation fails loudly
ANALYZER = "morning_brief_writer"

SECTIONS = ["Your Week", "Sports Desk", "Good News", "Science", "Tip of the Day"]
ITEM_COUNTS = {"Your Week": (1, 3), "Sports Desk": (2, 4), "Good News": (2, 3),
               "Science": (1, 2), "Tip of the Day": (1, 1)}
BODY_WORDS = (30, 90)
HEADLINE_WORDS = 12
LEAD_WORDS = 14

ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "body": {"type": "string"},
        "source_refs": {"type": "array", "items": {"type": "string"}},
        "link": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["headline", "body", "source_refs", "link"],
    "additionalProperties": False,
}
EDITION_SCHEMA = {
    "type": "object",
    "properties": {
        "date": {"type": "string", "description": "The edition date, YYYY-MM-DD."},
        "masthead_tagline": {"type": "string"},
        "lead_headline": {"type": "string"},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "enum": SECTIONS},
                    "items": {"type": "array", "items": ITEM_SCHEMA},
                },
                "required": ["name", "items"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["date", "masthead_tagline", "lead_headline", "sections"],
    "additionalProperties": False,
}
SUBMIT_TOOL = {
    "name": "submit_edition",
    "description": "Submit the finished edition of the morning paper.",
    "strict": True,
    "input_schema": EDITION_SCHEMA,
}


@dataclass
class Edition:
    data: dict[str, Any]
    problems: list[str] = field(default_factory=list)   # structural; fed back on revision
    model: str = MODEL
    usage: dict[str, int] = field(default_factory=dict)

    @property
    def cost_usd(self) -> float:
        return cost_usd(self.model, self.usage)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── validation ───────────────────────────────────────────────────────────────

def _words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def validate_edition(data: dict[str, Any], today: str | None = None) -> list[str]:
    """Structural problems, each phrased as a fix. Empty list = valid."""
    problems = [f"Schema: {e.message} at {'/'.join(map(str, e.absolute_path)) or 'top level'}."
                for e in jsonschema.Draft202012Validator(EDITION_SCHEMA).iter_errors(data)]
    if problems:
        return problems
    if today and data["date"] != today:
        problems.append(f"Set date to {today} (got {data['date']}).")
    if _words(data["lead_headline"]) > LEAD_WORDS:
        problems.append(f"Shorten the lead headline to under {LEAD_WORDS} words.")
    names = [s["name"] for s in data["sections"]]
    if names != SECTIONS:
        problems.append(f"Sections must be exactly, in order: {', '.join(SECTIONS)} (got {', '.join(names) or 'none'}).")
    for s in data["sections"]:
        lo, hi = ITEM_COUNTS.get(s["name"], (1, 9))
        if not lo <= len(s["items"]) <= hi:
            problems.append(f"{s['name']} needs {lo}–{hi} items (has {len(s['items'])}).")
        for i, it in enumerate(s["items"], 1):
            where = f"{s['name']} item {i} (\"{it['headline'][:40]}\")"
            if _words(it["headline"]) > HEADLINE_WORDS:
                problems.append(f"{where}: shorten the headline to under {HEADLINE_WORDS} words.")
            n = _words(it["body"])
            if not BODY_WORDS[0] <= n <= BODY_WORDS[1]:
                problems.append(f"{where}: body is {n} words; make it {BODY_WORDS[0]}–{BODY_WORDS[1]}.")
            if s["name"] in ("Good News", "Science") and not it["link"]:
                problems.append(f"{where}: news items need the story's url in link.")
    return problems


# ── prompt ───────────────────────────────────────────────────────────────────

def brief_dir() -> Path:
    return data_dir() / "brief"


def recent_editions(today: date, days: int = 6) -> list[dict[str, Any]]:
    """Headlines of saved editions from the past week (published or flagged), oldest first."""
    out = []
    for d in range(days, 0, -1):
        day = today - timedelta(days=d)
        path = brief_dir() / f"{day.isoformat()}.json"
        if not path.exists():
            continue
        try:
            saved = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        ed = saved.get("edition", saved)
        out.append({
            "date": day.isoformat(), "weekday": day.strftime("%A"),
            "lead_headline": ed.get("lead_headline"),
            "stories": [{"section": s.get("name"), "headline": it.get("headline"), "link": it.get("link")}
                        for s in ed.get("sections", []) for it in s.get("items", [])],
        })
    return out


def render_context(ctx: dict[str, Any], recent: list[dict[str, Any]]) -> str:
    lines = [f"Today is {ctx['weekday']}, {ctx['date']}. The context covers the last 7 days "
             "(and the coming week's games).", ""]
    for w in ctx.get("warnings", []):
        lines.append(f"WARNING: {w}")
    for name, block in ctx["domains"].items():
        lines.append(f"## {name}")
        for n in block["notes"]:
            lines.append(f"Note: {n}")
        for it in block["items"]:
            lines.append(json.dumps(it, ensure_ascii=False, separators=(",", ":")))
        if not block["items"]:
            lines.append("(nothing)")
        lines.append("")
    lines.append("## Recent editions")
    if recent:
        for r in recent:
            lines.append(json.dumps(r, ensure_ascii=False, separators=(",", ":")))
    else:
        lines.append("(none saved yet: no call-backs to earlier editions)")
    return "\n".join(lines)


def build_messages(ctx: dict[str, Any], recent: list[dict[str, Any]], *,
                   feedback: list[str] | None = None, previous: Edition | None = None) -> list[dict]:
    content = "Here is this week's context.\n\n" + render_context(ctx, recent)
    if previous is not None and feedback:
        content += (
            "\n\nYour previous draft failed review.\n\nPrevious draft:\n"
            + json.dumps(previous.data, ensure_ascii=False, indent=1)
            + "\n\nFix all of these:\n" + "\n".join(f"- {f}" for f in feedback)
            + "\n\nResubmit the whole edition."
        )
    content += f"\n\nWrite edition {ctx['date']} and submit it with submit_edition."
    return [{"role": "user", "content": content}]


# ── writing ──────────────────────────────────────────────────────────────────

def write(ctx: dict[str, Any], *, feedback: list[str] | None = None, previous: Edition | None = None,
          recent: list[dict[str, Any]] | None = None, client: Any = None, model: str = MODEL,
          effort: str | None = EFFORT) -> Edition:
    today = date.fromisoformat(ctx["date"])
    recent = recent_editions(today) if recent is None else recent
    data, usage = call_tool(
        client or default_client(),
        model=model,
        system=PROMPT_PATH.read_text(),
        messages=build_messages(ctx, recent, feedback=feedback, previous=previous),
        tool=SUBMIT_TOOL,
        max_tokens=MAX_TOKENS,
        effort=effort,
        analyzer=ANALYZER,
        tables_read=["main_marts.brief_context_7d"],
    )
    return Edition(data=data, problems=validate_edition(data, ctx["date"]), model=model, usage=usage)


def to_markdown(edition: dict[str, Any]) -> str:
    d = date.fromisoformat(edition["date"])
    out = [f"# The ONS Morning Edition", f"*{edition['masthead_tagline']}*",
           f"**{d.strftime('%A, %B')} {d.day}, {d.year}**", "", f"## {edition['lead_headline']}", ""]
    for s in edition["sections"]:
        out += [f"### {s['name']}", ""]
        for it in s["items"]:
            out.append(f"**{it['headline']}**  ")
            out.append(it["body"] + (f" [Read more]({it['link']})" if it.get("link") else ""))
            out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fixture", nargs="?", const="", default=None, help="use a fixture (no value: committed sample)")
    p.add_argument("--show-prompt", action="store_true", help="print the prompt and stop (no API call)")
    p.add_argument("--json", action="store_true", help="print the edition JSON instead of markdown")
    args = p.parse_args(argv)

    ctx = C.load_fixture(args.fixture) if args.fixture is not None else C.load_context()
    recent = [] if args.fixture is not None else None   # fixtures don't see real saved editions
    if args.show_prompt:
        msgs = build_messages(ctx, recent if recent is not None else recent_editions(date.fromisoformat(ctx["date"])))
        print(PROMPT_PATH.read_text(), "\n---\n", msgs[0]["content"])
        return 0

    from dotenv import load_dotenv   # the repo's .env holds ANTHROPIC_API_KEY
    load_dotenv()
    ed = write(ctx, recent=recent)
    print(json.dumps(ed.data, indent=2, ensure_ascii=False) if args.json else to_markdown(ed.data))
    print(f"\n-- {ed.model}, effort {EFFORT}: {ed.usage['input_tokens']:,} in / "
          f"{ed.usage['output_tokens']:,} out, ${ed.cost_usd:.4f} --")
    print("-- structure: OK --" if not ed.problems else "-- structural problems:\n" + "\n".join(f"   - {x}" for x in ed.problems))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
