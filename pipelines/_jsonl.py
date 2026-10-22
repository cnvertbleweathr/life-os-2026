"""
Shared reader for the append-only JSONL logs the API writes (see api/store.py).

The logs keep every write, so a habit toggled three times in a day is three
lines. Pipelines must collapse to the latest line per key before loading,
otherwise counts double up. That collapse lives here so every pipeline
does it the same way.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    return Path(os.getenv("ONS_DATA_DIR", ROOT / "data"))


def db_path() -> str:
    return os.getenv("ONS_DUCKDB_PATH", str(ROOT / "data" / "warehouse" / "ons.duckdb"))


def read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def latest_by(path: Path, key: str) -> dict[Any, dict[str, Any]]:
    """Last row per value of `key`; later lines win."""
    latest: dict[Any, dict[str, Any]] = {}
    for row in read_rows(path):
        k = row.get(key)
        if k:
            latest[k] = row
    return latest
