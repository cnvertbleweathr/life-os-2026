#!/usr/bin/env python3
"""
weekly_reflection.py

Runs every Sunday. Reads the week's data across all domains,
calls GPT-4o to write a 1-paragraph reflection + 3 focus areas
for next week. Saves to data/insights/weekly_reflection.md.

Usage:
  python scripts/weekly_reflection.py
  python scripts/weekly_reflection.py --force   # run even if not Sunday
"""

from __future__ import annotations

import argparse
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
OUT_PATH     = INSIGHTS_DIR / "weekly_reflection.md"


def read_csv(name: str) -> pd.DataFrame:
    path = EXPORTS_DIR / f"{name}.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def df_to_text(df: pd.DataFrame, max_rows: int = 20) -> str:
    if df.empty:
        return "No data."
    return df.head(max_rows).to_string(index=False)


def call_gpt(prompt: str, max_tokens: int = 1000) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
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


def get_week_data() -> dict[str, str]:
    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # Monday
    week_end   = week_start + timedelta(days=6)

    data = {}

    # Habits this week
    habit_daily = read_csv("habit_daily")
    if not habit_daily.empty:
        habit_daily["log_date"] = pd.to_datetime(habit_daily["log_date"], errors="coerce")
        this_week = habit_daily[
            (habit_daily["log_date"].dt.date >= week_start) &
            (habit_daily["log_date"].dt.date <= week_end)
        ]
        data["habits"] = df_to_text(this_week)
    else:
        data["habits"] = "No habit data."

    # Runs this week
    running = read_csv("running_weekly")
    if not running.empty:
        week_label = week_start.strftime("%Y-W%W")
        this_week_runs = running[running["week"] == week_label]
        data["running"] = df_to_text(this_week_runs) if not this_week_runs.empty else "No runs this week."
    else:
        data["running"] = "No running data."

    # CrossFit this week
    crossfit = read_csv("crossfit_weekly")
    if not crossfit.empty:
        week_label = week_start.strftime("%Y-W%W")
        this_week_cf = crossfit[crossfit["week"] == week_label]
        data["crossfit"] = df_to_text(this_week_cf) if not this_week_cf.empty else "No CrossFit this week."
    else:
        data["crossfit"] = "No CrossFit data."

    # PRs this week
    prs = read_csv("crossfit_prs")
    if not prs.empty:
        prs["date"] = pd.to_datetime(prs["date"], errors="coerce")
        this_week_prs = prs[
            (prs["date"].dt.date >= week_start) &
            (prs["date"].dt.date <= week_end)
        ]
        data["prs"] = df_to_text(this_week_prs) if not this_week_prs.empty else "No PRs this week."
    else:
        data["prs"] = "No PR data."

    # Books finished this week
    books = read_csv("books_read")
    if not books.empty:
        books["marked_read_at"] = pd.to_datetime(books["marked_read_at"], errors="coerce")
        this_week_books = books[
            (books["marked_read_at"].dt.date >= week_start) &
            (books["marked_read_at"].dt.date <= week_end)
        ]
        data["books"] = df_to_text(this_week_books) if not this_week_books.empty else "No books finished this week."
    else:
        data["books"] = "No reading data."

    # Goal progress snapshot
    data["goals"] = df_to_text(read_csv("goal_progress"))

    data["week_start"] = str(week_start)
    data["week_end"]   = str(week_end)
    data["today"]      = str(today)

    return data


def generate_reflection(data: dict) -> str:
    prompt = f"""You are a sharp, honest personal coach reviewing someone's week.

Week: {data['week_start']} to {data['week_end']}

HABITS THIS WEEK:
{data['habits']}

RUNNING THIS WEEK:
{data['running']}

CROSSFIT THIS WEEK:
{data['crossfit']}

NEW PRs THIS WEEK:
{data['prs']}

BOOKS FINISHED THIS WEEK:
{data['books']}

OVERALL GOAL PROGRESS:
{data['goals']}

Write a weekly reflection with exactly this structure:

**Week of {data['week_start']}**

[One honest paragraph — 4-6 sentences — about how the week went across fitness, habits, and personal growth. Be specific. Acknowledge both wins and gaps. Don't sugarcoat.]

**3 Focus Areas for Next Week:**
1. [Specific, actionable focus — not generic]
2. [Specific, actionable focus]
3. [Specific, actionable focus]

Be direct and personal. Use "you" to address the reader. Reference actual data points."""

    return call_gpt(prompt, max_tokens=600)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true", help="Run even if not Sunday")
    args = p.parse_args()

    today = date.today()
    is_sunday = today.weekday() == 6

    if not is_sunday and not args.force:
        print(f"Today is {today.strftime('%A')} — weekly reflection runs on Sundays.")
        print("Use --force to run anyway.")
        return

    print(f"Generating weekly reflection for week of {today - timedelta(days=today.weekday())}...")

    if not EXPORTS_DIR.exists():
        raise SystemExit("No exports found. Run `python scripts/export_for_insights.py` first.")

    data = get_week_data()
    reflection = generate_reflection(data)

    # Write markdown
    week_start = today - timedelta(days=today.weekday())
    content = f"<!-- generated: {datetime.now().isoformat()} -->\n\n{reflection}\n"
    OUT_PATH.write_text(content)
    print(f"Reflection written to {OUT_PATH}")
    print("\n" + reflection)


if __name__ == "__main__":
    main()
