# Testing
_Last updated: 2026-05-29_

## Summary
This codebase has no automated test suite. Validation is done manually via `--dry-run` flags on individual scripts, visual inspection of the Streamlit dashboard, and observing the daily sync orchestrator's output. There is no CI/CD pipeline.

## Test Frameworks
- None. No pytest, unittest, or other test framework is installed or configured.
- No test files exist in the repository (`test_*.py`, `*_test.py`, `tests/` directory, etc.).

## How Correctness Is Verified Today
- **`--dry-run` flags**: Several scripts (e.g., `scripts/daily_sync.py`) accept a dry-run mode that runs the pipeline without writing output.
- **dbt runs**: The dbt project provides SQL-level transformation validation through `dbt run` and `dbt test` (if models have tests configured).
- **Streamlit dashboard**: Visual inspection of the dashboard is the primary end-to-end validation method.
- **Log output**: Scripts emit structured logs; watching log output during runs is the de facto integration test.

## CI/CD
- None. No GitHub Actions, no pre-commit hooks, no automated pipeline.

## Easiest Functions to Test First
These pure functions have no external dependencies and would be straightforward to cover with unit tests:
- `normalize_timestamp_to_iso()` — timestamp normalization
- `_parse_dt()` — date parsing
- `_normalize_tags()` — tag normalization
- `_classify()` — content classification
- `spotify_safe_text()` — text sanitization for Spotify API

## Recommendations
1. Add `pytest` and write unit tests for the pure utility functions listed above.
2. Add a smoke-test script that runs the full daily sync in dry-run mode and asserts expected output shapes.
3. Consider a pre-commit hook that runs linting (ruff) on changed files.
