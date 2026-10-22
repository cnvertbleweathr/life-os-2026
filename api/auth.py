"""
api/auth.py — guard for personal endpoints (writes, check-in notes, inbox).

narcisystem.com is public through Cloudflare Tunnel, so anything the API
serves is reachable by anyone. Read-only dashboards were already public by
choice; endpoints that write, or that return free-text personal notes, are not.

Rule:
  - Requests that did NOT come through Cloudflare (no CF-Connecting-IP header:
    curl on the Mac mini, local dev, Tailscale) are trusted.
  - Requests through the tunnel must send X-ONS-Write-Token matching
    ONS_WRITE_TOKEN from .env.
  - If ONS_WRITE_TOKEN is unset, tunnel requests are refused outright
    (fail closed) rather than left open.

Cloudflare sets CF-Connecting-IP on every request it forwards and overwrites
any value a client sends, and port 8000 is only reachable locally, so the
header reliably marks public traffic.

Generate a token:  python -c "import secrets; print(secrets.token_urlsafe(32))"
"""

from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Request

TOKEN_HEADER = "x-ons-write-token"


def require_owner(request: Request) -> None:
    if "cf-connecting-ip" not in request.headers:
        return  # local / Tailscale

    expected = os.getenv("ONS_WRITE_TOKEN", "")
    if not expected:
        raise HTTPException(
            403,
            "Personal endpoints are disabled over the public internet until "
            "ONS_WRITE_TOKEN is set on the server.",
        )
    supplied = request.headers.get(TOKEN_HEADER, "")
    if not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(401, "Write key required")
