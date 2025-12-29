"""
Compute fitness metrics from SugarWOD cleaned workouts.

Reads:
  data/sugarwod/processed/workouts_clean.csv

Writes:
  data/sugarwod/metrics/fitness_summary_2026.csv
"""

from __future__ import annotations

import os
import pandas as pd

INPUT_PATH = "data/sugarwod/processed/workouts_clean.csv"
OUTPUT_PATH = "data/sugarwod/metrics/fitness_summary_2026.csv"

CROSSFIT_CLASSES_GOAL = 160


def main():
    if not os.path.exists(INPUT_PATH):
        raise FileNotFoundError(
            f"Missing {INPUT_PATH}. Run scripts/import_sugarwod_csv.py first."
        )

    df = pd.read_csv(INPUT_PATH)
    if df.empty:
        raise RuntimeError(
            "workouts_clean.csv has 0 rows. Export a real SugarWOD CSV and re-run import."
        )

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["year"] = df["date"].dt.year
    df_2026 = df[df["year"] == 2026].copy()

    classes_attended = len(df_2026)
    required_per_week = CROSSFIT_CLASSES_GOAL / 52

    # If no workouts yet in 2026, avoid NaNs and keep output clean
    if classes_attended == 0:
        weeks_elapsed = 0
        classes_per_week = 0.0
        rx_rate = ""
        pr_count = 0
    else:
        df_2026["week"] = df_2026["date"].dt.isocalendar().week.astype(int)
        weeks_elapsed = int(df_2026["week"].max())
        weeks_elapsed = max(weeks_elapsed, 1)
        classes_per_week = classes_attended / weeks_elapsed

        rx_rate = ""
        if "rx_or_scaled" in df_2026.columns:
            rx_rate = round((df_2026["rx_or_scaled"].str.upper() == "RX").mean(), 3)

        pr_count = int(df_2026["pr"].sum()) if "pr" in df_2026.columns else 0


    # RX rate
    rx_rate = None
    if "rx_or_scaled" in df_2026.columns:
        rx_rate = (df_2026["rx_or_scaled"].str.upper() == "RX").mean()

    # PR count (if present)
    pr_count = int(df_2026["pr"].sum()) if "pr" in df_2026.columns else None

    summary = {
        "classes_attended_2026": classes_attended,
        "classes_goal": CROSSFIT_CLASSES_GOAL,
        "classes_progress_pct": round((classes_attended / CROSSFIT_CLASSES_GOAL) * 100, 2),
        "weeks_elapsed": weeks_elapsed,
        "classes_per_week": round(classes_per_week, 2),
        "required_classes_per_week": round(required_per_week, 2),
        "rx_rate": round(rx_rate, 3) if rx_rate is not None else "",
        "pr_count": pr_count if pr_count is not None else "",
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    pd.DataFrame([summary]).to_csv(OUTPUT_PATH, index=False)

    print("Wrote:", OUTPUT_PATH)
    print(summary)


if __name__ == "__main__":
    main()

