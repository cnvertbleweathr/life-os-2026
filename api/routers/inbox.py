"""
/api/inbox — the Capture Inbox (ROADMAP P0).

One place to drop anything that doesn't have a home yet: an idea, a task, a
link, something worth logging. Items append to data/inbox/capture_inbox.jsonl
via api.store and load into raw.capture_inbox on the next sync
(pipelines/inbox_pipeline.py).

Triage, AI classification, and promotion to core.actions are later steps.
Every item is created with status "new" and a stable capture_id so those
later steps can refer to it.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.store import INBOX_LOG, timestamp, today_local

router = APIRouter()

Kind = Literal["note", "idea", "task", "link", "log"]


class CaptureIn(BaseModel):
    text:   str = Field(min_length=1, max_length=4000)
    kind:   Kind = "note"
    domain: str | None = Field(default=None, max_length=40)
    source: str = Field(default="web", max_length=40)


@router.post("")
async def capture(body: CaptureIn):
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "text is empty")
    return INBOX_LOG.append({
        "capture_id":   uuid.uuid4().hex,
        "captured_at":  timestamp(),
        "capture_date": today_local().isoformat(),
        "text":         text,
        "kind":         body.kind,
        "domain":       (body.domain or "").strip().lower() or None,
        "source":       body.source,
        "status":       "new",
    })


@router.get("")
async def inbox_list(limit: int = 50):
    """Most recent captures first."""
    limit = max(1, min(limit, 500))
    latest = INBOX_LOG.latest_by("capture_id")
    rows = sorted(latest.values(), key=lambda r: r.get("captured_at", ""), reverse=True)
    return rows[:limit]
