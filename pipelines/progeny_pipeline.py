#!/usr/bin/env python3
"""
Progeny DLT pipeline.

Loads the kids config, the committed reference YAML and the append-only
Progeny logs into DuckDB. The dashboard forms append to data/progeny/*.jsonl
(progeny/store.py); nothing writes to the warehouse except this pipeline.

Tables produced in DuckDB (schema: progeny):
  progeny.kids                    data/progeny/kids.yaml (replace)
  progeny.milestone_ref           progeny/reference/cdc_milestones.yaml (replace)
  progeny.path_levels             progeny/reference/learning_paths.yaml (replace)
  progeny.quotes                  quotes.jsonl         (merge on id)
  progeny.firsts                  firsts.jsonl         (merge on id)
  progeny.books                   books.jsonl          (merge on id)
  progeny.milestone_observations  milestones.jsonl     (merge on id)
  progeny.path_evidence           path_evidence.jsonl  (merge on id)
  progeny.prep_tasks              prep_tasks.jsonl     (merge on id)

The logs are collapsed to the latest line per id before loading, so an edit
replaces its row and a tombstone ({"id", "deleted": true}) marks it deleted.
Staging models drop deleted rows. Empty or missing logs load nothing, and
the staging models fall back to typed empty selects (relation_if_exists).

Usage:
  python pipelines/progeny_pipeline.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator

import dlt

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # run as a plain script from pipelines/
    sys.path.insert(0, str(ROOT))

from pipelines._jsonl import db_path  # noqa: E402
from progeny import store  # noqa: E402

TEXT, DATE, BOOL = "text", "date", "bool"

COMMON = {"id": TEXT, "deleted": BOOL, "logged_at": TEXT, "source": TEXT}

# Explicit, nullable column types so every column exists (and is typed) even
# before a row ever fills it in. Values are dlt data types.
LOG_TABLES: dict[str, tuple[str, dict[str, str]]] = {
    "quotes":        ("quotes", {"kid": TEXT, "date": DATE, "quote": TEXT, "context": TEXT}),
    "firsts":        ("firsts", {"kid": TEXT, "date": DATE, "title": TEXT, "notes": TEXT}),
    "books":         ("books", {"kid": TEXT, "date": DATE, "title": TEXT, "author": TEXT,
                                "repeat": BOOL}),
    "milestones":    ("milestone_observations", {"kid": TEXT, "milestone_id": TEXT,
                                                 "observed_date": DATE, "notes": TEXT}),
    "path_evidence": ("path_evidence", {"kid": TEXT, "path": TEXT, "level": TEXT,
                                        "date": DATE, "notes": TEXT}),
    "prep_tasks":    ("prep_tasks", {"task": TEXT, "category": TEXT, "due_date": DATE,
                                     "done_date": DATE, "created_date": DATE}),
}


def _hints(types: dict[str, str]) -> dict[str, dict]:
    # A fresh dict per column: dlt annotates hint dicts in place, so sharing
    # one object between columns corrupts the schema.
    return {name: {"data_type": t, "nullable": True} for name, t in types.items()}


def _log_resource(kind: str):
    table, cols = LOG_TABLES[kind]
    types = {**COMMON, **cols}

    @dlt.resource(name=table, write_disposition="merge", primary_key="id", columns=_hints(types))
    def _rows() -> Iterator[dict]:
        for row in store.latest_entries(kind):
            # Keep only known columns; a stray key in a hand-edited line
            # shouldn't add a column to the warehouse.
            out = {c: row.get(c) for c in types}
            out["deleted"] = bool(row.get("deleted", False))
            for c, t in types.items():
                if t == DATE and out[c] == "":
                    out[c] = None
            yield out

    return _rows


@dlt.resource(name="kids", write_disposition="replace",
              columns=_hints({"kid_id": TEXT, "display_name": TEXT, "birthdate": DATE,
                              "due_date": DATE, "kindergarten_start": DATE}))
def kids_resource() -> Iterator[dict]:
    yield from store.load_kids()


@dlt.resource(name="milestone_ref", write_disposition="replace")
def milestone_ref_resource() -> Iterator[dict]:
    yield from store.milestone_rows()


@dlt.resource(name="path_levels", write_disposition="replace")
def path_levels_resource() -> Iterator[dict]:
    yield from store.path_level_rows()


def run(year: int | None = None) -> None:  # year: run_pipelines.py passes it to every pipeline
    pipeline = dlt.pipeline(
        pipeline_name="progeny",
        destination=dlt.destinations.duckdb(db_path()),
        dataset_name="progeny",
    )
    resources = [milestone_ref_resource(), path_levels_resource()]
    if store.kids_path().exists():
        # Only replace kids when the config exists, so a missing file never
        # silently empties the table.
        resources.append(kids_resource())
    else:
        print(f"progeny: no {store.kids_path()} yet; copy progeny/config/kids.example.yaml there")
    resources += [_log_resource(kind)() for kind in LOG_TABLES]

    print(pipeline.run(resources))


if __name__ == "__main__":
    run()
