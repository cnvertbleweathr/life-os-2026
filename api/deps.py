"""
Shared utilities for all ONS API routers.
"""

from __future__ import annotations

import math
from typing import Any

import duckdb
import pandas as pd
from fastapi import Request


def get_db(request: Request) -> duckdb.DuckDBPyConnection:
    """Return the shared read-only DuckDB connection from app state."""
    return request.app.state.db


def _clean(value: Any) -> Any:
    """Convert NaN/NaT/pd.NA to None. float('nan') is not valid JSON."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def query(db: duckdb.DuckDBPyConnection, sql: str, params: list | None = None) -> list[dict[str, Any]]:
    """Execute SQL and return list of dicts. Returns [] on error."""
    try:
        df = db.execute(sql, params or []).df()
        records = df.to_dict(orient="records")
        return [{k: _clean(v) for k, v in row.items()} for row in records]
    except Exception:
        return []


def query_one(db: duckdb.DuckDBPyConnection, sql: str, params: list | None = None) -> dict[str, Any] | None:
    """Execute SQL and return first row as dict, or None."""
    rows = query(db, sql, params)
    return rows[0] if rows else None
