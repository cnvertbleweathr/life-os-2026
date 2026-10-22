"""
ONS FastAPI — query layer over DuckDB/dbt marts.

Run:
  uv add fastapi uvicorn
  uvicorn api.main:app --reload --port 8000

All endpoints return JSON. The Next.js frontend consumes these.
DuckDB is opened read-only on startup and shared across requests.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import duckdb
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import (
    cfb,
    checkin,
    fitness,
    goals,
    habits,
    home,
    inbox,
    kglw,
    music,
    reading,
    shows,
    sports,
)

ROOT    = Path(__file__).resolve().parents[1]
DB_PATH = str(ROOT / "data" / "warehouse" / "ons.duckdb")

# ── Shared DuckDB connection ──────────────────────────────────────────────────
# Opened once on startup, injected into routers via app.state.db
# All queries are read-only. User input (habits, check-ins, captures) is
# appended to JSONL logs by api/store.py and loaded by the daily sync.

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = duckdb.connect(DB_PATH, read_only=True)
    yield
    app.state.db.close()


app = FastAPI(
    title="ONS API",
    description="Operating Narcisystem — query layer over DuckDB/dbt marts",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow Next.js dev server and production domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",   # Next.js dev
        "http://localhost:3001",
        "https://capuchin.cyou",   # production domain
        "https://www.capuchin.cyou",
        "https://narcisystem.com",
        "https://www.narcisystem.com"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(home.router,    prefix="/api/home",    tags=["home"])
app.include_router(habits.router,  prefix="/api/habits",  tags=["habits"])
app.include_router(fitness.router, prefix="/api/fitness", tags=["fitness"])
app.include_router(reading.router, prefix="/api/reading", tags=["reading"])
app.include_router(goals.router,   prefix="/api/goals",   tags=["goals"])
app.include_router(music.router,   prefix="/api/music",   tags=["music"])
app.include_router(shows.router,   prefix="/api/shows",   tags=["shows"])
app.include_router(sports.router,  prefix="/api/sports",  tags=["sports"])
app.include_router(cfb.router,     prefix="/api/cfb",     tags=["cfb"])
app.include_router(kglw.router,    prefix="/api/kglw",    tags=["kglw"])

# Write path — these append to JSONL logs (api/store.py), never to DuckDB.
app.include_router(checkin.router, prefix="/api/checkin", tags=["checkin"])
app.include_router(inbox.router,   prefix="/api/inbox",   tags=["inbox"])

@app.get("/api/health")
async def health():
    return {"status": "ok", "db": DB_PATH}
