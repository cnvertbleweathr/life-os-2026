from pathlib import Path
import duckdb

DB_PATH = Path("data/warehouse/ons.duckdb")
OUTPUT_PATH = Path("data/manual/goal_progress.csv")


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(DB_PATH) as con:
        df = con.execute("""
            select
                year,
                domain,
                goal_key,
                case
                    when goal_value_type in ('int', 'float') then 0
                    when goal_value_type = 'bool' then 0
                    else null
                end as current_value,
                current_date as updated_at,
                '' as notes
            from raw.raw_goals
            order by domain, goal_key
        """).df()

    if OUTPUT_PATH.exists():
        backup_path = OUTPUT_PATH.with_suffix(".backup.csv")
        OUTPUT_PATH.rename(backup_path)
        print(f"Existing progress file backed up to {backup_path}")

    df.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote progress template to {OUTPUT_PATH}")
    print(df)


if __name__ == "__main__":
    main()
