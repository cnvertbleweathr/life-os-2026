#!/usr/bin/env python3
"""
generate_insights.py

Reads exported CSVs from data/exports/, passes context to Claude,
and writes structured insights to data/insights/latest.json.

Covers (in priority order):
  1. Goal pacing — at current rate, will you hit each goal?
  2. Habit correlations — what habits correlate with better performance?
  3. Flags and risks — what's declining or off track?
  4. Weekly wins — highlights from the past 7 days

Usage:
  python scripts/generate_insights.py
  python scripts/generate_insights.py --year 2026
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, date, timedelta
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

EXPORTS_DIR  = ROOT / "data" / "exports"
INSIGHTS_DIR = ROOT / "data" / "insights"
INSIGHTS_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH     = INSIGHTS_DIR / "latest.json"


def read_csv(name: str) -> pd.DataFrame:
    path = EXPORTS_DIR / f"{name}.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def df_to_text(df: pd.DataFrame, max_rows: int = 30) -> str:
    if df.empty:
        return "No data available."
    return df.head(max_rows).to_string(index=False)


def call_claude(prompt: str, max_tokens: int = 1500) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY in .env")

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json={
            "model": "gpt-4o",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def build_context(year: int) -> dict[str, str]:
    today = date.today()
    week_ago = today - timedelta(days=7)
    day_of_year = today.timetuple().tm_yday
    weeks_elapsed = int(today.isocalendar().week)
    weeks_remaining = 52 - weeks_elapsed

    ctx = {
        "today": str(today),
        "year": str(year),
        "day_of_year": str(day_of_year),
        "weeks_elapsed": str(weeks_elapsed),
        "weeks_remaining": str(weeks_remaining),
    }

    # Load all exported data
    for name in [
        "goal_progress", "habit_summary", "habit_daily",
        "running_weekly", "running_summary",
        "crossfit_weekly", "crossfit_prs", "crossfit_lifts",
        "reading_summary", "books_read", "spotify_summary",
    ]:
        df = read_csv(name)
        ctx[name] = df_to_text(df)

    return ctx


def generate_goal_pacing(ctx: dict) -> str:
    prompt = f"""Today is {ctx['today']} — week {ctx['weeks_elapsed']} of {ctx['year']} 
({ctx['weeks_remaining']} weeks remaining).

Here is the current goal progress:
{ctx['goal_progress']}

Running weekly data:
{ctx['running_weekly']}

CrossFit weekly attendance:
{ctx.get('crossfit_weekly', 'No data')}

Reading summary:
{ctx['reading_summary']}

For each numeric goal, calculate:
- Current pace (per week or per month)
- Projected year-end value at current pace
- Whether they'll hit the goal, miss it, or are on track
- If missing, what weekly rate they need from now to still hit it

Format as concise bullet points. Be specific with numbers. Flag anything critically off track with ⚠️.
No preamble. Just bullets."""

    return call_claude(prompt, max_tokens=800)


def generate_habit_correlations(ctx: dict) -> str:
    prompt = f"""Here is the last 60 days of daily habit tracking:
{ctx['habit_daily']}

Here is weekly running data:
{ctx['running_weekly']}

Analyze correlations between habits and performance. Look for patterns like:
- Do meditation days correlate with better running or more habits completed?
- Are there streaks or consistency patterns worth noting?
- What does the data suggest about which habits drive other habits?

Be specific — reference actual dates or weeks if relevant.
Format as 3-5 concise bullet points. No preamble."""

    return call_claude(prompt, max_tokens=600)


def generate_flags_and_risks(ctx: dict) -> str:
    prompt = f"""Today is {ctx['today']}. Review this performance data and flag anything concerning.

Goal progress:
{ctx['goal_progress']}

Habit summary (YTD completion rates):
{ctx['habit_summary']}

Running weekly (most recent first):
{ctx['running_weekly']}

CrossFit weekly (most recent first):
{ctx.get('crossfit_weekly', 'No data')}

Identify:
- Goals that are significantly off pace
- Habits with low completion rates
- Drops in activity (e.g. consecutive weeks with low mileage or classes)
- Anything that needs attention before it becomes a bigger problem

Flag each issue with ⚠️. Be direct. Max 5 bullets. No preamble."""

    return call_claude(prompt, max_tokens=500)


def generate_weekly_wins(ctx: dict) -> str:
    prompt = f"""Today is {ctx['today']}. Look at the data from the past 7 days and identify wins and highlights.

Habit data (last 60 days, most recent first):
{ctx['habit_daily']}

Recent runs:
{ctx['running_weekly']}

Recent CrossFit PRs:
{ctx.get('crossfit_prs', 'No data')}

Books read this year:
{ctx['books_read']}

Identify wins from the PAST 7 DAYS specifically:
- Habit streaks or perfect days
- Strong running performance
- New PRs
- Books finished
- Any personal bests or notable achievements

Format as 3-5 upbeat bullet points. Use 🏆 for standout wins. No preamble."""

    return call_claude(prompt, max_tokens=400)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int, default=datetime.now().year)
    args = p.parse_args()

    if not EXPORTS_DIR.exists() or not list(EXPORTS_DIR.glob("*.csv")):
        raise SystemExit(
            f"No exports found in {EXPORTS_DIR}. "
            "Run `python scripts/export_for_insights.py` first."
        )

    print("Building context from exports...")
    ctx = build_context(args.year)

    print("Generating goal pacing...")
    goal_pacing = generate_goal_pacing(ctx)

    print("Generating habit correlations...")
    habit_correlations = generate_habit_correlations(ctx)

    print("Generating flags and risks...")
    flags_risks = generate_flags_and_risks(ctx)

    print("Generating weekly wins...")
    weekly_wins = generate_weekly_wins(ctx)

    output = {
        "generated_at": datetime.now().isoformat(),
        "year": args.year,
        "sections": {
            "goal_pacing":          goal_pacing,
            "habit_correlations":   habit_correlations,
            "flags_and_risks":      flags_risks,
            "weekly_wins":          weekly_wins,
        }
    }

    OUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"\nInsights written to {OUT_PATH}")

    # Preview
    print("\n" + "="*50)
    print("WEEKLY WINS:")
    print(weekly_wins)
    print("\nFLAGS & RISKS:")
    print(flags_risks)


if __name__ == "__main__":
    main()
