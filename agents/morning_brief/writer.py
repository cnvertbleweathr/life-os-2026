"""
Stage 2 of the morning-brief agent: the writer.

One LLM call. In: the day's snapshot. Out: a Draft with a headline, the brief,
and a list of claims, each quoting a piece of the brief and naming the fact
ids it rests on. Those claims are what stage 3's grounding check verifies.

Two ideas worth noticing:

- Structured output through a tool call. The model answers by "calling"
  submit_brief, so the brief arrives as JSON matching our schema rather than
  prose we'd have to parse. (Forcing the tool with tool_choice isn't allowed
  on every model, so we ask for it and nudge once if the model forgets.)
- The writer takes optional `feedback` and the previous draft. Stage 1 doesn't
  use them, but stage 4's revise loop is just: write, evaluate, call write()
  again with what failed.

    uv run python -m agents.morning_brief.writer                  # today's live snapshot
    uv run python -m agents.morning_brief.writer --snapshot data/ai/morning_brief/snapshots/2026-11-15.json
    uv run python -m agents.morning_brief.writer --show-prompt    # see what the model sees, no API call
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from agents.morning_brief.snapshot import build_snapshot

PROMPT_PATH = Path(__file__).parent / "prompts" / "writer.md"
MODEL = os.getenv("ONS_BRIEF_MODEL", "claude-sonnet-5-5")
MAX_TOKENS = 1500

SUBMIT_TOOL = {
    "name": "submit_brief",
    "description": "Submit the finished morning brief.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {"type": "string", "description": "One line, under 12 words."},
            "brief": {"type": "string", "description": "The brief: 120-200 words, 2-3 short paragraphs."},
            "claims": {
                "type": "array",
                "description": "One entry per factual statement in the brief.",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "The statement, copied exactly from the brief."},
                        "fact_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["text", "fact_ids"],
                },
            },
        },
        "required": ["headline", "brief", "claims"],
    },
}


@dataclass
class Claim:
    text: str
    fact_ids: list[str]


@dataclass
class Draft:
    headline: str
    brief: str
    claims: list[Claim]
    model: str = MODEL
    usage: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def render_snapshot(snapshot: dict[str, Any]) -> str:
    """Turn the snapshot into the plain-text fact sheet the model reads."""
    out = [f"Today is {snapshot['weekday']}, {snapshot['date']}.", ""]
    for name, s in snapshot["sections"].items():
        if s["error"]:
            out += [f"## {name}: ERROR (no data)", ""]
            continue
        flag = f"STALE, newest data {s['as_of']}" if s["stale"] else f"as of {s['as_of'] or 'n/a'}"
        out.append(f"## {name} ({flag})")
        for key, value in s["facts"].items():
            out.append(f"- {name}.{key}: {json.dumps(value, default=str)}")
        if not s["facts"]:
            out.append("- (no facts)")
        for note in s["notes"]:
            out.append(f"Note: {note}")
        out.append("")
    return "\n".join(out)


def build_messages(snapshot: dict[str, Any], feedback: list[str] | None = None,
                   previous: Draft | None = None) -> list[dict[str, Any]]:
    content = "Here are today's facts.\n\n" + render_snapshot(snapshot)
    if previous and feedback:
        content += (
            "\n\nYour previous draft failed review.\n\nPrevious draft:\n"
            + json.dumps({"headline": previous.headline, "brief": previous.brief}, indent=2)
            + "\n\nWhat to fix:\n" + "\n".join(f"- {f}" for f in feedback)
            + "\n\nWrite a new draft that fixes these problems and keeps what worked."
        )
    content += "\n\nWrite the brief and submit it with submit_brief."
    return [{"role": "user", "content": content}]


def write(snapshot: dict[str, Any], *, feedback: list[str] | None = None,
          previous: Draft | None = None, client: Any = None, model: str = MODEL) -> Draft:
    if client is None:
        import anthropic   # imported here so tests and --show-prompt don't need a key
        client = anthropic.Anthropic()

    # Some models reject a forced tool_choice, so the model picks the tool
    # itself ("auto"). If it answers in prose instead, nudge it once.
    messages = build_messages(snapshot, feedback, previous)
    usage = {"input_tokens": 0, "output_tokens": 0}
    call = None
    for attempt in range(2):
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=PROMPT_PATH.read_text(),
            tools=[SUBMIT_TOOL],
            tool_choice={"type": "auto"},
            messages=messages,
        )
        usage["input_tokens"] += response.usage.input_tokens
        usage["output_tokens"] += response.usage.output_tokens
        call = next((b for b in response.content if b.type == "tool_use"), None)
        if call:
            break
        messages = messages + [
            {"role": "assistant", "content": response.content},
            {"role": "user", "content": "Submit the brief with the submit_brief tool, not as plain text."},
        ]
    if call is None:
        raise RuntimeError("The writer never called submit_brief.")
    data = call.input
    return Draft(
        headline=data["headline"].strip(),
        brief=data["brief"].strip(),
        claims=[Claim(c["text"], list(c.get("fact_ids", []))) for c in data.get("claims", [])],
        model=model,
        usage=usage,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", type=date.fromisoformat)
    p.add_argument("--snapshot", type=Path, help="use a saved snapshot instead of building one")
    p.add_argument("--show-prompt", action="store_true", help="print the prompt and stop")
    p.add_argument("--json", action="store_true", help="print the whole draft as JSON")
    args = p.parse_args(argv)

    if args.snapshot:
        snapshot = json.loads(args.snapshot.read_text())
    else:
        snapshot = build_snapshot(args.date)
    if args.show_prompt:
        print(PROMPT_PATH.read_text(), "\n---\n", build_messages(snapshot)[0]["content"])
        return 0

    from dotenv import load_dotenv   # the repo's .env holds ANTHROPIC_API_KEY
    load_dotenv()
    draft = write(snapshot)
    if args.json:
        print(json.dumps(draft.to_dict(), indent=2))
    else:
        print(f"# {draft.headline}\n\n{draft.brief}\n")
        print(f"-- {len(draft.claims)} claims --")
        for c in draft.claims:
            print(f"  [{', '.join(c.fact_ids)}] {c.text}")
        print(f"-- tokens: {draft.usage} --")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
