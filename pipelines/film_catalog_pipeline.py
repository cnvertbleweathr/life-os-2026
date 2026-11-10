#!/usr/bin/env python3
"""
pipelines/film_catalog_pipeline.py: mirror the film scene catalog into DuckDB.

data/film/scene_catalog.jsonl (written by the API, the suggestion step and the
catalog CLI; see api/film_catalog.py) is the source of truth. This loads the
latest row per film_key into film.scene_catalog, replacing the table each run,
so the warehouse always matches the log.

Usage:
  python pipelines/film_catalog_pipeline.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import dlt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines._jsonl import data_dir, db_path, latest_by  # noqa: E402

COLUMNS = {
    "film_key":              {"data_type": "text", "nullable": False},
    "tmdb_id":               {"data_type": "bigint"},
    "title":                 {"data_type": "text"},
    "year":                  {"data_type": "bigint"},
    "scene_label":           {"data_type": "text"},
    "scene_note":            {"data_type": "text"},
    "suggested_timestamp_s": {"data_type": "double"},
    "suggestion_confidence": {"data_type": "text"},
    "render_mode":           {"data_type": "text"},
    "clip_start":            {"data_type": "double"},
    "clip_end":              {"data_type": "double"},
    "plex_file":             {"data_type": "text"},
    "youtube_url":           {"data_type": "text"},
    "status":                {"data_type": "text"},
    "gif_web":               {"data_type": "text"},
    "gif_matrix":            {"data_type": "text"},
    "render_error":          {"data_type": "text"},
    "suggested_by":          {"data_type": "text"},
    "suggested_at":          {"data_type": "text"},
    "approved_at":           {"data_type": "text"},
    "rejected_at":           {"data_type": "text"},
    "rendered_at":           {"data_type": "text"},
    "updated_at":            {"data_type": "text"},
}


def catalog_rows() -> list[dict]:
    latest = latest_by(data_dir() / "film" / "scene_catalog.jsonl", "film_key")
    return [{k: row.get(k) for k in COLUMNS} for row in latest.values()]


def run(destination_path: str | None = None, pipelines_dir: str | None = None):
    rows = catalog_rows()

    @dlt.resource(name="scene_catalog", write_disposition="replace", columns=COLUMNS)
    def scene_catalog():
        yield from rows

    pipeline = dlt.pipeline(
        pipeline_name="film_catalog",
        destination=dlt.destinations.duckdb(destination_path or db_path()),
        dataset_name="film",
        pipelines_dir=pipelines_dir,
    )
    info = pipeline.run(scene_catalog())
    print(f"film.scene_catalog: {len(rows)} rows")
    return info


if __name__ == "__main__":
    print(run())
