"""
Shared utilities for all ONS API routers.
"""

from __future__ import annotations

from typing import Any

import duckdb
import pandas as pd
from fastapi import Request


def get_db(request: Request) -> duckdb.DuckDBPyConnection:
    """Return the shared read-only DuckDB connection from app state."""
    return request.app.state.db


def query(db: duckdb.DuckDBPyConnection, sql: str, params: list | None = None) -> list[dict[str, Any]]:
    """Execute SQL and return list of dicts. Returns [] on error."""
    try:
        df = db.execute(sql, params or []).df()
        return df.where(pd.notna(df), None).to_dict(orient="records")
    except Exception:
        return []


def query_one(db: duckdb.DuckDBPyConnection, sql: str, params: list | None = None) -> dict[str, Any] | None:
    """Execute SQL and return first row as dict, or None."""
    rows = query(db, sql, params)
    return rows[0] if rows else None
