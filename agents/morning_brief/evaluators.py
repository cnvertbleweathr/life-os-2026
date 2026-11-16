"""
Stage 3 of the morning-brief agent: the evaluators.

Three checks, cheapest first. Each returns a list of problems written as
instructions the writer can act on, because in stage 4 these problems become
the writer's feedback.

1. grounding (code): every claim quotes the brief, cites real fact ids, and
   every number, date, weekday and time in it appears in the facts it cites.
   Numbers, dates and times outside any claim are flagged as uncited.
2. style (code): length, shape, and the voice rules that a regex can check.
3. tone (LLM judge): funny, kind, light, voice, scored 1-5 against
   prompts/judge.md. The judge scores; code decides pass/fail, using the
   thresholds below. Tune them in stage 5 once you've rated briefs yourself.

The code checks catch "wrong", which a model judge is unreliable at. The judge
catches "accurate but not funny", which code can't see. What none of them
catch: a claim that cites the right numbers but says something untrue about
them ("5.1 miles yesterday" when the run was Tuesday is caught by the weekday
check, but "your best week ever" is not). That's what your own ratings in
stage 5 are for.

    uv run python -m agents.morning_brief.evaluators              # write today's brief, then evaluate it
    uv run python -m agents.morning_brief.evaluators --no-tone    # skip the judge's API call
    uv run python -m agents.morning_brief.evaluators --draft d.json --snapshot s.json
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

from agents.morning_brief.llm import call_tool, default_client
from agents.morning_brief.snapshot import build_snapshot, facts as flat_facts
from agents.morning_brief.writer import Claim, Draft

JUDGE_PROMPT = Path(__file__).parent / "prompts" / "judge.md"
JUDGE_MODEL = os.getenv("ONS_JUDGE_MODEL", "claude-haiku-5-5")
THRESHOLDS = {"funny": 3, "kind": 4, "light": 3, "voice": 4}
WORDS = (120, 200)


# ── 1. Grounding ─────────────────────────────────────────────────────────────

NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
WEEKDAYS = "monday tuesday wednesday thursday friday saturday sunday".split()

TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\s?([ap])\.?m\.?\b", re.I)
DATE_RE = re.compile(r"\b(" + "|".join(MONTHS) + r")[a-z]*\.?\s+(\d{1,2})\b(?!:)", re.I)
WEEKDAY_RE = re.compile(r"\b(" + "|".join(WEEKDAYS) + r")s?\b", re.I)
NUMBER_RE = re.compile(r"(?<![\w.])(\d+(?:,\d{3})*(?:\.\d+)?)(?![\w])")
WORD_RE = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\b", re.I)


@dataclass
class Token:
    kind: str      # "time" | "date" | "weekday" | "number"
    text: str      # as written in the brief
    value: Any     # normalized: "7:00 PM", "Nov 6", "Thu", 5.1
    start: int
    end: int


def extract_tokens(text: str, number_words: bool = True) -> list[Token]:
    """Find everything checkable in a piece of text. Times and dates are taken
    first so their digits aren't double-counted as bare numbers."""
    tokens: list[Token] = []
    taken: list[tuple[int, int]] = []

    def free(m: re.Match) -> bool:
        return not any(a < m.end() and m.start() < b for a, b in taken)

    def add(kind: str, m: re.Match, value: Any) -> None:
        tokens.append(Token(kind, m.group(0), value, m.start(), m.end()))
        taken.append((m.start(), m.end()))

    for m in TIME_RE.finditer(text):
        add("time", m, f"{m.group(1)} {m.group(2).upper()}M")
    for m in DATE_RE.finditer(text):
        if free(m):
            add("date", m, f"{m.group(1).title()} {int(m.group(2))}")
    for m in WEEKDAY_RE.finditer(text):
        if free(m):
            add("weekday", m, m.group(1)[:3].title())
    for m in NUMBER_RE.finditer(text):
        if free(m):
            add("number", m, float(m.group(1).replace(",", "")))
    if number_words:
        for m in WORD_RE.finditer(text):
            if free(m) and m.group(1).lower() != "zero":   # "zero tickets" is usually a joke
                add("number", m, float(NUMBER_WORDS[m.group(1).lower()]))
    return sorted(tokens, key=lambda t: t.start)


def _supported(token: Token, values: list[Any]) -> bool:
    strings = [str(v) for v in values if isinstance(v, str)]
    if token.kind == "time":
        return any(token.value.replace(" ", "").lower() in s.replace(" ", "").lower() for s in strings)
    if token.kind == "date":
        return any(re.search(rf"\b{re.escape(token.value)}\b", s) for s in strings)
    if token.kind == "weekday":
        return any(re.search(rf"\b{token.value}\b", s) for s in strings)

    # A number word inside a cited title ("One Flew Over the Cuckoo's Nest") is
    # part of the name, not a count.
    if token.text.isalpha() and any(re.search(rf"\b{token.text}\b", s, re.I) for s in strings):
        return True

    # number: match a numeric fact, a number inside a string fact, or a list's length
    candidates: list[float] = []
    for v in values:
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            candidates.append(float(v))
        elif isinstance(v, str):
            candidates += [float(x.replace(",", "")) for x in NUMBER_RE.findall(v)]
    places = len(token.text.split(".")[1]) if "." in token.text else 0
    return any(abs(c - token.value) < 1e-9 or round(c, places) == token.value for c in candidates)


def _cited_values(fact_ids: list[str], facts: dict[str, Any]) -> list[Any]:
    values: list[Any] = []
    for fid in fact_ids:
        v = facts.get(fid)
        if isinstance(v, list):
            values.append(len(v))
            values += v
        elif v is not None:
            values.append(v)
    return values


def check_grounding(draft: Draft, facts: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    full = f"{draft.headline}\n{draft.brief}"
    norm = lambda s: re.sub(r"\s+", " ", s.replace("’", "'")).strip()
    covered: list[tuple[int, int]] = []

    for c in draft.claims:
        where = norm(full).find(norm(c.text))
        if where < 0:
            problems.append(f'The claim "{c.text}" isn\'t in the brief word for word. Quote claims exactly.')
        else:
            covered.append((where, where + len(norm(c.text))))
        unknown = [f for f in c.fact_ids if f not in facts]
        if unknown:
            problems.append(f'The claim "{c.text}" cites fact ids that don\'t exist: {", ".join(unknown)}.')
        values = _cited_values(c.fact_ids, facts)
        for t in extract_tokens(c.text):
            if not _supported(t, values):
                problems.append(
                    f'"{t.text}" in "{c.text}" isn\'t in the facts it cites '
                    f'({", ".join(c.fact_ids) or "none"}). Cite the fact it comes from, or remove it.'
                )

    # Anything checkable in the headline or brief that no claim covers. Bare
    # "one" is skipped here ("no one", "this one") but still checked in claims.
    for t in extract_tokens(norm(full)):
        if t.text.lower() == "one":
            continue
        if not any(a <= t.start and t.end <= b for a, b in covered):
            problems.append(f'"{t.text}" appears in the brief without a claim backing it. Add a claim or cut it.')
    return problems


# ── 2. Style ─────────────────────────────────────────────────────────────────

CLICHES = ["you've got this", "you got this", "every step counts", "keep it up", "crush it",
           "rise and shine", "seize the day", "one step at a time"]
FIRST_PERSON = re.compile(r"\b(I'm|I'll|I've|I'd|I|me|my|we're|we'll|we|us|our)\b")   # longest first
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def check_style(draft: Draft) -> list[str]:
    problems: list[str] = []
    n = len(draft.brief.split())
    if not WORDS[0] <= n <= WORDS[1]:
        problems.append(f"The brief is {n} words; keep it between {WORDS[0]} and {WORDS[1]}.")
    if len(draft.headline.split()) >= 12:
        problems.append("The headline is 12 words or more; keep it under 12.")
    paragraphs = [p for p in draft.brief.split("\n\n") if p.strip()]
    if not 2 <= len(paragraphs) <= 3:
        problems.append(f"The brief has {len(paragraphs)} paragraphs; use two or three.")
    if re.search(r"^\s*(#|[-*•]\s|\d+\.\s)", draft.brief, re.M):
        problems.append("Drop the headers and bullet points; write plain paragraphs.")
    full = f"{draft.headline}\n{draft.brief}"
    for word in sorted({m.group(0) for m in FIRST_PERSON.finditer(full)}):
        problems.append(f'The writer refers to itself ("{word}"). Talk to her as "you" only.')
    for phrase in CLICHES:
        if phrase in full.lower():
            problems.append(f'Cut the motivational cliché "{phrase}".')
    if EMOJI.search(full):
        problems.append("Remove the emoji.")
    if full.count("!") > 1:
        problems.append("Use at most one exclamation mark.")
    return problems


# ── 3. Tone (LLM judge) ──────────────────────────────────────────────────────

REVIEW_TOOL = {
    "name": "submit_review",
    "description": "Submit the tone review.",
    "input_schema": {
        "type": "object",
        "properties": {
            **{k: {"type": "object",
                   "properties": {"score": {"type": "integer", "minimum": 1, "maximum": 5},
                                  "reason": {"type": "string"}},
                   "required": ["score", "reason"]} for k in THRESHOLDS},
            "best_line": {"type": "string"},
            "suggestions": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        },
        "required": [*THRESHOLDS, "best_line", "suggestions"],
    },
}


@dataclass
class ToneReview:
    scores: dict[str, int]
    reasons: dict[str, str]
    best_line: str
    suggestions: list[str]
    usage: dict[str, int] = field(default_factory=dict)

    def problems(self) -> list[str]:
        failing = [k for k, floor in THRESHOLDS.items() if self.scores.get(k, 0) < floor]
        if not failing:
            return []
        out = [f"Tone: {k} scored {self.scores[k]}/5 (needs {THRESHOLDS[k]}): {self.reasons[k]}" for k in failing]
        return out + [f"Suggestion: {s}" for s in self.suggestions]


def review_tone(draft: Draft, client: Any = None, model: str = JUDGE_MODEL) -> ToneReview:
    data, usage = call_tool(
        client or default_client(),
        model=model,
        system=JUDGE_PROMPT.read_text(),
        messages=[{"role": "user", "content": f"# {draft.headline}\n\n{draft.brief}"}],
        tool=REVIEW_TOOL,
        max_tokens=1500,
    )
    return ToneReview(
        scores={k: int(data[k]["score"]) for k in THRESHOLDS},
        reasons={k: data[k]["reason"] for k in THRESHOLDS},
        best_line=data.get("best_line", ""),
        suggestions=list(data.get("suggestions", [])),
        usage=usage,
    )


# ── All together ─────────────────────────────────────────────────────────────

@dataclass
class Evaluation:
    grounding: list[str]
    style: list[str]
    tone: ToneReview | None

    @property
    def problems(self) -> list[str]:
        """Everything that failed, phrased as feedback for the writer."""
        return self.grounding + self.style + (self.tone.problems() if self.tone else [])

    @property
    def passed(self) -> bool:
        return not self.problems

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "grounding": self.grounding, "style": self.style,
                "tone": asdict(self.tone) if self.tone else None}


def evaluate(draft: Draft, snapshot: dict[str, Any], *, client: Any = None, tone: bool = True) -> Evaluation:
    grounding = check_grounding(draft, flat_facts(snapshot))
    style = check_style(draft)
    # Skip the paid judge when the draft already has to be rewritten for facts.
    judged = review_tone(draft, client) if tone and not grounding else None
    return Evaluation(grounding, style, judged)


def _draft_from_json(d: dict) -> Draft:
    return Draft(headline=d["headline"], brief=d["brief"],
                 claims=[Claim(c["text"], c["fact_ids"]) for c in d["claims"]],
                 model=d.get("model", "?"), usage=d.get("usage", {}))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", type=date.fromisoformat)
    p.add_argument("--snapshot", type=Path, help="saved snapshot JSON (default: build one now)")
    p.add_argument("--draft", type=Path, help="saved draft JSON from `writer --json` (default: write one now)")
    p.add_argument("--no-tone", action="store_true", help="skip the LLM judge")
    args = p.parse_args(argv)

    from dotenv import load_dotenv
    load_dotenv()
    snapshot = json.loads(args.snapshot.read_text()) if args.snapshot else build_snapshot(args.date)
    if args.draft:
        draft = _draft_from_json(json.loads(args.draft.read_text()))
    else:
        from agents.morning_brief.writer import write
        draft = write(snapshot)

    result = evaluate(draft, snapshot, tone=not args.no_tone)
    print(f"# {draft.headline}\n\n{draft.brief}\n")
    print(f"grounding: {'ok' if not result.grounding else ''}")
    for x in result.grounding:
        print(f"  ✗ {x}")
    print(f"style: {'ok' if not result.style else ''}")
    for x in result.style:
        print(f"  ✗ {x}")
    if result.tone:
        t = result.tone
        print("tone: " + "  ".join(f"{k} {t.scores[k]}/5" for k in THRESHOLDS))
        for k in THRESHOLDS:
            print(f"  {k}: {t.reasons[k]}")
        if t.best_line:
            print(f'  best line: "{t.best_line}"')
        for s in t.suggestions:
            print(f"  → {s}")
    elif not args.no_tone:
        print("tone: skipped (fix grounding first)")
    print(f"\n{'PASS' if result.passed else 'FAIL'}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
