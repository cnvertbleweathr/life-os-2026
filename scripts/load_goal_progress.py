from pathlib import Path

import duckdb
import pandas as pd

DB_PATH = Path("data/warehouse/lifeos.duckdb")
PROGRESS_PATH = Path("data/manual/goal_progress.csv")


def main() -> None:
    if not PROGRESS_PATH.exists():
        raise FileNotFoundError(f"Could not find {PROGRESS_PATH}")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(PROGRESS_PATH)

    required_columns = {
    "year",
    "domain",
    "goal_key",
    "current_value",
    "status",
    "updated_at",
    "notes",
    }

    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(f"Missing required columns: {sorted(missing_columns)}")

    with duckdb.connect(DB_PATH) as con:
        con.execute("create schema if not exists raw")
        con.register("goal_progress_df", df)

        con.execute("""
            create or replace table raw.raw_goal_progress as
            select
                cast(year as integer) as year,
                lower(trim(domain)) as domain,
                lower(trim(goal_key)) as goal_key,
                try_cast(current_value as double) as current_value,
                lower(trim(status)) as status,
                cast(updated_at as date) as updated_at,
                notes
            from goal_progress_df
        """)

        print("Loaded goal progress:")
        print(
            con.execute("""
                select domain, goal_key, current_value, updated_at
                from raw.raw_goal_progress
                order by domain, goal_key
            """).df()
        )


if __name__ == "__main__":
    main()
