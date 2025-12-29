"""
Import SugarWOD workout export CSV and produce a cleaned, normalized dataset.

Input:
  data/sugarwod/exports/workouts_YYYYMMDD.csv  (or any csv path)

Output:
  data/sugarwod/processed/workouts_clean.csv
"""

from __future__ import annotations

import argparse
import os
import pandas as pd


EXPORT_DIR = "data/sugarwod/exports"
OUTPUT_PATH = "data/sugarwod/processed/workouts_clean.csv"


def find_latest_export(export_dir: str) -> str:
    csvs = [
        os.path.join(export_dir, f)
        for f in os.listdir(export_dir)
        if f.lower().endswith(".csv")
    ]
    if not csvs:
        raise FileNotFoundError(
            f"No CSV exports found in {export_dir}. "
            f"Export from SugarWOD and place the file there."
        )
    return max(csvs, key=os.path.getmtime)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    # Standardize column names
    df.columns = [c.strip() for c in df.columns]

    # Parse date column (mm/dd/yyyy per your spec)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], format="%m/%d/%Y", errors="coerce")

    # Normalize text fields
    text_cols = [
        "title", "description", "score_type", "barbell_lift",
        "set_details", "notes", "rx_or_scaled", "best_result_display"
    ]
    for c in text_cols:
        if c in df.columns:
            df[c] = df[c].fillna("").astype(str).str.strip()

    # best_result_raw -> numeric
    if "best_result_raw" in df.columns:
        df["best_result_raw"] = pd.to_numeric(df["best_result_raw"], errors="coerce")

    # pr -> boolean-ish
    if "pr" in df.columns:
        # SugarWOD exports vary; make robust
        df["pr"] = (
            df["pr"]
            .astype(str)
            .str.strip()
            .str.lower()
            .isin(["true", "1", "yes", "y"])
        )

    # Drop completely empty rows (sometimes exports include blanks)
    df = df.dropna(how="all")

    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="Path to SugarWOD export CSV. If omitted, uses latest in exports folder.")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    input_path = args.input or find_latest_export(EXPORT_DIR)
    df = pd.read_csv(input_path)

    df_clean = clean(df)

    df_clean.to_csv(OUTPUT_PATH, index=False)
    print(f"Imported: {input_path}")
    print(f"Rows: {len(df_clean)}")
    print(f"Wrote: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

