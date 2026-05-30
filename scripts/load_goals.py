from pathlib import Path
import json

import duckdb
import pandas as pd
import yaml

DB_PATH = Path("data/warehouse/ons.duckdb")
GOALS_PATH = Path("goals/2026.yaml")


def get_goals_root(goals_doc: dict) -> tuple[int, dict]:
    """
    Supports either of these YAML shapes:

    Shape A:
      year: 2026
      domains:
        fitness:
          running_miles: 350

    Shape B:
      fitness:
        running_miles: 350
    """
    year = goals_doc.get("year", 2026)

    if "domains" in goals_doc and isinstance(goals_doc["domains"], dict):
        return year, goals_doc["domains"]

    ignored_top_level_keys = {"year", "metadata", "notes"}
    domains = {
        key: value
        for key, value in goals_doc.items()
        if key not in ignored_top_level_keys
    }

    return year, domains


def flatten_goals(year: int, domains: dict) -> list[dict]:
    rows = []

    for domain, values in domains.items():
        if not isinstance(values, dict):
            rows.append(
                {
                    "year": year,
                    "domain": domain,
                    "goal_key": domain,
                    "goal_value": json.dumps(values),
                    "goal_value_type": type(values).__name__,
                }
            )
            continue

        for goal_key, goal_value in values.items():
            rows.append(
                {
                    "year": year,
                    "domain": domain,
                    "goal_key": goal_key,
                    "goal_value": json.dumps(goal_value),
                    "goal_value_type": type(goal_value).__name__,
                }
            )

    return rows


def main() -> None:
    if not GOALS_PATH.exists():
        raise FileNotFoundError(f"Could not find {GOALS_PATH}")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with GOALS_PATH.open("r") as f:
        goals_doc = yaml.safe_load(f)

    year, domains = get_goals_root(goals_doc)
    rows = flatten_goals(year, domains)
    df = pd.DataFrame(rows)

    if df.empty:
        raise ValueError("No goals found. Check goals/2026.yaml structure.")

    with duckdb.connect(DB_PATH) as con:
        con.execute("create schema if not exists raw")
        con.register("goals_df", df)

        con.execute("""
            create or replace table raw.raw_goals as
            select * from goals_df
        """)

        print("Loaded goals by domain:")
        print(
            con.execute("""
                select domain, count(*) as goals
                from raw.raw_goals
                group by domain
                order by domain
            """).df()
        )


if __name__ == "__main__":
    main()