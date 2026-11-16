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
| 2 | **Writer**: one LLM call that takes the snapshot and returns the brief plus claims citing fact ids (`writer.py`, `prompts/writer.md`) | drafted |
| 3 | **Evaluators**: a code check that every cited number matches its fact, and an LLM judge that scores tone against a rubric | |
| 4 | **Revise loop**: failed checks go back to the writer as feedback, capped at 3 tries; every draft and score is logged | |
| 5 | **Eval set**: saved snapshots plus your own ratings, run on every prompt change; checks whether the judge agrees with you | |
| 6 | **Ship**: world-news tool, `daily_sync` step after `dbt run`, API endpoint, home-page card | |

## Stage 1 notes

- Each tool returns `facts` (flat, named, the only things the writer may claim), `as_of` and `stale` (how fresh the data is), and `notes` (context the writer needs, e.g. "shows are matched by name, not tickets you hold").
- Habits are read from `data/habits/habits_log.jsonl`, the file the Habits page writes to. `main_marts.mart_habit_streaks` is built from `habits.habit_log`, which has fallen behind, and it currently reports every streak as 0.
- A tool that fails records an `error` and the rest still run. A missing log day is "unknown", not "missed".

```bash
python -m agents.morning_brief.writer --show-prompt  # what the writer sees, no API call
python -m agents.morning_brief.writer                # write today's brief
python -m agents.morning_brief.snapshot --facts        # what the agent can see today
python -m agents.morning_brief.snapshot --save         # keep it for the eval set
pytest tests/test_morning_brief_*.py
```
