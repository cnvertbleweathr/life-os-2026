# Morning brief agent

A daily brief for the ONS home page: where things stand with habits, training, reading, film, shows and the calendar, written to be fun to read in the morning. An evaluation loop checks every brief before it's published.

Plain Python and direct API calls, no agent framework. Once stages 1–4 work, the loop gets rebuilt in LangGraph for comparison.

## Shape

```
tools.py ─► snapshot ─► writer ─► draft + cited claims
                           ▲               │
                           │               ▼
                      feedback ◄── evaluators: grounding (code) + tone (LLM judge)
                                           │ pass
                                           ▼
                                  DuckDB log ─► API ─► home page
```

This is the evaluator–optimizer (reflection) pattern: one model writes, the evaluators grade, and the feedback goes back for another draft, up to a fixed number of tries.

## Stages

| # | Piece | Status |
|---|---|---|
| 1 | **Data tools** (`tools.py`, `snapshot.py`): deterministic functions that turn the warehouse and data files into named facts | in review |
| 2 | **Writer**: one LLM call that takes the snapshot and returns the brief plus claims citing fact ids (`writer.py`, `prompts/writer.md`) | in review |
| 3 | **Evaluators**: a code check that every cited number matches its fact, and an LLM judge that scores tone against a rubric (`evaluators.py`, `prompts/judge.md`) | drafted |
| 4 | **Revise loop**: failed checks go back to the writer as feedback, capped at 3 tries; every draft and score is logged | |
| 5 | **Eval set**: saved snapshots plus your own ratings, run on every prompt change; checks whether the judge agrees with you | |
| 6 | **Ship**: world-news tool, `daily_sync` step after `dbt run`, API endpoint, home-page card | |

## Stage 1 notes

- Each tool returns `facts` (flat, named, the only things the writer may claim), `as_of` and `stale` (how fresh the data is), and `notes` (context the writer needs, e.g. "shows are matched by name, not tickets you hold").
- Habits are read from `data/habits/habits_log.jsonl`, the file the Habits page writes to. `main_marts.mart_habit_streaks` is built from `habits.habit_log`, which has fallen behind, and it currently reports every streak as 0.
- A tool that fails records an `error` and the rest still run. A missing log day is "unknown", not "missed".

```bash
uv run python -m agents.morning_brief.evaluators            # write today's brief and grade it
uv run python -m agents.morning_brief.evaluators --no-tone  # grade without the judge's API call
uv run python -m agents.morning_brief.writer --show-prompt  # what the writer sees, no API call
uv run python -m agents.morning_brief.writer                # write today's brief
uv run python -m agents.morning_brief.snapshot --facts        # what the agent can see today
uv run python -m agents.morning_brief.snapshot --save         # keep it for the eval set
uv run pytest tests/test_morning_brief_*.py
```

## Stage 3 notes

- Three checks, cheapest first: **grounding** (code), **style** (code), **tone** (LLM judge, a cheaper model via `ONS_JUDGE_MODEL`). The judge only runs once grounding passes, so it isn't paid to grade a draft that has to be rewritten anyway.
- Grounding pulls every number, number word, date, weekday and time out of each claim and checks it against the facts that claim cites. Anything checkable outside a claim, headline included, is flagged as uncited.
- Every problem is phrased as an instruction ("Cite the fact it comes from, or remove it"), because in stage 4 problems become the writer's feedback.
- The judge only gives scores; code decides pass/fail with `THRESHOLDS`. Code is better at catching "wrong"; the judge is better at catching "accurate but not funny".
- What none of it catches: true numbers with a false spin ("your best week ever"). That's what your own ratings in stage 5 are for.
- The tests use the real Nov 15 brief. It looked clean by hand; grounding finds an uncited "Three" in the headline and a "since Nov 6" cited to the wrong facts. Every section now exposes a citable `newest_data` fact for that.
